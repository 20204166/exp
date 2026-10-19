"""Behavioral tests for the standalone Qt diagnostics page."""

import json
import unittest
from dataclasses import replace
from unittest.mock import Mock

from PySide6.QtCore import Qt

from maintenance.diagnostics import (
    ClusterDiagnostic,
    ComponentDiagnostic,
    DiagnosticsSnapshot,
    NodeDiagnostic,
    OperationDiagnostic,
    PlacementDiagnostic,
    RenderDiagnostic,
    serialize_diagnostics,
)
from maintenance.observability import ObservabilityWatcher
from maintenance.ui.qt_diagnostics_page import QtDiagnosticsPage
from tests.support.qt import get_qapplication


def empty_snapshot() -> DiagnosticsSnapshot:
    return DiagnosticsSnapshot((), (), (), RenderDiagnostic(0, 0, 0, 0, 0))


def live_snapshot() -> DiagnosticsSnapshot:
    return DiagnosticsSnapshot(
        components=(
            ComponentDiagnostic(
                "cpu", "in_flight", "supported", True, 12.5, None, None
            ),
            ComponentDiagnostic(
                "storage",
                "failed",
                "supported",
                False,
                None,
                "read",
                "disk unavailable",
            ),
        ),
        operations=(OperationDiagnostic("scan", 7, True, False, None, None),),
        nodes=(
            NodeDiagnostic(
                "node-a", "Worker A", "trusted", "paired", "online", None, ()
            ),
        ),
        render=RenderDiagnostic(3, 9, 6, 2, 1),
        most_recent_failure="storage: disk unavailable",
        placement=PlacementDiagnostic("placement", "worker-a", 2, "selected"),
        cluster=ClusterDiagnostic(
            "coordinator", "coord", 2, 1.0, 10, 20, 0, 256, "normal", 100.0, False
        ),
        observability=_observability_snapshot(),
    )


def _observability_snapshot():
    observer = ObservabilityWatcher()
    observer.record("app:scan", 0.25)
    observer.record_event("app:scan", "coalesced")
    return observer.snapshot()


class QtDiagnosticsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def test_empty_snapshot_has_explicit_empty_states_and_no_cluster(self) -> None:
        page = QtDiagnosticsPage(empty_snapshot(), on_back=Mock(), on_copy=Mock())
        page.show()
        self.app.processEvents()
        rendered = " ".join(
            label.text() for label in page.findChildren(type(page.title_label))
        )
        self.assertIn("No data yet", rendered)
        self.assertIn("No placement decision yet", rendered)
        self.assertIn("No cluster configured", rendered)
        self.assertIn("Nothing currently running", rendered)
        page.close()

    def test_live_snapshot_renders_partial_rows_status_and_metrics(self) -> None:
        page = QtDiagnosticsPage(live_snapshot(), on_back=Mock(), on_copy=Mock())
        text = " ".join(
            label.text() for label in page.findChildren(type(page.title_label))
        )
        for value in (
            "disk unavailable",
            "3 pending",
            "worker-a",
            "History (logical bytes)",
            "app:scan",
        ):
            self.assertIn(value, text)
        self.assertEqual(page.value_colors["cpu"], page.colors["warning"])
        self.assertEqual(page.value_colors["storage"], page.colors["danger"])
        page.close()

    def test_copy_serializes_current_snapshot_and_calls_once(self) -> None:
        copied = Mock()
        snapshot = live_snapshot()
        page = QtDiagnosticsPage(snapshot, on_back=Mock(), on_copy=copied)
        page.copy_button.click()
        copied.assert_called_once_with(serialize_diagnostics(snapshot))
        self.assertEqual(json.loads(copied.call_args.args[0])["render"]["pending"], 3)
        page.close()

    def test_capture_success_failure_and_exception_keep_explanation(self) -> None:
        save = Mock(return_value="capture.json")
        page = QtDiagnosticsPage(
            empty_snapshot(),
            on_back=Mock(),
            on_copy=Mock(),
            on_save_capture=save,
            developer_mode_visible=True,
        )
        page.save_capture_button.click()
        self.assertIn("Saved: capture.json", page.capture_status.text())
        save.return_value = None
        page.save_capture_button.click()
        self.assertIn("could not be saved", page.capture_status.text())
        save.side_effect = OSError("permission denied")
        page.save_capture_button.click()
        self.assertIn("permission denied", page.capture_status.text())
        page.close()

    def test_developer_visibility_is_explicit_and_back_focus_is_available(self) -> None:
        back = Mock()
        page = QtDiagnosticsPage(
            empty_snapshot(), on_back=back, on_copy=Mock(), on_save_capture=Mock()
        )
        self.assertFalse(page.save_capture_button.isVisible())
        page.show()
        page.activateWindow()
        page.focus_back()
        self.app.processEvents()
        self.assertEqual(self.app.focusWidget(), page.back_button)
        page.back_button.click()
        back.assert_called_once_with()
        page.close()

        visible_page = QtDiagnosticsPage(
            empty_snapshot(),
            on_back=Mock(),
            on_copy=Mock(),
            on_save_capture=Mock(return_value="capture.json"),
            developer_mode_visible=True,
        )
        visible_page.show()
        self.app.processEvents()
        self.assertTrue(visible_page.save_capture_button.isVisible())
        visible_page.close()

    def test_dense_values_have_accessible_names_and_selectable_text(self) -> None:
        page = QtDiagnosticsPage(live_snapshot(), on_back=Mock(), on_copy=Mock())
        value = page.value_labels["storage"]
        self.assertEqual(value.accessibleName(), "storage diagnostic value")
        self.assertTrue(
            value.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        )
        page.close()

    def test_scrollable_wrapping_at_migration_widths(self) -> None:
        page = QtDiagnosticsPage(live_snapshot(), on_back=Mock(), on_copy=Mock())
        for width in (900, 1280, 1600):
            page.resize(width, 500)
            page.show()
            self.app.processEvents()
            self.assertGreaterEqual(page.width(), width - 10)
        self.assertTrue(page.scroll_area.widgetResizable())
        page.close()

    def test_render_refresh_reuses_rows_and_replaces_snapshot(self) -> None:
        page = QtDiagnosticsPage(live_snapshot(), on_back=Mock(), on_copy=Mock())
        value = page.value_labels["cpu"]
        refreshed = replace(live_snapshot(), render=RenderDiagnostic(0, 10, 10, 2, 1))
        page.render(refreshed)
        self.assertIs(page.value_labels["cpu"], value)
        self.assertEqual(page._snapshot, refreshed)
        page.close()

    def test_render_can_move_between_empty_and_populated_sections(self) -> None:
        page = QtDiagnosticsPage(empty_snapshot(), on_back=Mock(), on_copy=Mock())
        page.render(live_snapshot())
        self.assertEqual(page.value_labels["cpu"].text().split(" · ")[0], "in_flight")
        page.render(empty_snapshot())
        self.assertIn(
            "No data yet",
            [label.text() for label in page.findChildren(type(page.title_label))],
        )
        page.close()


if __name__ == "__main__":
    unittest.main()
