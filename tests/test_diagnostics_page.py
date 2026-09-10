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
        back_callback = Mock()
        copy_callback = Mock()
        callbacks = DiagnosticsPageCallbacks(
            on_back=back_callback, on_copy=copy_callback
        )
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
        return page, callbacks, copy_callback, recorder

    def test_empty_state_messages_are_visible(self) -> None:
        _page, _callbacks, _copy_callback, recorder = self.make_page()
        texts = recorder.label_texts()
        self.assertIn("No recent failures", texts)
        self.assertIn("Nothing currently running", texts)
        self.assertIn("No remote nodes configured", texts)

    def test_copy_callback_receives_serialized_snapshot(self) -> None:
        page, _callbacks, copy_callback, _recorder = self.make_page()
        page.copy_button.kwargs["command"]()
        copy_callback.assert_called_once()
        self.assertIn("components", copy_callback.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
