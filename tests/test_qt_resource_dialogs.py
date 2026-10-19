"""Focused behavioral tests for the isolated Qt resource dialogs."""

import getpass
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QLabel, QScrollArea

from maintenance.models import FileCandidate, ProcessCandidate, ResourceSummary
from maintenance.ui.qt_resource_dialogs import (
    QtInfoDialog,
    QtProcessDialog,
    QtStorageDialog,
)
from tests.support.qt import get_qapplication


def process(
    pid: int, name: str, *, allowed: bool = True, cpu: float = 1.0
) -> ProcessCandidate:
    return ProcessCandidate(
        pid=pid,
        name=name,
        memory_bytes=pid * 1024,
        memory_percent=1.0,
        cpu_percent=cpu,
        activity="Active" if cpu >= 1 else "Low activity",
        username=getpass.getuser(),
        action_allowed=allowed,
        create_time=float(pid),
    )


def file_candidate(path: str, *, size: int = 10) -> FileCandidate:
    return FileCandidate(
        Path(path), size, datetime(2026, 10, 18, tzinfo=timezone.utc), "Large file"
    )


class QtResourceDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def test_info_dialog_uses_summary_and_close_callback_once(self) -> None:
        closed: list[bool] = []
        summary = ResourceSummary(
            "gpu",
            "GPU",
            "Radeon",
            "Graphics hardware",
            None,
            (
                "AMD hardware with an unusually long identifier " + "X" * 90,
                "Temperature: 56°C",
            ),
        )
        dialog = QtInfoDialog(summary, on_close=lambda: closed.append(True), colors={})
        self.assertIsInstance(dialog, QDialog)
        self.assertIsInstance(dialog.details_scroll, QScrollArea)
        self.assertEqual(dialog.windowTitle(), "GPU Details")
        self.assertIn(
            "Hardware", [label.text() for label in dialog.findChildren(QLabel)]
        )
        dialog.open()
        dialog.reject()
        dialog.close()
        self.assertEqual(closed, [True])

    def test_process_filter_sort_protection_and_normal_confirmation(self) -> None:
        refreshed: list[bool] = []
        quit_calls: list[tuple[list[int], dict[int, float]]] = []
        closed: list[bool] = []
        dialog = QtProcessDialog(
            resource_key="cpu",
            node_title="Local",
            read_only=False,
            on_refresh=lambda: refreshed.append(True),
            on_quit=lambda pids, times: quit_calls.append((pids, times)),
            on_force_quit=lambda pids, times: None,
            on_close=lambda: closed.append(True),
            colors={},
        )
        dialog.update_candidates(
            [
                process(20, "zeta"),
                process(10, "Alpha"),
                process(1, "system", allowed=False),
            ]
        )
        dialog.search_edit.setText("ALP")
        self.assertEqual(dialog.table.rowCount(), 1)
        dialog.search_edit.clear()
        self.assertEqual(dialog.status_label.text(), "3 shown • 2 available for review")
        self.assertFalse(dialog.select_candidate(1))
        self.assertTrue(dialog.select_candidate(10))
        with patch.object(dialog, "_confirm", return_value=True):
            dialog.quit_selected()
        self.assertEqual(quit_calls, [([10], {10: 10.0})])
        self.assertEqual(refreshed, [])
        dialog.close()
        self.assertEqual(closed, [True])

    def test_process_sort_is_numeric_and_selected_candidates_follow_visible_order(
        self,
    ) -> None:
        dialog = QtProcessDialog(
            resource_key="cpu",
            node_title="Local",
            read_only=False,
            on_refresh=lambda: None,
            on_quit=lambda *_: None,
            on_force_quit=lambda *_: None,
            on_close=lambda: None,
            colors={},
        )
        dialog.update_candidates([process(99, "Zulu"), process(2, "Alpha")])
        dialog.sort_by(1)
        dialog.sort_by(1)
        ids = [dialog.table.item(row, 1) for row in range(2)]
        self.assertTrue(all(item is not None for item in ids))
        self.assertEqual([item.text() for item in ids if item is not None], ["2", "99"])
        dialog.set_selected_pids([99, 2])
        self.assertEqual(
            [candidate.pid for candidate in dialog.selected_candidates()], [2, 99]
        )
        dialog.close()

    def test_process_unknown_and_read_only_states_block_action(self) -> None:
        calls: list[bool] = []
        dialog = QtProcessDialog(
            resource_key="memory",
            node_title="Remote",
            read_only=True,
            on_refresh=lambda: None,
            on_quit=lambda *_: calls.append(True),
            on_force_quit=lambda *_: calls.append(True),
            on_close=lambda: None,
            colors={},
        )
        dialog.update_candidates([process(5, "App")])
        self.assertFalse(dialog.quit_button.isEnabled())
        dialog.set_action_state(busy=True)
        self.assertIn("in progress", dialog.status_label.text().lower())
        dialog.set_action_state(unknown=True)
        self.assertIn("unknown", dialog.status_label.text().lower())
        dialog.quit_selected()
        self.assertEqual(calls, [])
        dialog.close()

    def test_process_action_result_remains_visible_after_unlock(self) -> None:
        dialog = QtProcessDialog(
            resource_key="cpu",
            node_title="Local",
            read_only=False,
            on_refresh=lambda: None,
            on_quit=lambda *_: None,
            on_force_quit=lambda *_: None,
            on_close=lambda: None,
            colors={},
        )
        dialog.update_candidates([process(5, "App")])
        dialog.set_action_state(busy=True)
        dialog.set_action_result("Stopped 1 process.")
        self.assertEqual(dialog.status_label.text(), "Stopped 1 process.")
        self.assertTrue(dialog.quit_button.isEnabled())
        dialog.close()

    def test_force_escalation_requires_distinct_confirmation(self) -> None:
        force: list[tuple[list[int], dict[int, float]]] = []
        dialog = QtProcessDialog(
            resource_key="cpu",
            node_title="Local",
            read_only=False,
            on_refresh=lambda: None,
            on_quit=lambda *_: None,
            on_force_quit=lambda pids, times: force.append((pids, times)),
            on_close=lambda: None,
            colors={},
        )
        dialog.update_candidates([process(10, "App")])
        dialog.set_selected_pids([10])
        with patch.object(dialog, "_confirm_force", return_value=False):
            dialog.request_force_quit([10])
        self.assertEqual(force, [])
        with patch.object(dialog, "_confirm_force", return_value=True):
            dialog.request_force_quit([10])
        self.assertEqual(force, [([10], {10: 10.0})])
        dialog.close()

    def test_storage_confirmation_read_only_progress_and_cancel(self) -> None:
        moved: list[list[FileCandidate]] = []
        cancelled: list[bool] = []
        dialog = QtStorageDialog(
            node_title="Remote",
            read_only=True,
            scan_root_label="Downloads",
            on_scan=lambda: None,
            on_cancel_scan=lambda: cancelled.append(True),
            on_move_selected=moved.append,
            on_close=lambda: None,
            colors={},
        )
        candidate = file_candidate("/downloads/" + "a" * 100 + ".zip", size=2048)
        dialog.update_candidates([candidate])
        self.assertEqual(dialog.table.rowCount(), 1)
        item = dialog.table.item(0, 0)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertIn(candidate.path.name, item.text())
        self.assertFalse(dialog.move_button.isEnabled())
        dialog.set_scan_state("Scanning Downloads", busy=True, progress=40)
        self.assertTrue(dialog.cancel_button.isEnabled())
        self.assertEqual(dialog.progress_bar.value(), 40)
        dialog.cancel_button.click()
        self.assertEqual(cancelled, [True])
        self.assertFalse(dialog.cancel_button.isEnabled())
        dialog.set_scan_state("Still cancelling", busy=True, progress=45)
        self.assertFalse(dialog.cancel_button.isEnabled())
        dialog.set_scan_state("Scan cancelled", busy=False)
        self.assertFalse(dialog.cancel_button.isEnabled())
        dialog.close()

    def test_storage_move_requires_confirmation_and_sends_candidates(self) -> None:
        selected: list[list[FileCandidate]] = []
        candidate = file_candidate("/safe-looking/path.zip")
        dialog = QtStorageDialog(
            node_title="Local",
            read_only=False,
            scan_root_label="Downloads",
            on_scan=lambda: None,
            on_cancel_scan=lambda: None,
            on_move_selected=selected.append,
            on_close=lambda: None,
            colors={},
        )
        dialog.update_candidates([candidate])
        dialog.table.selectRow(0)
        with patch.object(dialog, "_confirm_move", return_value=False):
            dialog.move_selected()
        self.assertEqual(selected, [])
        with patch.object(dialog, "_confirm_move", return_value=True):
            dialog.move_selected()
        self.assertEqual(selected, [[candidate]])
        dialog.close()

    def test_dialogs_are_resizable_and_escape_close_callback_runs_once(self) -> None:
        closed: list[bool] = []
        dialog = QtStorageDialog(
            node_title="Local",
            read_only=False,
            scan_root_label="Downloads",
            on_scan=lambda: None,
            on_cancel_scan=lambda: None,
            on_move_selected=lambda _: None,
            on_close=lambda: closed.append(True),
            colors={},
        )
        for width in (900, 1280, 1600):
            dialog.resize(width, 700)
            self.app.processEvents()
            self.assertGreaterEqual(dialog.width(), width)
        dialog.open()
        dialog.setFocus()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertEqual(closed, [True])
        dialog.close()
        self.assertEqual(closed, [True])

    def test_interactive_controls_have_accessible_names_and_keyboard_focus(
        self,
    ) -> None:
        process_dialog = QtProcessDialog(
            resource_key="cpu",
            node_title="Local",
            read_only=False,
            on_refresh=lambda: None,
            on_quit=lambda *_: None,
            on_force_quit=lambda *_: None,
            on_close=lambda: None,
            colors={},
        )
        self.assertTrue(process_dialog.search_edit.accessibleName())
        self.assertTrue(
            process_dialog.search_edit.focusPolicy() & Qt.FocusPolicy.TabFocus
        )
        self.assertTrue(process_dialog.table.accessibleName())
        self.assertTrue(process_dialog.quit_button.accessibleName())
        process_dialog.close()


if __name__ == "__main__":
    unittest.main()
