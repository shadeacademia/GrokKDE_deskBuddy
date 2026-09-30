import unittest

from stream import StreamParser


class StreamParserTest(unittest.TestCase):
    def test_text_tool_and_end(self):
        raw = "\n".join([
            '{"type":"thought","data":"hidden"}',
            '{"type":"tool_call","toolCallId":"c1","title":"Read","toolName":"read_file","status":"in_progress"}',
            '{"type":"text","data":"Done."}',
            '{"type":"end","sessionId":"abc-123","stopReason":"end_turn"}',
        ]) + "\n"
        events = StreamParser().feed(raw)
        self.assertEqual(events, [
            {"kind": "status", "data": "Thinking"},
            {"kind": "status", "data": "Read"},
            {"kind": "text", "data": "Done."},
            {"kind": "end", "session_id": "abc-123"},
        ])

    def test_partial_line_is_buffered(self):
        parser = StreamParser()
        self.assertEqual(parser.feed('{"type":"text","data":"hel'), [])
        self.assertEqual(parser.feed('lo"}\n'), [{"kind": "text", "data": "hello"}])

    def test_invalid_json_is_skipped(self):
        events = StreamParser().feed('not json\n{"type":"error","message":"nope"}\n')
        self.assertEqual(events, [{"kind": "error", "data": "nope"}])

    def test_tool_without_title_uses_name(self):
        events = StreamParser().feed('{"type":"tool_call","toolName":"bash"}\n')
        self.assertEqual(events, [{"kind": "status", "data": "bash"}])

    def test_thought_is_thinking_not_the_thought_text(self):
        events = StreamParser().feed('{"type":"thought","data":"secret reasoning"}\n')
        self.assertEqual(events, [{"kind": "status", "data": "Thinking"}])

    def test_finished_tool_returns_to_thinking(self):
        events = StreamParser().feed('{"type":"tool_call_update","status":"completed"}\n')
        self.assertEqual(events, [{"kind": "status", "data": "Thinking"}])

    def test_usage_counts_the_full_prompt(self):
        raw = (
            '{"type":"usage","usage":{"input_tokens":10000,'
            '"cache_read_input_tokens":36080,"cache_creation_input_tokens":0,'
            '"output_tokens":40}}\n'
        )
        self.assertEqual(StreamParser().feed(raw), [{"kind": "context", "tokens": 46080}])

    def test_usage_accepts_camel_case(self):
        raw = '{"type":"usage","usage":{"inputTokens":8000,"cacheReadInputTokens":2000}}\n'
        self.assertEqual(StreamParser().feed(raw), [{"kind": "context", "tokens": 10000}])

    def test_end_usage_is_not_a_context_reading(self):
        raw = '{"type":"end","sessionId":"abc","usage":{"input_tokens":999999}}\n'
        self.assertEqual(
            StreamParser().feed(raw),
            [{"kind": "end", "session_id": "abc"}],
        )


class QueuedLineTest(unittest.TestCase):
    def test_streaming_reply_does_not_replace_a_queued_user_line(self):
        from PySide6.QtGui import QGuiApplication

        from main import ChatModel, Corner

        QGuiApplication.instance() or QGuiApplication([])
        corner = Corner()
        corner._persist = lambda: None
        corner._model = ChatModel()
        corner._busy = True
        corner._model.append("user", "where did we leave our desktop grok project?")
        corner._model.append("assistant", "")
        corner._assistant_row = 1
        corner._assistant = "partial"
        corner.send("the KDE overlay that this chat is in..(for context)")
        corner._apply({"kind": "text", "data": " answer"})
        items = corner._model._items
        self.assertEqual(items[1], {"who": "assistant", "body": "partial answer"})
        self.assertEqual(
            items[2],
            {"who": "user", "body": "the KDE overlay that this chat is in..(for context)"},
        )

    def test_refresh_chat_drops_the_session_and_transcript(self):
        import json
        import tempfile
        from pathlib import Path

        import main
        from PySide6.QtGui import QGuiApplication

        from main import Corner

        QGuiApplication.instance() or QGuiApplication([])
        tmp = Path(tempfile.mkdtemp())
        saved = (main.RUNTIME, main.SESSION_PATH, main.TRANSCRIPT_PATH, main.LOG_PATH)
        main.RUNTIME = tmp
        main.SESSION_PATH = tmp / "session"
        main.TRANSCRIPT_PATH = tmp / "transcript.json"
        main.LOG_PATH = tmp / "log"
        try:
            corner = Corner()
            corner._session = "old-session"
            main.SESSION_PATH.write_text("old-session\n", encoding="utf-8")
            corner._model.append("user", "hello")
            corner._model.append("assistant", "hi")
            corner._queue.append("still queued")
            corner._set_context_percent(18)
            corner.new_chat()
            self.assertEqual(corner.contextPercent, -1)
            self.assertEqual(corner._session, "")
            self.assertEqual(corner._queue, [])
            self.assertEqual(corner._model._items, [])
            self.assertFalse(main.SESSION_PATH.exists())
            self.assertEqual(json.loads(main.TRANSCRIPT_PATH.read_text(encoding="utf-8")), [])
        finally:
            main.RUNTIME, main.SESSION_PATH, main.TRANSCRIPT_PATH, main.LOG_PATH = saved

    def test_status_shows_thinking_then_replying(self):
        from PySide6.QtGui import QGuiApplication

        from main import ChatModel, Corner

        QGuiApplication.instance() or QGuiApplication([])
        corner = Corner()
        corner._persist = lambda: None
        corner._model = ChatModel([{"who": "assistant", "body": ""}])
        corner._assistant_row = 0
        corner._apply({"kind": "status", "data": "Thinking"})
        self.assertEqual(corner.activity, "Thinking")
        corner._apply({"kind": "text", "data": "Hi"})
        self.assertEqual(corner.activity, "Replying")
        self.assertEqual(corner._model._items[0]["body"], "Hi")

    def test_prompt_tokens_become_a_percent_of_the_window(self):
        from PySide6.QtGui import QGuiApplication

        from main import Corner

        QGuiApplication.instance() or QGuiApplication([])
        corner = Corner()
        corner._persist = lambda: None
        self.assertEqual(corner.contextPercent, -1)
        corner._apply({"kind": "context", "tokens": 46080})
        self.assertEqual(corner.contextPercent, 18)
        corner._apply({"kind": "context", "tokens": 179200})
        self.assertEqual(corner.contextPercent, 70)
        corner._apply({"kind": "context", "tokens": 207050})
        self.assertEqual(corner.contextPercent, 81)

    def test_small_dip_keeps_the_higher_reading(self):
        from PySide6.QtGui import QGuiApplication

        from main import Corner

        QGuiApplication.instance() or QGuiApplication([])
        corner = Corner()
        corner._persist = lambda: None
        corner._apply({"kind": "context", "tokens": 130560})
        self.assertEqual(corner.contextPercent, 51)
        corner._apply({"kind": "context", "tokens": 122880})
        self.assertEqual(corner.contextPercent, 51)
        corner._apply({"kind": "context", "tokens": 148480})
        self.assertEqual(corner.contextPercent, 58)

    def test_large_drop_is_a_real_shrink(self):
        from PySide6.QtGui import QGuiApplication

        from main import Corner

        QGuiApplication.instance() or QGuiApplication([])
        corner = Corner()
        corner._persist = lambda: None
        corner._apply({"kind": "context", "tokens": 207050})
        corner._apply({"kind": "context", "tokens": 20480})
        self.assertEqual(corner.contextPercent, 8)


if __name__ == "__main__":
    unittest.main()
