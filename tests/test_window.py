import threading
import time
import tkinter as tk
import unittest
from typing import Any
from unittest.mock import Mock, patch

from maintenance.components import DOWNLOADS_SCAN_CANCELLED, ScanCancelled
from maintenance.components.coordinator import ComponentRefreshScheduler
from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    ResourceSummary,
)
from maintenance.nodes import NodeId
from maintenance.preferences import AppPreferences, PreferencesSaveError
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.render_coordinator import RenderIntent, UICoordinator
from tests.support.models import FIXED_SCANNED_AT, make_snapshot, make_summary
from tests.support.scheduling import FailingMaster, TimerMaster
from tests.support.widget_recording import RecordingWidget
from tests.support.window import make_window as make_bare_window
from window import AppWindow


class AppWindowTests(unittest.TestCase):
    @staticmethod
    def make_window(master: TimerMaster | None = None) -> Any:
        return make_bare_window(
            master=master,
            _preferences=AppPreferences.defaults(),
            _preferences_store=Mock(),
            _capabilities={},
            _refresh_cards_scrollbar=Mock(),
            cards_frame=Mock(),
            settings_home=Mock(),
            preferences_page=Mock(),
            analyze_button=Mock(),
            cancel_button=Mock(),
            status_label=Mock(),
            refreshed_label=Mock(),
            scan_time_label=Mock(),
            progress_bar=None,
            health_label=Mock(),
        )

    def test_show_snapshot_updates_last_refreshed_label(self) -> None:
        window = self.make_window()
        window.snapshot = None
        window.cards = {}
        window.scan_time_label = Mock()
        window.refreshed_label = Mock()
        window._set_busy = Mock()
        window._schedule_auto_scan = Mock()
        snapshot = Mock()
        snapshot.resources = []
        snapshot.scanned_at = FIXED_SCANNED_AT

        window._show_snapshot(snapshot)

        window.refreshed_label.config.assert_called_once_with(
            text="Last refreshed: 03:42:52"
        )

    def test_background_queue_delivers_payload_on_main_thread_poll(self) -> None:
        window = self.make_window()
        callback = Mock()
        window._background_tasks = 1
        window._background_queue.put((callback, ("payload",)))
        window._background_queue.put(None)

        window._drain_background_queue()

        callback.assert_called_once_with("payload")
        self.assertEqual(window._background_tasks, 0)

    def test_background_service_resolves_delivery_hook_at_dispatch_time(self) -> None:
        window = self.make_window()
        window._background_service()
        delivered = Mock()
        window._invoke_delivered = delivered
        callback = Mock()
        window._background_queue.put((callback, ("payload",)))

        window._drain_background_queue()

        delivered.assert_called_once()
        callback.assert_not_called()

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

    def test_closed_partial_window_does_not_start_analysis(self) -> None:
        window: Any = object.__new__(AppWindow)
        window._is_closing = True

        window.handle_analyze()

    def test_partial_window_without_registry_does_not_start_discovery(self) -> None:
        window: Any = object.__new__(AppWindow)
        window._is_closing = True

        window._start_discovery()

    def test_partial_window_without_coordinator_stops_discovery_timer(self) -> None:
        window: Any = object.__new__(AppWindow)
        window.master = TimerMaster()
        window._is_closing = True
        window._pending_after_ids = {"after#1"}
        window._node_registry = Mock()
        window._discovery_tick_id = "after#1"

        window._stop_discovery()

        self.assertEqual(window.master.cancelled, ["after#1"])
        self.assertIsNone(window._discovery_tick_id)

    def test_partial_window_without_registry_stops_discovery_timer(self) -> None:
        window: Any = object.__new__(AppWindow)
        window.master = TimerMaster()
        window._is_closing = True
        window._pending_after_ids = {"after#1"}
        window._discovery_tick_id = "after#1"

        window._stop_discovery()

        self.assertEqual(window.master.cancelled, ["after#1"])
        self.assertIsNone(window._discovery_tick_id)

    def test_partial_window_can_run_daemon_without_background_queue(self) -> None:
        window: Any = object.__new__(AppWindow)
        finished = threading.Event()

        window._run_daemon(
            lambda: "result",
            lambda result: self.assertEqual(result, "result"),
            self.fail,
            finished.set,
        )

        self.assertTrue(finished.wait(1))

    def test_unexpected_timer_failure_is_logged(self) -> None:
        window = self.make_window(FailingMaster())

        with self.assertLogs("window", level="ERROR"):
            identifier = window._schedule_timer(10, Mock())

        self.assertIsNone(identifier)

    def test_close_cancels_component_poll_before_destroying_root(self) -> None:
        window = self.make_window()
        window._component_poll_id = "after#1"
        window._pending_after_ids = {"after#1", "after#2"}

        window._close()

        self.assertTrue(window._is_closing)
        self.assertIsNone(window._component_poll_id)
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

    def test_component_poll_uses_one_second_interval(self) -> None:
        window = self.make_window()

        window._schedule_component_poll()

        self.assertEqual(
            window.master.scheduled[0][0],
            AppWindow.COMPONENT_POLL_MILLISECONDS,
        )

    def test_component_poll_does_not_duplicate_when_already_scheduled(self) -> None:
        window = self.make_window()
        window._component_poll_id = "after#1"

        window._schedule_component_poll()

        self.assertEqual(window.master.scheduled, [])

    def test_component_cycle_launches_due_components_and_reschedules(self) -> None:
        window = self.make_window()
        window._launch_component_scan = Mock()
        window._component_scheduler = ComponentRefreshScheduler({"cpu": 1000})

        window._run_component_cycle()

        window._launch_component_scan.assert_called_once_with("cpu")
        self.assertEqual(
            window.master.scheduled[-1][0],
            AppWindow.COMPONENT_POLL_MILLISECONDS,
        )

    def test_hidden_non_urgent_component_refresh_is_deferred_until_visible(
        self,
    ) -> None:
        window = self.make_window()
        window._launch_component_scan = Mock()
        window._component_scheduler = ComponentRefreshScheduler({"cpu": 1000})
        window._page_router = Mock()
        window._page_router.is_mapped.return_value = False

        window._run_component_cycle()
        window._run_component_cycle()

        window._launch_component_scan.assert_not_called()

        window._page_router.is_mapped.return_value = True
        window._coordinator.flush_deferred("component:cpu")

        window._launch_component_scan.assert_called_once_with("cpu")

    def test_repeated_hidden_component_cycles_do_not_schedule_immediate_timers(
        self,
    ) -> None:
        window = self.make_window()
        window._launch_component_scan = Mock()
        window._component_scheduler = ComponentRefreshScheduler({"cpu": 1000})
        window._page_router = Mock()
        window._page_router.is_mapped.return_value = False

        for _ in range(20):
            window._run_component_cycle()

        delays = [entry[0] for entry in window.master.scheduled]
        self.assertEqual(len(delays), 20)
        self.assertNotIn(0, delays)
        self.assertTrue(
            all(delay == AppWindow.COMPONENT_POLL_MILLISECONDS for delay in delays)
        )
        window._launch_component_scan.assert_not_called()

    def test_explicit_visible_component_refresh_starts_immediately(self) -> None:
        window = self.make_window()
        window._launch_component_scan = Mock()
        window._component_scheduler = ComponentRefreshScheduler({"cpu": 1000})
        window._page_router = Mock()
        window._page_router.is_mapped.return_value = True

        window._run_component_cycle()

        window._launch_component_scan.assert_called_once_with("cpu")

    def test_switch_selected_node_cancels_old_node_component_work(self) -> None:
        window = self.make_window()
        old_context = Mock()
        old_context.descriptor = Mock(id=NodeId("old"))
        old_context.scheduler = Mock()
        new_context = Mock()
        new_context.descriptor = Mock(id=NodeId("new"))
        new_context.scheduler = Mock()
        registry = Mock()
        registry.select = Mock()
        registry.context = Mock(side_effect=[old_context, new_context])
        registry.selected_context = Mock(return_value=new_context)
        window._node_registry = registry
        window._selected_node_id = NodeId("old")
        window._feature_catalog = Mock(all=Mock(return_value=(Mock(key="cpu"),)))
        render_coordinator = Mock(invalidate=Mock())
        window._render_coordinator = Mock(return_value=render_coordinator)
        window._cancel_active_scan = Mock()
        window._sync_selected_context_mirrors = Mock()
        window._render_selected_node = Mock()
        window._schedule_timer = Mock()

        window._switch_selected_node(NodeId("new"))

        registry.select.assert_called_once_with(NodeId("new"))
        window._cancel_active_scan.assert_called_once()
        old_context.scheduler.cancel.assert_called_once_with("cpu")
        render_coordinator.invalidate.assert_any_call(
            "component:cpu",
            0,
            node_id=NodeId("new"),
        )
        window._sync_selected_context_mirrors.assert_called_once_with(new_context)
        window._render_selected_node.assert_called_once_with(new_context)

    def test_late_snapshot_and_error_callbacks_are_ignored(self) -> None:
        window = self.make_window()
        window._is_closing = True
        window._set_busy = Mock()

        window._show_snapshot(Mock())
        window._show_error("error")

        window._set_busy.assert_not_called()

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
        window._schedule_timer.assert_any_call(0, window.handle_analyze)

    def test_handle_analyze_schedules_scan_timeout_watchdog(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()

        window.handle_analyze()

        self.assertIsNotNone(window._scan_timeout_id)
        delays = [entry[0] for entry in window.master.scheduled]
        self.assertIn(AppWindow.SCAN_TIMEOUT_MILLISECONDS, delays)

    def test_scan_timeout_stops_scan_and_reports_error(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()
        window._show_error = Mock()

        window.handle_analyze()
        cancel_event = window._analysis_cancel_event
        window._handle_scan_timeout(1)

        window._show_error.assert_called_once_with(AppWindow.SCAN_TIMEOUT_MESSAGE)
        self.assertTrue(cancel_event.is_set())
        self.assertIsNone(window._analysis_cancel_event)
        # The lease stays held until the worker physically finishes.
        self.assertTrue(window._scan_coordinator.active)
        self.assertEqual(window._timed_out_generation, 1)

        window._background_tasks = 1
        window._background_queue.put(None)
        window._drain_background_queue()

        self.assertFalse(window._scan_coordinator.active)
        self.assertIsNone(window._timed_out_generation)

    def test_timeout_lease_prevents_overlap_then_recovers(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()
        window._show_error = Mock()

        window.handle_analyze()
        window._handle_scan_timeout(1)
        # A new trigger while the old worker is still running is coalesced.
        window.handle_analyze()
        self.assertTrue(window._scan_coordinator.active)
        self.assertTrue(window._scan_coordinator.rerun_requested)

        window._schedule_timer = Mock(return_value="after#1")
        window._background_tasks = 1
        window._background_queue.put(None)
        window._drain_background_queue()

        self.assertFalse(window._scan_coordinator.active)
        window._schedule_timer.assert_any_call(0, window.handle_analyze)

    def test_timeout_lease_is_force_released_after_grace(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()
        window._show_error = Mock()

        window.handle_analyze()
        window._handle_scan_timeout(1)
        window._release_lease_after_grace(1)

        self.assertFalse(window._scan_coordinator.active)
        self.assertIsNone(window._timed_out_generation)

    def test_scan_timeout_is_ignored_for_resolved_generation(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()
        window._show_error = Mock()
        window._show_snapshot = Mock()

        window.handle_analyze()
        window._show_snapshot_for_generation(1, Mock())
        window._handle_scan_timeout(1)

        window._show_error.assert_not_called()

    def test_late_scan_completion_after_timeout_is_dropped(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()
        window._show_error = Mock()
        window._show_snapshot = Mock()
        snapshot = Mock()

        window.handle_analyze()
        window._handle_scan_timeout(1)
        window._show_snapshot_for_generation(1, snapshot)

        window._show_error.assert_called_once_with(AppWindow.SCAN_TIMEOUT_MESSAGE)
        window._show_snapshot.assert_not_called()

    def test_completed_scan_cancels_timeout_watchdog(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()
        window._show_snapshot = Mock()

        window.handle_analyze()
        timeout_id = window._scan_timeout_id
        window._show_snapshot_for_generation(1, Mock())

        self.assertIsNone(window._scan_timeout_id)
        self.assertIn(timeout_id, window.master.cancelled)

    def test_resolve_generation_clears_timeout_and_cancel_event(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()

        window.handle_analyze()
        timeout_id = window._scan_timeout_id
        resolved, rerun_requested = window._resolve_generation(1)

        self.assertTrue(resolved)
        self.assertFalse(rerun_requested)
        self.assertIsNone(window._scan_timeout_id)
        self.assertIn(timeout_id, window.master.cancelled)
        self.assertIsNone(window._analysis_cancel_event)

    def test_resolve_generation_ignores_already_resolved(self) -> None:
        window = self.make_window()
        window._resolved_scan_generation = 1
        window._scan_timeout_id = "pending-id"
        window._analysis_cancel_event = threading.Event()

        resolved, rerun_requested = window._resolve_generation(1)

        self.assertFalse(resolved)
        self.assertFalse(rerun_requested)
        self.assertEqual(window._scan_timeout_id, "pending-id")
        self.assertIsNotNone(window._analysis_cancel_event)

    def test_close_cancels_pending_scan_timeout(self) -> None:
        window = self.make_window()
        window.analyzer = Mock()
        window._run_in_background = Mock()

        window.handle_analyze()
        timeout_id = window._scan_timeout_id
        window._close()

        self.assertIn(timeout_id, window.master.cancelled)
        self.assertIsNone(window._scan_timeout_id)

    def test_run_handles_ctrl_c_with_normal_close_path(self) -> None:
        window = self.make_window()
        window.master.mainloop = Mock(side_effect=KeyboardInterrupt)
        window._close = Mock()

        window.run()

        window._close.assert_called_once_with()

    def test_close_during_live_scan_swallows_late_result(self) -> None:
        window = self.make_window()
        window.snapshot = None
        started = threading.Event()
        release = threading.Event()

        def slow_snapshot(cancel_event: threading.Event | None = None) -> str:
            del cancel_event
            started.set()
            release.wait(5)
            return "late-result"

        window.analyzer = Mock()
        window.analyzer.dashboard_snapshot = slow_snapshot
        window._set_busy = Mock()
        window._schedule_auto_scan = Mock()
        window._show_error = Mock()

        window.handle_analyze()
        self.assertTrue(started.wait(2), "scan worker did not start")

        window._close()
        release.set()

        deadline = time.monotonic() + 2
        while window._background_queue.qsize() < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        window._drain_background_queue()

        self.assertTrue(window._is_closing)
        self.assertTrue(window.master.destroyed)
        self.assertEqual(window._background_tasks, 0)
        window._show_error.assert_not_called()
        self.assertIsNone(window.snapshot)

    def test_scan_failure_replay_survives_timeout_watchdog(self) -> None:
        window = self.make_window()
        window._show_error = Mock()
        window._show_snapshot = Mock()
        window._scan_coordinator.generation = 2

        window._show_error_for_generation(2, "disk unavailable")
        window._handle_scan_timeout(2)
        window._show_error_for_generation(2, "disk unavailable")

        window._show_error.assert_called_once_with("disk unavailable")

    def test_open_resource_routes_every_card_to_intended_dialog(self) -> None:
        window = self.make_window()
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=Mock())
        window.analyzer = Mock()
        window.process_manager = Mock()
        window.file_manager = Mock()

        with (
            patch("window.ProcessDialog") as process_dialog,
            patch("window.StorageDialog") as storage_dialog,
            patch("window.InfoDialog") as info_dialog,
        ):
            for key in ("cpu", "memory", "storage", "gpu", "network", "battery"):
                window.open_resource(key)

        self.assertEqual(process_dialog.call_count, 2)
        self.assertEqual(storage_dialog.call_count, 1)
        self.assertEqual(info_dialog.call_count, 3)

        process_kwargs = [call.kwargs for call in process_dialog.call_args_list]
        self.assertEqual(
            [kwargs["resource_key"] for kwargs in process_kwargs],
            ["cpu", "memory"],
        )
        for kwargs in process_kwargs:
            self.assertEqual(kwargs["analyzer"], window.analyzer)
            self.assertEqual(kwargs["manager"], window.process_manager)
            self.assertEqual(kwargs["colors"], window.colors)
            self.assertTrue(callable(kwargs["on_changed"]))

        storage_kwargs = storage_dialog.call_args.kwargs
        self.assertEqual(storage_kwargs["manager"], window.file_manager)
        self.assertEqual(storage_kwargs["colors"], window.colors)
        self.assertTrue(callable(storage_kwargs["on_changed"]))

        for call in info_dialog.call_args_list:
            self.assertEqual(call.args[0], window.master)
            self.assertEqual(call.kwargs["colors"], window.colors)

    def test_open_resource_unknown_key_propagates_snapshot_lookup_error(self) -> None:
        window = self.make_window()
        window.snapshot = Mock()
        window.snapshot.get = Mock(side_effect=KeyError("Unknown resource: nope"))

        with (
            patch("window.ProcessDialog"),
            patch("window.StorageDialog"),
            patch("window.InfoDialog"),
            self.assertRaises(KeyError),
        ):
            window.open_resource("nope")

    def test_open_resource_requires_scan_before_opening(self) -> None:
        window = self.make_window()
        window.snapshot = None

        with (
            patch("window.messagebox.showinfo") as showinfo,
            patch("window.ProcessDialog") as process_dialog,
        ):
            window.open_resource("cpu")

        showinfo.assert_called_once()
        process_dialog.assert_not_called()

    @staticmethod
    def _summary(
        key: str,
        title: str,
        value: str = "10%",
        *,
        failed: bool = False,
    ) -> ResourceSummary:
        return make_summary(
            key,
            title,
            value=value,
            subtitle="subtitle",
            percent=5.0,
            details=(f"{key} detail",),
            failed=failed,
        )

    @staticmethod
    def _snapshot(*resources: ResourceSummary) -> DashboardSnapshot:
        return make_snapshot(*resources)

    def test_merge_snapshot_keeps_last_valid_card_on_transient_failure(self) -> None:
        window = self.make_window()
        window.snapshot = self._snapshot(self._summary("cpu", "CPU", "25%"))

        merged = window._merge_snapshot(
            self._snapshot(self._summary("cpu", "CPU", "Unavailable", failed=True))
        )

        self.assertEqual(merged.get("cpu").value, "25%")

    def test_merge_snapshot_shows_unavailable_after_sustained_failure(self) -> None:
        window = self.make_window()
        window.snapshot = self._snapshot(self._summary("cpu", "CPU", "25%"))
        failed = self._summary("cpu", "CPU", "Unavailable", failed=True)

        merged = window._merge_snapshot(self._snapshot(failed))
        for _ in range(window.FAILED_CARD_KEEP_LIMIT - 1):
            merged = window._merge_snapshot(self._snapshot(failed))

        self.assertEqual(merged.get("cpu").value, "Unavailable")

    def test_merge_snapshot_keeps_unrelated_cards_updating(self) -> None:
        window = self.make_window()
        window.snapshot = self._snapshot(
            self._summary("cpu", "CPU", "25%"),
            self._summary("memory", "Memory", "50%"),
        )

        merged = window._merge_snapshot(
            self._snapshot(
                self._summary("cpu", "CPU", "Unavailable", failed=True),
                self._summary("memory", "Memory", "60%"),
            )
        )

        self.assertEqual(merged.get("cpu").value, "25%")
        self.assertEqual(merged.get("memory").value, "60%")

    def test_merge_snapshot_first_scan_failure_shows_unavailable(self) -> None:
        window = self.make_window()
        window.snapshot = None

        merged = window._merge_snapshot(
            self._snapshot(self._summary("cpu", "CPU", "Unavailable", failed=True))
        )

        self.assertEqual(merged.get("cpu").value, "Unavailable")

    def test_merge_snapshot_success_resets_failure_count(self) -> None:
        window = self.make_window()
        window.snapshot = self._snapshot(self._summary("cpu", "CPU", "25%"))
        failed = self._summary("cpu", "CPU", "Unavailable", failed=True)

        window.snapshot = window._merge_snapshot(self._snapshot(failed))
        merged = window._merge_snapshot(
            self._snapshot(self._summary("cpu", "CPU", "30%"))
        )
        self.assertEqual(merged.get("cpu").value, "30%")

        window.snapshot = merged
        merged_again = window._merge_snapshot(self._snapshot(failed))
        self.assertEqual(merged_again.get("cpu").value, "30%")

    def test_component_result_applies_to_card_and_snapshot(self) -> None:
        window = self.make_window()
        window.cards = {"cpu": Mock()}
        window.snapshot = self._snapshot(self._summary("cpu", "CPU", "25%"))

        window._apply_component("cpu", self._summary("cpu", "CPU", "30%"))

        window.cards["cpu"].update_summary.assert_called_once()
        self.assertEqual(window.snapshot.get("cpu").value, "30%")

    def test_component_failure_keeps_last_valid_until_limit(self) -> None:
        window = self.make_window()
        window.cards = {"cpu": Mock()}
        window.snapshot = self._snapshot(self._summary("cpu", "CPU", "25%"))
        failed = self._summary("cpu", "CPU", "Unavailable", failed=True)

        for _ in range(window.FAILED_CARD_KEEP_LIMIT):
            window._apply_component("cpu", failed)

        self.assertEqual(window.snapshot.get("cpu").value, "Unavailable")

    def test_component_apply_does_not_touch_global_scan_status(self) -> None:
        window = self.make_window()
        window.cards = {"cpu": Mock()}
        window.snapshot = self._snapshot(self._summary("cpu", "CPU", "25%"))

        window._apply_component("cpu", self._summary("cpu", "CPU", "30%"))

        window.status_label.config.assert_not_called()
        self.assertIsNone(window.progress_bar)
        window.cards["cpu"].update_summary.assert_called_once()

    def test_component_cycle_skips_in_flight_component(self) -> None:
        window = self.make_window()
        window._component_scheduler = ComponentRefreshScheduler({"cpu": 1000})
        window._component_scheduler.begin("cpu", 0.0)
        window._launch_component_scan = Mock()

        window._run_component_cycle()

        window._launch_component_scan.assert_not_called()

    def test_component_queue_drains_error_as_failed_and_keeps_last_valid(self) -> None:
        window = self.make_window()
        window.cards = {"cpu": Mock()}
        window.snapshot = self._snapshot(self._summary("cpu", "CPU", "25%"))

        window._queue_component_result("cpu", 0.0, RuntimeError("boom"))

        self.assertEqual(window.snapshot.get("cpu").value, "25%")
        self.assertFalse(window._component_scheduler.in_flight("cpu"))

    def test_run_daemon_delivers_success_and_calls_finished(self) -> None:
        window = self.make_window()
        received: list[Any] = []
        finished = threading.Event()

        window._run_daemon(
            lambda: 42,
            received.append,
            received.append,
            on_finished=finished.set,
        )

        self.assertTrue(finished.wait(1))
        self.assertEqual(received, [42])

    def test_run_daemon_delivers_error_without_finished_hook(self) -> None:
        window = self.make_window()
        received: list[Any] = []

        def boom() -> None:
            raise RuntimeError("boom")

        window._run_daemon(boom, received.append, received.append)

        deadline = time.monotonic() + 1
        while not received and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(len(received), 1)
        self.assertIsInstance(received[0], RuntimeError)

    def test_cancel_analysis_sets_cancel_event(self) -> None:
        window = self.make_window()
        window._analysis_cancel_event = threading.Event()

        window._cancel_analysis()

        self.assertTrue(window._analysis_cancel_event.is_set())
        window.cancel_button.config.assert_called_with(state=tk.DISABLED)
        window.status_label.config.assert_called_with(text="●  Cancelling...")

    def test_set_busy_toggles_cancel_button(self) -> None:
        window = self.make_window()

        window._set_busy(True)
        window.cancel_button.config.assert_called_with(state=tk.NORMAL)

        window._set_busy(False)
        window.cancel_button.config.assert_called_with(state=tk.DISABLED)

    def test_request_render_applies_directly_without_coordinator(self) -> None:
        window = self.make_window()
        applied: list[object] = []

        accepted = window._request_render(
            RenderIntent(target="scan-status", payload="done", payload_set=True),
            lambda intent: applied.append(intent.payload),
        )

        self.assertTrue(accepted)
        self.assertEqual(applied, ["done"])

    def test_request_render_defers_hidden_target_through_coordinator(self) -> None:
        window = self.make_window()
        window._ui_coordinator = UICoordinator()
        window._ui_coordinator.set_visible("scan-status", False)
        applied: list[object] = []

        window._request_render(
            RenderIntent(target="scan-status", payload="queued", payload_set=True),
            lambda intent: applied.append(intent.payload),
        )

        self.assertEqual(applied, [])
        self.assertEqual(window._ui_coordinator.pending_count, 1)

        window._ui_coordinator.set_visible("scan-status", True)

        self.assertEqual(applied, ["queued"])
        self.assertEqual(window._ui_coordinator.pending_count, 0)

    def test_set_busy_toggles_button_coordinator_buttons(self) -> None:
        window = self.make_window()
        coordinator = ButtonCoordinator()
        scan_button = RecordingWidget()
        cancel_button = RecordingWidget()
        coordinator.register("preferences:scan", Mock())
        coordinator.register("preferences:cancel-scan", Mock(), enabled=False)
        coordinator.bind(scan_button, "preferences:scan")
        coordinator.bind(cancel_button, "preferences:cancel-scan")
        window._button_coordinator = coordinator

        window._set_busy(True)
        self.assertEqual(scan_button.config_options["state"], tk.DISABLED)
        self.assertEqual(cancel_button.config_options["state"], tk.NORMAL)
        self.assertFalse(coordinator.is_enabled("preferences:scan"))
        self.assertTrue(coordinator.is_enabled("preferences:cancel-scan"))

        window._set_busy(False)
        self.assertEqual(scan_button.config_options["state"], tk.NORMAL)
        self.assertEqual(cancel_button.config_options["state"], tk.DISABLED)
        self.assertTrue(coordinator.is_enabled("preferences:scan"))
        self.assertFalse(coordinator.is_enabled("preferences:cancel-scan"))

    def test_cancel_analysis_disables_button_coordinator_cancel(self) -> None:
        window = self.make_window()
        window._analysis_cancel_event = threading.Event()
        coordinator = ButtonCoordinator()
        cancel_button = RecordingWidget()
        coordinator.register("preferences:cancel-scan", Mock())
        coordinator.bind(cancel_button, "preferences:cancel-scan")
        window._button_coordinator = coordinator

        window._cancel_analysis()

        self.assertTrue(window._analysis_cancel_event.is_set())
        self.assertEqual(cancel_button.config_options["state"], tk.DISABLED)
        self.assertFalse(coordinator.is_enabled("preferences:cancel-scan"))

    def test_show_progress_updates_status(self) -> None:
        window = self.make_window()

        window._show_progress("Scanning CPU...")

        window.status_label.config.assert_called_with(text="●  Scanning CPU... (1/6)")

    def test_presentation_targets_include_optional_preferences_pair(self) -> None:
        window = self.make_window()
        window.preferences_status_label = Mock()
        window.preferences_progress_bar = Mock()

        window._for_each_presentation_target(
            lambda label, bar: (
                label.config(text="x"),
                bar.stop() if bar is not None else None,
            )
        )

        window.status_label.config.assert_called_with(text="x")
        window.preferences_status_label.config.assert_called_with(text="x")
        window.preferences_progress_bar.stop.assert_called_once()

    def test_presentation_targets_work_without_preferences_pair(self) -> None:
        window = self.make_window()

        window._for_each_presentation_target(
            lambda label, bar: (
                label.config(text="x"),
                bar.stop() if bar is not None else None,
            )
        )

        window.status_label.config.assert_called_with(text="x")
        self.assertIsNone(window.progress_bar)

    def test_render_visibility_tracks_active_page(self) -> None:
        window = self.make_window()
        window._ui_coordinator = Mock()

        window._sync_render_visibility("nodes")

        window._ui_coordinator.set_visible.assert_any_call("dashboard-snapshot", False)
        window._ui_coordinator.set_visible.assert_any_call("scan-status", False)
        window._ui_coordinator.set_visible.assert_any_call("thermals", False)
        window._ui_coordinator.set_visible.assert_any_call("discovery-pages", True)

    def test_cancelled_scan_keeps_previous_results_without_error_dialog(self) -> None:
        window = self.make_window()
        window._scan_coordinator.generation = 1
        window._show_error = Mock()
        window._set_busy = Mock()

        window._show_error_for_generation(
            1,
            str(ScanCancelled(DOWNLOADS_SCAN_CANCELLED)),
        )

        window._show_error.assert_not_called()
        window._set_busy.assert_called_once_with(False)
        window.refreshed_label.config.assert_called_with(
            text="Scan cancelled; previous results remain"
        )

    def test_progress_steps_advance_with_scan_messages(self) -> None:
        window = self.make_window()

        for message in ("CPU", "Memory", "Storage", "GPU", "Network", "Battery"):
            window._show_progress(f"Scanning {message}...")

        self.assertIsNone(window.progress_bar)
        window.status_label.config.assert_called_with(
            text="●  Scanning Battery... (6/6)"
        )

    def test_success_sets_full_bar_and_complete_status(self) -> None:
        window = self.make_window()
        window.snapshot = None
        window.cards = {}
        window._refresh_health = Mock()
        window._set_busy = Mock()
        window._schedule_component_poll = Mock()

        window._show_snapshot(self._snapshot())

        window.status_label.config.assert_any_call(
            text="● Scan complete",
            style="Ready.Status.TLabel",
        )
        delays = [entry[0] for entry in window.master.scheduled]
        self.assertIn(AppWindow.COMPLETION_HOLD_MILLISECONDS, delays)

    def test_completion_hold_returns_status_to_ready_keeps_bar_full(self) -> None:
        window = self.make_window()
        window.snapshot = None
        window.cards = {}
        window._refresh_health = Mock()
        window._set_busy = Mock()
        window._schedule_component_poll = Mock()
        window._show_snapshot(self._snapshot())

        hold = next(
            entry[1]
            for entry in window.master.scheduled
            if entry[0] == AppWindow.COMPLETION_HOLD_MILLISECONDS
        )
        hold()

        window.status_label.config.assert_any_call(
            text="●  Ready",
            style="Ready.Status.TLabel",
        )
        self.assertIsNone(window.progress_bar)

    def test_hold_is_suppressed_when_new_scan_active(self) -> None:
        window = self.make_window()
        window.snapshot = None
        window.cards = {}
        window._refresh_health = Mock()
        window._set_busy = Mock()
        window._schedule_component_poll = Mock()
        window._show_snapshot(self._snapshot())

        window._scan_coordinator.active = True
        hold = next(
            entry[1]
            for entry in window.master.scheduled
            if entry[0] == AppWindow.COMPLETION_HOLD_MILLISECONDS
        )
        hold()

        window.status_label.config.assert_any_call(
            text="● Scan complete",
            style="Ready.Status.TLabel",
        )
        ready_texts = [
            call.kwargs.get("text")
            for call in window.status_label.config.call_args_list
            if call.kwargs.get("text") == "●  Ready"
        ]
        self.assertEqual(ready_texts, [])

    def test_error_resets_progress_bar_to_zero(self) -> None:
        window = self.make_window()
        window._show_progress("Scanning CPU...")

        with patch("window.messagebox.showerror"):
            window._show_error("boom")

        self.assertIsNone(window.progress_bar)

    def test_cancel_branch_resets_progress_bar_to_zero(self) -> None:
        window = self.make_window()
        window._scan_coordinator.generation = 1
        window._show_error = Mock()
        window._set_busy = Mock()
        window._show_progress("Scanning CPU...")

        window._show_error_for_generation(
            1,
            str(ScanCancelled(DOWNLOADS_SCAN_CANCELLED)),
        )

        self.assertIsNone(window.progress_bar)

    def test_busy_start_resets_progress_and_cancels_hold(self) -> None:
        window = self.make_window()
        window._show_progress("Scanning CPU...")
        transition = window._completion_transition()
        transition.start(500, lambda: None)
        pending_id = transition.pending_id
        self.assertIsNotNone(pending_id)

        window._set_busy(True)
        window._show_progress("Scanning CPU...")

        self.assertIn(pending_id, window.master.cancelled)
        window.status_label.config.assert_any_call(text="●  Scanning CPU... (1/6)")


class SettingsIntegrationTests(unittest.TestCase):
    @staticmethod
    def _summary(
        key: str,
        capability: CapabilityState = CapabilityState.UNKNOWN,
    ) -> ResourceSummary:
        return make_summary(
            key,
            key,
            value="10%",
            subtitle="subtitle",
            percent=5.0,
            details=(f"{key} detail",),
            capability=capability,
        )

    def test_interval_commit_updates_only_named_component(self) -> None:
        window = AppWindowTests.make_window()
        window.analyze_button = Mock()
        window.cancel_button = Mock()
        window.preferences_page = Mock()

        window._on_interval_commit("cpu", 5)

        self.assertEqual(window._preferences.refresh_intervals.cpu, 5000)
        self.assertEqual(window._component_scheduler.intervals["cpu"], 5000)
        self.assertEqual(window._component_scheduler.intervals["network"], 1000)
        window.preferences_page.show_status.assert_called_with("Preferences saved")

    def test_interval_commit_does_not_retime_other_components(self) -> None:
        window = AppWindowTests.make_window()
        window.preferences_page = Mock()
        scheduler = window._component_scheduler
        scheduler.mark_all_refreshed(0.0)

        window._on_interval_commit("cpu", 5)

        # Storage (default 30s) stays due at 30.0, not pushed out by the CPU
        # edit, and CPU is not due early (its deadline was pushed to now+5s).
        self.assertEqual(scheduler.due_keys(29.0), ("network", "memory", "gpu"))
        self.assertEqual(
            scheduler.due_keys(30.0),
            ("network", "memory", "gpu", "storage", "battery"),
        )
        self.assertEqual(scheduler.intervals["storage"], 30000)
        self.assertEqual(scheduler.intervals["cpu"], 5000)

    def test_invalid_interval_commit_is_rejected_and_restored(self) -> None:
        window = AppWindowTests.make_window()
        window.preferences_page = Mock()

        window._on_interval_commit("cpu", 999)

        self.assertEqual(window._preferences.refresh_intervals.cpu, 1000)
        window.preferences_page.show_error.assert_called_once()

    def test_apply_preferences_failure_keeps_runtime_unchanged(self) -> None:
        window = AppWindowTests.make_window()
        window.preferences_page = Mock()
        from unittest.mock import patch

        with patch.object(
            window._preferences_store,
            "save",
            side_effect=PreferencesSaveError("disk full"),
        ):
            window._on_interval_commit("cpu", 5)

        self.assertEqual(window._preferences.refresh_intervals.cpu, 1000)
        window.preferences_page.show_error.assert_called_with(
            "Preferences could not be saved"
        )

    def test_manual_hide_pauses_network_and_battery_only(self) -> None:
        window = AppWindowTests.make_window()
        window._on_card_visibility_change("network", False)
        window._on_card_visibility_change("battery", False)
        window._on_card_visibility_change("cpu", False)

        self.assertTrue(window._component_scheduler.is_paused("network"))
        self.assertTrue(window._component_scheduler.is_paused("battery"))
        self.assertFalse(window._component_scheduler.is_paused("cpu"))

    def test_re_enabling_card_requests_one_refresh(self) -> None:
        window = AppWindowTests.make_window()
        window._full_snapshot_applied_at = 1.0
        window._on_card_visibility_change("network", False)
        window._on_card_visibility_change("network", True)

        self.assertFalse(window._component_scheduler.is_paused("network"))
        self.assertIn("network", window._component_scheduler.due_keys(1.0))

    def test_unsupported_capability_auto_hides_and_pauses(self) -> None:
        window = AppWindowTests.make_window()
        window._preferences = window._preferences.with_hide_unavailable_cards(True)

        window._observe_capability(
            "battery",
            self._summary("battery", CapabilityState.UNSUPPORTED),
        )
        self.assertTrue(window._is_card_visible("battery"))
        self.assertFalse(window._component_scheduler.is_paused("battery"))

        window._observe_capability(
            "battery",
            self._summary("battery", CapabilityState.UNSUPPORTED),
        )

        self.assertFalse(window._is_card_visible("battery"))
        self.assertTrue(window._component_scheduler.is_paused("battery"))

    def test_single_unsupported_observation_is_not_enough_to_hide(self) -> None:
        window = AppWindowTests.make_window()
        window._preferences = window._preferences.with_hide_unavailable_cards(True)

        window._observe_capability(
            "battery",
            self._summary("battery", CapabilityState.UNSUPPORTED),
        )

        self.assertTrue(window._is_card_visible("battery"))
        self.assertFalse(window._component_scheduler.is_paused("battery"))

    def test_supported_observation_resets_unsupported_count(self) -> None:
        window = AppWindowTests.make_window()
        window._preferences = window._preferences.with_hide_unavailable_cards(True)
        window._observe_capability(
            "battery",
            self._summary("battery", CapabilityState.UNSUPPORTED),
        )
        window._observe_capability(
            "battery",
            self._summary("battery", CapabilityState.SUPPORTED),
        )
        window._observe_capability(
            "battery",
            self._summary("battery", CapabilityState.UNSUPPORTED),
        )

        self.assertTrue(window._is_card_visible("battery"))

    def test_unknown_capability_never_auto_hides(self) -> None:
        window = AppWindowTests.make_window()
        window._preferences = window._preferences.with_hide_unavailable_cards(True)
        window._observe_capability(
            "gpu",
            self._summary("gpu", CapabilityState.UNKNOWN),
        )

        self.assertTrue(window._is_card_visible("gpu"))
        self.assertFalse(window._component_scheduler.is_paused("gpu"))

    def test_supported_recovery_restores_auto_hidden_card(self) -> None:
        window = AppWindowTests.make_window()
        window._preferences = window._preferences.with_hide_unavailable_cards(True)
        window._observe_capability(
            "battery",
            self._summary("battery", CapabilityState.UNSUPPORTED),
        )
        window._observe_capability(
            "battery",
            self._summary("battery", CapabilityState.UNSUPPORTED),
        )
        self.assertFalse(window._is_card_visible("battery"))

        window._observe_capability(
            "battery",
            self._summary("battery", CapabilityState.SUPPORTED),
        )

        self.assertTrue(window._is_card_visible("battery"))
        self.assertFalse(window._component_scheduler.is_paused("battery"))

    def test_capability_is_processed_before_last_valid_merge(self) -> None:
        window = AppWindowTests.make_window()
        window.snapshot = make_snapshot(
            self._summary("battery", CapabilityState.SUPPORTED),
            system_label="linux",
        )

        incoming = self._summary("battery", CapabilityState.UNSUPPORTED)
        window._observe_capability("battery", incoming)
        window._observe_capability("battery", incoming)

        self.assertEqual(
            window._capabilities["battery"],
            CapabilityState.UNSUPPORTED,
        )

    def test_scan_state_mirrors_to_settings_presentation(self) -> None:
        window = AppWindowTests.make_window()
        window.preferences_status_label = Mock()
        window.preferences_progress_bar = Mock()

        window._set_busy(True)
        window.preferences_status_label.config.assert_any_call(
            text="●  Scanning...",
            style="Busy.Status.TLabel",
        )
        window._show_progress("Scanning CPU...")
        window.preferences_status_label.config.assert_any_call(
            text="●  Scanning CPU... (1/6)"
        )
        window.preferences_progress_bar.config.assert_any_call(value=1)
        window.status_label.config.assert_any_call(text="●  Scanning CPU... (1/6)")

    def test_scan_complete_mirrors_to_settings_presentation(self) -> None:
        window = AppWindowTests.make_window()
        window.preferences_status_label = Mock()
        window.preferences_progress_bar = Mock()
        window.snapshot = None
        window.cards = {}
        window._refresh_health = Mock()
        window._schedule_component_poll = Mock()

        window._show_snapshot(
            make_snapshot(system_label="linux"),
        )

        window.preferences_progress_bar.config.assert_any_call(
            value=6,
            style="Complete.Horizontal.TProgressbar",
        )
        window.preferences_status_label.config.assert_any_call(
            text="● Scan complete",
            style="Ready.Status.TLabel",
        )

    def test_navigation_switches_between_all_three_pages(self) -> None:
        window = AppWindowTests.make_window()
        window._page_router = Mock()
        window.settings_home = Mock()
        window.preferences_page = Mock()

        window._show_settings_page()
        window._page_router.show.assert_called_with("settings")
        window.settings_home.focus_back.assert_called_once()

        window._show_preferences_page()
        window._page_router.show.assert_called_with("preferences")
        window.preferences_page.focus_back.assert_called_once()

        window._show_dashboard_page()
        window._page_router.show.assert_called_with("dashboard")

    def test_settings_category_dispatch_opens_preferences(self) -> None:
        window = AppWindowTests.make_window()
        window._page_router = Mock()

        window._on_select_settings_category("preferences")

        window._page_router.show.assert_called_with("preferences")

    def test_settings_category_dispatch_opens_diagnostics(self) -> None:
        window = AppWindowTests.make_window()
        window._page_router = Mock()

        window._on_select_settings_category("diagnostics")

        window._page_router.show.assert_called_with("diagnostics")

    def test_preferences_back_returns_to_settings(self) -> None:
        window = AppWindowTests.make_window()
        window._page_router = Mock()
        window.settings_home = Mock()

        window._show_settings_page()
        window.settings_home.focus_back.assert_called_once()
        window._page_router.show.assert_called_with("settings")

    def test_reset_restores_defaults_after_confirmation(self) -> None:
        window = AppWindowTests.make_window()
        window.preferences_page = Mock()
        window._preferences = window._preferences.with_interval("cpu", 5000)
        window._preferences = window._preferences.with_card_visibility("gpu", False)

        with patch("window.messagebox.askyesno", return_value=True):
            window._on_reset()

        self.assertEqual(window._preferences.refresh_intervals.cpu, 1000)
        self.assertIn("gpu", window._preferences.visible_cards)

    def test_reset_skipped_without_confirmation(self) -> None:
        window = AppWindowTests.make_window()
        window.preferences_page = Mock()
        window._preferences = window._preferences.with_interval("cpu", 5000)

        with patch("window.messagebox.askyesno", return_value=False):
            window._on_reset()

        self.assertEqual(window._preferences.refresh_intervals.cpu, 5000)

    def test_show_snapshot_caches_dashboard_result_for_retrieval(self) -> None:
        window = AppWindowTests.make_window()
        window.snapshot = None
        window.cards = {
            feature.key: Mock() for feature in window._feature_catalog.all()
        }
        window._refresh_health = Mock()
        window._set_busy = Mock()
        window._schedule_component_poll = Mock()

        snapshot = make_snapshot(
            self._summary("cpu", CapabilityState.UNKNOWN),
            system_label="linux",
        )
        window._show_snapshot(snapshot)

        cached = window._coordinator.last_result("snapshot:dashboard")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.get("cpu").value, "10%")

    def test_component_result_cached_for_retrieval(self) -> None:
        window = AppWindowTests.make_window()
        window.cards = {"cpu": Mock()}
        window.snapshot = make_snapshot(
            self._summary("cpu"),
            system_label="linux",
        )

        window._apply_component("cpu", self._summary("cpu", CapabilityState.UNKNOWN))

        cached = window._coordinator.last_result("component:cpu")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.value, "10%")

    def test_gpu_transient_timeout_keeps_last_valid_card(self) -> None:
        window = AppWindowTests.make_window()
        valid = make_summary(
            "gpu",
            "GPU",
            value="Radeon Vega Series",
            subtitle="Graphics hardware",
            percent=None,
            details=("AMD Vega GPU",),
            capability=CapabilityState.SUPPORTED,
        )
        window.snapshot = make_snapshot(valid, system_label="linux")
        window._observe_capability("gpu", valid)

        transient = make_summary(
            "gpu",
            "GPU",
            value="GPU information unavailable",
            subtitle="Information unavailable",
            percent=None,
            details=("GPU information unavailable: query timed out",),
            failed=True,
            capability=CapabilityState.UNKNOWN,
        )
        merged = window._merge_snapshot(
            make_snapshot(transient, system_label="linux"),
        )

        self.assertEqual(merged.get("gpu").value, "Radeon Vega Series")
        self.assertEqual(window._capabilities.get("gpu"), CapabilityState.SUPPORTED)


if __name__ == "__main__":
    unittest.main()
