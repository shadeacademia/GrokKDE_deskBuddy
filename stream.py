"""Parse grok --output-format streaming-json lines into UI events."""

import json


class StreamParser:
    def __init__(self):
        self._buf = ""

    def feed(self, chunk: str) -> list[dict]:
        self._buf += chunk
        events = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            events.extend(self._line(line))
        return events

    def _line(self, line: str) -> list[dict]:
        line = line.strip()
        if not line:
            return []
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return []
        if not isinstance(obj, dict):
            return []
        kind = obj.get("type")
        if kind == "text":
            return [{"kind": "text", "data": obj.get("data") or ""}]
        if kind == "thought":
            return [{"kind": "status", "data": "Thinking"}]
        if kind == "tool_call":
            label = obj.get("title") or obj.get("toolName") or "Working"
            return [{"kind": "status", "data": str(label)}]
        if kind == "tool_call_update":
            if obj.get("status") in ("completed", "failed", "cancelled"):
                return [{"kind": "status", "data": "Thinking"}]
            return []
        if kind == "error":
            return [{"kind": "error", "data": obj.get("message") or "Grok hit an error"}]
        if kind == "end":
            session = obj.get("sessionId") or obj.get("session_id") or ""
            return [{"kind": "end", "session_id": str(session)}]
        return []
