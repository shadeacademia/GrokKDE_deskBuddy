"""Account state and desktop entries for Grok Corner."""

import os
import shutil
import subprocess
from pathlib import Path

APP_NAME = "Grok Corner"


def account_signed_in(data) -> bool:
    if not isinstance(data, dict):
        return False
    for value in data.values():
        if isinstance(value, dict) and value.get("user_id"):
            return True
    return False


def autostart_enabled(text: str) -> bool:
    if not text or not text.strip():
        return False
    for line in text.splitlines():
        if line.strip().lower() == "hidden=true":
            return False
    return True


def _exec(path: Path) -> str:
    text = str(path)
    if any(char in text for char in " \t\n"):
        return f'"{text}"'
    return text


def desktop_entry(
    *,
    exec_path: Path,
    work_path: Path,
    icon: Path,
    autostart: bool,
    hidden: bool = False,
) -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={APP_NAME}",
        "GenericName=Grok",
        "Comment=Always-on Grok in the corner",
        f"Exec={_exec(exec_path)}",
        f"Path={work_path}",
        f"Icon={icon}",
        "Terminal=false",
        "StartupNotify=false",
        "Categories=Utility;",
        "Keywords=Grok;",
        "OnlyShowIn=KDE;",
        "X-KDE-Wayland-Interfaces=zwlr_layer_shell_v1",
    ]
    if autostart:
        lines.append("X-KDE-autostart-phase=2")
        lines.append("X-KDE-StartupNotify=false")
    if hidden:
        lines.append("Hidden=true")
    return "\n".join(lines) + "\n"


def install(app_dir: Path) -> None:
    app_dir = app_dir.resolve()
    launcher = app_dir / "grok-corner"
    icon_src = app_dir / "grok-corner.png"
    if not launcher.is_file():
        raise SystemExit(f"Missing launcher: {launcher}")
    if not icon_src.is_file():
        raise SystemExit(f"Missing icon: {icon_src}")
    grok = Path.home() / ".grok" / "bin" / "grok"
    if not grok.is_file():
        raise SystemExit(f"Grok is not installed at {grok}")

    home = Path.home()
    icon_dir = home / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    icon_dir.mkdir(parents=True, exist_ok=True)
    icon_dest = icon_dir / "grok-corner.png"
    shutil.copyfile(icon_src, icon_dest)

    apps = home / ".local" / "share" / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    entry = desktop_entry(
        exec_path=launcher,
        work_path=home,
        icon=icon_dest,
        autostart=False,
    )
    (apps / "grok-corner.desktop").write_text(entry, encoding="utf-8")

    auto_dir = home / ".config" / "autostart"
    auto_dir.mkdir(parents=True, exist_ok=True)
    auto_path = auto_dir / "grok-corner.desktop"
    hidden = auto_path.exists() and not autostart_enabled(auto_path.read_text(encoding="utf-8"))
    auto_path.write_text(
        desktop_entry(
            exec_path=launcher,
            work_path=home,
            icon=icon_dest,
            autostart=True,
            hidden=hidden,
        ),
        encoding="utf-8",
    )

    bindir = home / ".local" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    link = bindir / "grok-corner"
    if link.is_symlink():
        link.unlink()
    if not link.exists():
        link.symlink_to(launcher)

    updater = shutil.which("update-desktop-database")
    if updater:
        subprocess.run([updater, str(apps)], check=False)
    cache = shutil.which("kbuildsycoca6")
    if cache and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        subprocess.run([cache, "--noincremental"], check=False)

    print(f"Launcher: {apps / 'grok-corner.desktop'}")
    print(f"Autostart: {auto_path}" + (" (off)" if hidden else " (on)"))
    print(f"Command: {link if link.is_symlink() else launcher}")
