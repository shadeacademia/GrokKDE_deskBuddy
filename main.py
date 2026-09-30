#!/usr/bin/env python3
"""Always-on Grok corner for this KDE session."""

import json
import os
import sys
import fcntl
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QFileSystemWatcher,
    QModelIndex,
    QObject,
    Property,
    QProcess,
    QProcessEnvironment,
    QTimer,
    QUrl,
    Qt,
    Signal,
    Slot,
    qInstallMessageHandler,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from prefs import account_signed_in, autostart_enabled, desktop_entry
from stream import StreamParser

GROK = str(Path.home() / ".grok" / "bin" / "grok")
CWD = str(Path.home())
APP_DIR = Path(__file__).resolve().parent
AUTH_PATH = Path.home() / ".grok" / "auth.json"
AUTOSTART_PATH = Path.home() / ".config" / "autostart" / "grok-corner.desktop"
ICON_PATH = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "grok-corner.png"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/grok-corner-{os.getuid()}")) / "grok-corner"
SESSION_PATH = RUNTIME / "session"
TRANSCRIPT_PATH = RUNTIME / "transcript.json"
LOG_PATH = RUNTIME / "log"
LOCK_PATH = RUNTIME / "lock"


def log(message: str) -> None:
    try:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except OSError:
        pass


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_transcript() -> list[dict]:
    data = _read_json(TRANSCRIPT_PATH)
    if not isinstance(data, list):
        return []
    items = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        who = entry.get("who")
        body = entry.get("body")
        if who in ("user", "assistant") and isinstance(body, str) and body.strip():
            items.append({"who": who, "body": body})
    return items


def load_session() -> str:
    try:
        value = SESSION_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return value


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def session_missing(text: str) -> bool:
    lowered = text.lower()
    return "session" in lowered and any(
        phrase in lowered for phrase in ("not found", "does not exist", "no such", "unknown session")
    )


class ChatModel(QAbstractListModel):
    WhoRole = Qt.ItemDataRole.UserRole + 1
    TextRole = Qt.ItemDataRole.UserRole + 2

    def __init__(self, items=None):
        super().__init__()
        self._items = list(items or [])

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        if role == self.WhoRole:
            return item["who"]
        if role == self.TextRole:
            return item["body"]
        return None

    def roleNames(self):
        return {self.WhoRole: b"who", self.TextRole: b"body"}

    def append(self, who: str, body: str) -> None:
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append({"who": who, "body": body})
        self.endInsertRows()

    def update_at(self, row: int, body: str) -> None:
        if not (0 <= row < len(self._items)):
            return
        self._items[row]["body"] = body
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [self.TextRole])

    def remove_at(self, row: int) -> None:
        if not (0 <= row < len(self._items)):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        self._items.pop(row)
        self.endRemoveRows()

    def snapshot(self) -> list[dict]:
        return [
            {"who": item["who"], "body": item["body"]}
            for item in self._items
            if item["body"].strip()
        ]

    def clear(self) -> None:
        if not self._items:
            return
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()


def _autostart_text(hidden: bool) -> str:
    icon = ICON_PATH if ICON_PATH.is_file() else APP_DIR / "grok-corner.png"
    return desktop_entry(
        exec_path=APP_DIR / "grok-corner",
        work_path=Path.home(),
        icon=icon,
        autostart=True,
        hidden=hidden,
    )


# grok-4.7 fills this window, then compacts around 80%.
CONTEXT_WINDOW = 256_000
# Steps in one reply swing by about 15 points. Compaction falls much further.
CONTEXT_DIP = 30


