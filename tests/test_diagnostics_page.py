"""Headless presentation tests for the Diagnostics page."""

import unittest
from unittest.mock import Mock

from maintenance.diagnostics import DiagnosticsSnapshot, RenderDiagnostic
from maintenance.ui.diagnostics_page import DiagnosticsPage, DiagnosticsPageCallbacks
from tests.support.widget_recording import WidgetRecorder


def empty_snapshot() -> DiagnosticsSnapshot:
    return DiagnosticsSnapshot(
        components=(),
        operations=(),
        nodes=(),
        render=RenderDiagnostic(0, 0, 0, 0, 0),
    )


class DiagnosticsPageTests(unittest.TestCase):
    def make_page(self):
        recorder = WidgetRecorder()
        callbacks = DiagnosticsPageCallbacks(on_back=Mock(), on_copy=Mock())
        page = DiagnosticsPage(
            recorder.parent(),
            callbacks=callbacks,
            snapshot=empty_snapshot(),
            frame_cls=recorder.frame_cls(),
            label_cls=recorder.label_cls(),
            style_frame_cls=recorder.style_frame_cls(),
            style_label_cls=recorder.style_label_cls(),
            button_cls=recorder.button_cls(),
            canvas_cls=recorder.canvas_cls(),
            scrollbar_cls=recorder.scrollbar_cls(),
        )
        return page, callbacks, recorder

    def test_empty_state_messages_are_visible(self) -> None:
        _page, _callbacks, recorder = self.make_page()
        texts = recorder.label_texts()
        self.assertIn("No recent failures", texts)
        self.assertIn("Nothing currently running", texts)
        self.assertIn("No remote nodes configured", texts)

    def test_copy_callback_receives_serialized_snapshot(self) -> None:
        page, callbacks, _recorder = self.make_page()
        page.copy_button.kwargs["command"]()
        callbacks.on_copy.assert_called_once()
        self.assertIn("components", callbacks.on_copy.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
