"""Focused tests for toolkit-neutral dashboard scan adapters."""

from __future__ import annotations

import subprocess
import sys
import unittest
from unittest.mock import Mock

from maintenance.ui import window_scan


class WindowScanRuntimeTests(unittest.TestCase):
    def test_scan_coordinator_adapter_does_not_import_window_or_tk(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; from types import SimpleNamespace; "
                    "from maintenance.ui.window_scan import scan_coordinator_state; "
                    "controller = SimpleNamespace(__dict__={}); "
                    "scan_coordinator_state(controller); "
                    "assert 'window' not in sys.modules; "
                    "assert not any(name == 'tkinter' or name.startswith('tkinter.') "
                    "for name in sys.modules)"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cancel_notice_uses_shell_callback_without_tk_label(self) -> None:
        controller = Mock()
        controller._resolution_for_generation.return_value = False
        controller._show_scan_cancelled_notice = Mock()

        window_scan.show_error_for_generation(
            controller, 4, window_scan.DOWNLOADS_SCAN_CANCELLED
        )

        controller._show_scan_cancelled_notice.assert_called_once_with(
            window_scan.SCAN_CANCELLED_NOTICE
        )
        controller.refreshed_label.config.assert_not_called()
        controller._schedule_rerun_if_requested.assert_called_once_with(False)

    def test_cancel_notice_retains_legacy_label_fallback(self) -> None:
        controller = Mock(
            spec=[
                "_resolution_for_generation",
                "_set_busy",
                "_reset_progress_bar",
                "refreshed_label",
                "_schedule_rerun_if_requested",
                "_show_error",
            ]
        )
        controller._resolution_for_generation.return_value = True

        window_scan.show_error_for_generation(
            controller, 9, window_scan.DOWNLOADS_SCAN_CANCELLED
        )

        controller.refreshed_label.config.assert_called_once_with(
            text=window_scan.SCAN_CANCELLED_NOTICE
        )
        controller._show_error.assert_not_called()
        controller._schedule_rerun_if_requested.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
