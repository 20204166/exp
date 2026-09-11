"""Headless presentation tests for the Diagnostics page."""

import unittest
from unittest.mock import Mock

from maintenance.diagnostics import (
    ClusterDiagnostic,
    DiagnosticsSnapshot,
    PlacementDiagnostic,
    RenderDiagnostic,
)
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
            **recorder.page_kwargs(),
        )
        return page, callbacks, copy_callback, recorder

    def test_empty_state_messages_are_visible(self) -> None:
        _page, _callbacks, _copy_callback, recorder = self.make_page()
        texts = recorder.label_texts()
        self.assertIn("No recent failures", texts)
        self.assertIn("Nothing currently running", texts)
        self.assertIn("No remote nodes configured", texts)
        self.assertIn("No placement decision yet", texts)

    def test_placement_row_is_visible(self) -> None:
        page, _callbacks, _copy_callback, recorder = self.make_page()
        page.render(
            DiagnosticsSnapshot(
                components=(),
                operations=(),
                nodes=(),
                render=RenderDiagnostic(0, 0, 0, 0, 0),
                placement=PlacementDiagnostic("placement", "worker-a", 2, "selected"),
            )
        )
        texts = recorder.label_texts()
        self.assertIn("placement", texts)
        self.assertIn("worker-a · 2 eligible · selected", texts)

    def test_cluster_history_row_is_labeled_as_logical_bytes(self) -> None:
        page, _callbacks, _copy_callback, recorder = self.make_page()
        page.render(
            DiagnosticsSnapshot(
                components=(),
                operations=(),
                nodes=(),
                render=RenderDiagnostic(0, 0, 0, 0, 0),
                cluster=ClusterDiagnostic(
                    "coordinator", "coord", 2, 1.0, 10, 20, 0, 256,
                    "normal", 100.0, False, None,
                ),
            )
        )
        texts = recorder.label_texts()
        self.assertIn("History (logical bytes)", texts)
        self.assertIn("10 / 20 bytes", texts)

    def test_copy_callback_receives_serialized_snapshot(self) -> None:
        page, _callbacks, copy_callback, _recorder = self.make_page()
        page.copy_button.kwargs["command"]()
        copy_callback.assert_called_once()
        self.assertIn("components", copy_callback.call_args.args[0])

    def test_refresh_reuses_existing_row_widgets(self) -> None:
        page, _callbacks, _copy_callback, recorder = self.make_page()
        frame_count = len(recorder.widgets("frame"))

        page.render(empty_snapshot())

        self.assertEqual(len(recorder.widgets("frame")), frame_count)


if __name__ == "__main__":
    unittest.main()
