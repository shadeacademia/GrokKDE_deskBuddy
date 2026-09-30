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


if __name__ == "__main__":
    unittest.main()