def context_percent(tokens: int) -> int:
    if tokens < 0:
        return -1
    return (tokens * 100 + CONTEXT_WINDOW // 2) // CONTEXT_WINDOW


def next_context_percent(current: int, tokens: int) -> int:
    percent = context_percent(tokens)
    if current < 0 or percent >= current or percent + CONTEXT_DIP <= current:
        return percent
    return current


class Corner(QObject):
    busyChanged = Signal()
    activityChanged = Signal()
    contextPercentChanged = Signal()
    bumped = Signal()
    signedInChanged = Signal()
    autostartChanged = Signal()
    signingInChanged = Signal()

    def __init__(self):
        super().__init__()
        self._model = ChatModel(load_transcript())
        self._busy = False
        self._activity = ""
        self._context_percent = -1
        self._signed_in = False
        self._autostart = False
        self._signing_in = False
        self._login_proc = None
        self._queue = []
        self._proc = None
        self._parser = StreamParser()
        self._session = load_session()
        self._stderr = ""
        self._assistant = ""
        self._assistant_row = None
        self._prompt = ""
        self._used_resume = False
        self._retried = False
        self._closed = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._persist)
        self._auth_watch = QFileSystemWatcher(self)
        auth_dir = AUTH_PATH.parent
        if auth_dir.is_dir():
            self._auth_watch.addPath(str(auth_dir))
        if AUTH_PATH.is_file():
            self._auth_watch.addPath(str(AUTH_PATH))
        self._auth_watch.fileChanged.connect(self._on_auth_changed)
        self._auth_watch.directoryChanged.connect(self._on_auth_changed)
        self.refresh()

    def _on_auth_changed(self, _path: str) -> None:
        if AUTH_PATH.is_file() and str(AUTH_PATH) not in self._auth_watch.files():
            self._auth_watch.addPath(str(AUTH_PATH))
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        self._set_signed_in(account_signed_in(_read_json(AUTH_PATH)))
        try:
            text = AUTOSTART_PATH.read_text(encoding="utf-8")
        except OSError:
            text = ""
        self._set_autostart(autostart_enabled(text))

    def _set_signed_in(self, value: bool) -> None:
        if self._signed_in == value:
            return
        self._signed_in = value
        self.signedInChanged.emit()

    def _get_signed_in(self):
        return self._signed_in

    signedIn = Property(bool, _get_signed_in, notify=signedInChanged)

    def _set_autostart(self, value: bool) -> None:
        if self._autostart == value:
            return
        self._autostart = value
        self.autostartChanged.emit()

    def _get_autostart(self):
        return self._autostart

    autostart = Property(bool, _get_autostart, notify=autostartChanged)

    def _set_signing_in(self, value: bool) -> None:
        if self._signing_in == value:
            return
        self._signing_in = value
        self.signingInChanged.emit()

    def _get_signing_in(self):
        return self._signing_in

    signingIn = Property(bool, _get_signing_in, notify=signingInChanged)

    def _grok_process(self) -> QProcess:
        proc = QProcess(self)
        proc.setWorkingDirectory(CWD)
        env = QProcessEnvironment.systemEnvironment()
        env.remove("QT_WAYLAND_SHELL_INTEGRATION")
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        return proc

    @Slot()
    def login(self) -> None:
        if self._login_proc is not None and self._login_proc.state() != QProcess.ProcessState.NotRunning:
            return
        proc = self._grok_process()
        proc.finished.connect(self._login_finished)
        proc.readyRead.connect(lambda: log(bytes(proc.readAll()).decode("utf-8", "replace").rstrip()))
        self._login_proc = proc
        self._set_signing_in(True)
        log("login started")
        proc.start(GROK, ["login"])

    def _login_finished(self, code, _status) -> None:
        log(f"login finished {code}")
        self._set_signing_in(False)
        self.refresh()

    @Slot()
    def logout(self) -> None:
        proc = self._grok_process()
        proc.finished.connect(lambda code, status: self._logout_finished(proc, code))
        log("logout started")
        proc.start(GROK, ["logout"])

    def _logout_finished(self, proc: QProcess, code: int) -> None:
        tail = bytes(proc.readAll()).decode("utf-8", "replace").strip()
        if tail:
            log(tail.splitlines()[-1])
        log(f"logout finished {code}")
        proc.deleteLater()
        self.refresh()

    @Slot(bool)
    def setAutostart(self, enabled: bool) -> None:
        try:
            AUTOSTART_PATH.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART_PATH.write_text(_autostart_text(hidden=not enabled), encoding="utf-8")
        except OSError as exc:
            log(f"autostart write failed: {exc}")
            return
        self.refresh()

    @Property(QObject, constant=True)
    def messages(self):
        return self._model

    def _get_busy(self):
        return self._busy

    def _set_busy(self, value: bool) -> None:
        if self._busy == value:
            return
        self._busy = value
        self.busyChanged.emit()

    busy = Property(bool, _get_busy, notify=busyChanged)

    def _get_activity(self):
        return self._activity

    def _set_activity(self, value: str) -> None:
        if self._activity == value:
            return
        self._activity = value
        self.activityChanged.emit()

    activity = Property(str, _get_activity, notify=activityChanged)

    def _get_context_percent(self):
        return self._context_percent

    def _set_context_percent(self, value: int) -> None:
        if self._context_percent == value:
            return
        self._context_percent = value
        self.contextPercentChanged.emit()

    contextPercent = Property(int, _get_context_percent, notify=contextPercentChanged)

    @Slot(str)
    def send(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._model.append("user", text)
        self._persist()
        self.bumped.emit()
        self._queue.append(text)
        self._pump()

    def _pump(self) -> None:
        if self._busy or not self._queue:
            return
        self._start(self._queue.pop(0))

    def _start(self, prompt: str) -> None:
        self._set_busy(True)
        self._set_activity("Thinking")
        self._prompt = prompt
        self._assistant = ""
        self._stderr = ""
        self._closed = False
        self._parser = StreamParser()
        self._used_resume = bool(self._session)
        self._model.append("assistant", "")
        self._assistant_row = self._model.rowCount() - 1
        self.bumped.emit()

        proc = QProcess(self)
        proc.setWorkingDirectory(CWD)
        env = QProcessEnvironment.systemEnvironment()
        env.remove("QT_WAYLAND_SHELL_INTEGRATION")
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.readyReadStandardError.connect(self._on_stderr)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        args = [
            "-p", prompt,
            "--output-format", "streaming-json",
            "--yolo",
            "--cwd", CWD,
        ]
        if self._session:
            args = ["-r", self._session, *args]
        log("start " + " ".join(args[:6]))
        self._proc = proc
        proc.start(GROK, args)

    def _on_stdout(self) -> None:
        if self._proc is None:
            return
        chunk = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        for event in self._parser.feed(chunk):
            self._apply(event)

    def _on_stderr(self) -> None:
        if self._proc is None:
            return
        chunk = bytes(self._proc.readAllStandardError()).decode("utf-8", "replace")
        self._stderr = (self._stderr + chunk)[-8000:]

    def _apply(self, event: dict) -> None:
        kind = event["kind"]
        if kind == "text":
            self._assistant += event["data"]
            self._set_assistant_body(self._assistant)
            self._set_activity("Replying")
        elif kind == "status":
            self._set_activity(event["data"])
        elif kind == "error":
            self._append_note(event["data"])
        elif kind == "context":
            self._set_context_percent(next_context_percent(self._context_percent, event["tokens"]))
        elif kind == "end" and event.get("session_id"):
            self._session = event["session_id"]
            _atomic_write(SESSION_PATH, self._session + "\n")

    def _append_note(self, note: str) -> None:
        note = note.strip()
        if not note:
            return
        combined = f"{self._assistant}\n\n{note}".strip() if self._assistant else note
        self._assistant = combined
        self._set_assistant_body(combined)

    def _on_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._finish_turn(f"Couldn't start Grok ({self._proc.errorString() if self._proc else 'missing'})")

    def _on_finished(self, code, _status) -> None:
        if code == 0:
            self._finish_turn("")
            return
        detail = self._stderr.strip().splitlines()
        tail = detail[-1] if detail else f"Grok exited {code}"
        self._finish_turn(tail)

    def _finish_turn(self, err: str) -> None:
        if self._closed:
            return
        self._closed = True
        if self._proc is not None:
            self._proc.deleteLater()
            self._proc = None
        if err and self._used_resume and not self._retried and session_missing(err):
            log(f"session missing, starting fresh: {err}")
            self._session = ""
            try:
                SESSION_PATH.unlink()
            except OSError:
                pass
            self._retried = True
            row = self._assistant_row
            self._assistant_row = None
            if row is not None:
                self._model.remove_at(row)
            self._set_busy(False)
            self._queue.insert(0, self._prompt)
            self._pump()
            return
        self._retried = False
        if err:
            self._append_note(err)
        elif not self._assistant.strip():
            self._set_assistant_body("No reply.")
        self._assistant_row = None
        self._set_busy(False)
        self._set_activity("Stopped" if err else "")
        self._persist()
        self.bumped.emit()
        self._pump()

    def _set_assistant_body(self, body: str) -> None:
        if self._assistant_row is None:
            return
        self._model.update_at(self._assistant_row, body)
        self._save_timer.start()
        self.bumped.emit()

    def _persist(self) -> None:
        _atomic_write(TRANSCRIPT_PATH, json.dumps(self._model.snapshot(), ensure_ascii=False, indent=2))

    def _drop_turn(self) -> None:
        proc = self._proc
        self._proc = None
        self._assistant_row = None
        self._assistant = ""
        self._prompt = ""
        self._stderr = ""
        self._parser = StreamParser()
        self._retried = False
        self._closed = True
        self._queue.clear()
        if proc is None:
            return
        for signal, slot in (
            (proc.readyReadStandardOutput, self._on_stdout),
            (proc.readyReadStandardError, self._on_stderr),
            (proc.finished, self._on_finished),
            (proc.errorOccurred, self._on_error),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        proc.kill()
        proc.deleteLater()

    @Slot()
    def new_chat(self) -> None:
        # Drop the resumed session. The next message starts with an empty context.
        self._drop_turn()
        self._session = ""
        try:
            SESSION_PATH.unlink()
        except OSError:
            pass
        self._model.clear()
        self._set_busy(False)
        self._set_activity("")
        self._set_context_percent(-1)
        self._persist()
        self.bumped.emit()
        log("chat refreshed")

    @Slot()
    def quit(self) -> None:
        if self._proc is not None:
            self._proc.kill()
        QGuiApplication.quit()


def _lock() -> object:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("already running")
        print("Grok Corner is already running.", file=sys.stderr)
        sys.exit(0)
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def _qt_message(_mode, _context, message):
    log(message)


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    os.environ.setdefault("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    lock = _lock()
    qInstallMessageHandler(_qt_message)
    QQuickWindow.setDefaultAlphaBuffer(True)
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Grok Corner")
    app.setDesktopFileName("grok-corner")
    corner = Corner()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("corner", corner)
    engine.rootContext().setContextProperty("startExpanded", os.environ.get("GROK_CORNER_EXPAND") == "1")
    qml = Path(__file__).with_name("Corner.qml")
    engine.load(QUrl.fromLocalFile(str(qml)))
    roots = engine.rootObjects()
    if not roots:
        log("qml failed to load")
        sys.exit(1)
    for obj in roots:
        show = getattr(obj, "show", None)
        if callable(show):
            show()
    log(f"up pid={os.getpid()} session={corner._session or 'new'}")
    code = app.exec()
    del lock
    sys.exit(code)


if __name__ == "__main__":
    main()
