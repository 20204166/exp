import unittest
from typing import Any
from unittest.mock import Mock
from queue import Queue

from window import AppWindow


class FakeMaster:
    def __init__(self) -> None:
        self.scheduled: list[tuple[object, ...]] = []
        self.cancelled: list[str] = []
        self.destroyed = False
        self.next_timer_id = 0

    def after(self, delay: int, callback: object, *args: object) -> str:
        self.scheduled.append((delay, callback, *args))
        self.next_timer_id += 1
        return f"after#{self.next_timer_id}"

    def after_cancel(self, identifier: str) -> None:
        self.cancelled.append(identifier)

    def destroy(self) -> None:
        self.destroyed = True


class FailingMaster(FakeMaster):
    def after(self, delay: int, callback: object, *args: object) -> str:
        del delay, callback, args
        raise RuntimeError("event loop is not running")


class FailingCancelMaster(FakeMaster):
    def after_cancel(self, identifier: str) -> None:
        del identifier
        raise RuntimeError("event loop is not running")


class AppWindowTests(unittest.TestCase):
    @staticmethod
    def make_window(master: FakeMaster | None = None) -> Any:
        window: Any = object.__new__(AppWindow)
        window.master = master or FakeMaster()
        window.auto_scan_id = None
        window._is_closing = False
        window._pending_after_ids = set()
        window._background_poll_id = None
        window._background_tasks = 0
        window._analysis_active = False
        window._analysis_generation = 0
        window._analysis_requested = False
        window._analysis_cancel_event = None
        window._background_queue = Queue()
        return window

    def test_output_uses_named_tk_fixed_font(self) -> None:
        self.assertEqual(AppWindow.OUTPUT_FONT, "TkFixedFont")

    def test_background_queue_delivers_payload_on_main_thread_poll(self) -> None:
        window = self.make_window()
        callback = Mock()
        window._background_tasks = 1
        window._background_queue.put((callback, ("payload",)))
        window._background_queue.put(None)

        window._drain_background_queue()

        callback.assert_called_once_with("payload")
        self.assertEqual(window._background_tasks, 0)

    def test_background_queue_ignores_late_payload_after_close(self) -> None:
        window = self.make_window()
        window._is_closing = True
        callback = Mock()
        window._background_tasks = 1
        window._background_queue.put((callback, ("payload",)))
        window._background_queue.put(None)

        window._drain_background_queue()

        callback.assert_not_called()
        self.assertEqual(window._background_tasks, 0)

    def test_unexpected_timer_failure_is_logged(self) -> None:
        window = self.make_window(FailingMaster())

        with self.assertLogs("window", level="ERROR"):
            identifier = window._schedule_timer(10, Mock())

        self.assertIsNone(identifier)

    def test_close_cancels_auto_scan_before_destroying_root(self) -> None:
        window = self.make_window()
        window.auto_scan_id = "after#1"
        window._pending_after_ids = {"after#1", "after#2"}

        window._close()

        self.assertTrue(window._is_closing)
        self.assertIsNone(window.auto_scan_id)
        self.assertEqual(
            set(window.master.cancelled),
            {"after#1", "after#2"},
        )
        self.assertTrue(window.master.destroyed)

    def test_timer_is_removed_after_callback_runs(self) -> None:
        window = self.make_window()
        callback = Mock()

        identifier = window._schedule_timer(500, callback, "payload")
        scheduled_callback = window.master.scheduled[0][1]
        scheduled_callback()

        self.assertEqual(identifier, "after#1")
        self.assertNotIn(identifier, window._pending_after_ids)
        callback.assert_called_once_with("payload")

    def test_failed_timer_cancellation_keeps_identifier_and_blocks_replacement(
        self,
    ) -> None:
        window = self.make_window(FailingCancelMaster())
        window.auto_scan_id = "after#1"
        window._pending_after_ids = {"after#1"}

        with self.assertLogs("window", level="ERROR"):
            window._schedule_auto_scan()

        self.assertEqual(window.auto_scan_id, "after#1")
        self.assertEqual(window._pending_after_ids, {"after#1"})
        self.assertEqual(window.master.scheduled, [])

    def test_auto_scan_uses_five_second_interval(self) -> None:
        window = self.make_window()

        window._schedule_auto_scan()

        self.assertEqual(
            window.master.scheduled[0][0],
            AppWindow.AUTO_SCAN_MILLISECONDS,
        )

    def test_late_snapshot_and_error_callbacks_are_ignored(self) -> None:
        window = self.make_window()
        window._is_closing = True
        window._set_busy = Mock()

        window._show_snapshot(Mock())
        window._show_error("error")

        window._set_busy.assert_not_called()

    def test_auto_scan_clears_id_before_starting_scan(self) -> None:
        window = self.make_window()
        window.auto_scan_id = "after#1"
        window.handle_analyze = Mock()

        window._run_auto_scan()

        self.assertIsNone(window.auto_scan_id)
        window.handle_analyze.assert_called_once_with()

    def test_dashboard_scan_does_not_overlap_when_requested_twice(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()

        window.handle_analyze()
        window.handle_analyze()

        window._run_in_background.assert_called_once()
        window.analyzer.dashboard_snapshot.assert_not_called()

    def test_dashboard_request_during_scan_is_replayed_after_completion(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()
        window._show_snapshot = Mock()
        window._schedule_timer = Mock()

        window.handle_analyze()
        window.handle_analyze()
        window._show_snapshot_for_generation(1, Mock())

        window._show_snapshot.assert_called_once()
        window._schedule_timer.assert_called_once_with(0, window.handle_analyze)


if __name__ == "__main__":
    unittest.main()
