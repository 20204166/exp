"""Platform-simulated admission and UI-thread boundary regressions."""

import threading
import unittest
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import Mock, patch

from maintenance.components import ClockCoordinator, JobProfile, PressureSnapshot
from maintenance.components.clock_coordinator import ResourceGovernor
from maintenance.components.coordinator import AppCoordinator
from maintenance.nodes import LOCAL_NODE_ID, NodeId
from maintenance.ui.render_coordinator import UICoordinator
from tests import test_window, test_window_nodes
from tests.support.models import make_snapshot, make_summary
from tests.support.scheduling import DeferredRunner


class GovernorIntegrationTests(unittest.TestCase):
    def test_component_cancel_retains_capacity_until_completion_then_retries(
        self,
    ) -> None:
        window = test_window_nodes._make_window(start_discovery=False)
        context = window._node_registry.context(NodeId(LOCAL_NODE_ID))
        context.provider = Mock()
        context.provider.component_summary.return_value = make_summary("cpu", "CPU")
        window._component_scheduler = context.scheduler
        window._feature_catalog.all = lambda: [SimpleNamespace(key="cpu")]
        runner = DeferredRunner()
        window._coordinator = AppCoordinator(runner=runner, deliver=window._submit_ui)
        governor = ResourceGovernor(clock=lambda: 100.0)
        window._resource_governor = governor
        key = "node:local:component:cpu"
        with patch.object(governor, "request_pressure_sample", return_value=False):
            window._launch_component_scan("cpu")
            window._cancel_node_operations(context)
            self.assertIn(key, governor._active)
            self.assertTrue(context.scheduler.in_flight("cpu"))
            window._launch_component_scan("cpu")
            self.assertEqual(runner.pending, 1)
            self.assertFalse(window._coordinator.state(key).rerun_requested)
            runner.run_next()
            self.assertIn(key, governor._active)
            window._drain_background_queue()
            self.assertNotIn(key, governor._active)
            self.assertFalse(context.scheduler.in_flight("cpu"))
            context.scheduler.request_refresh("cpu")
            window._launch_component_scan("cpu")
            self.assertEqual(runner.pending, 1)

    def test_all_component_cards_complete_one_coordinated_cycle(self) -> None:
        window = test_window_nodes._make_window(start_discovery=False)
        context = window._node_registry.context(NodeId(LOCAL_NODE_ID))
        keys = tuple(context.scheduler.intervals)
        context.provider = Mock()
        context.provider.component_summary.side_effect = lambda key, **_kwargs: (
            make_summary(key, key.upper())
        )
        context.scheduler.mark_all_refreshed(0.0)
        for key in keys:
            context.scheduler.request_refresh(key)
        runner = DeferredRunner()
        window._coordinator = AppCoordinator(runner=runner, deliver=window._submit_ui)
        window._component_scheduler = context.scheduler
        window._apply_component = Mock()
        window._schedule_component_poll = Mock()

        for key in keys:
            window._launch_component_scan(key)
        self.assertEqual(runner.pending, len(keys))
        while runner.pending:
            runner.run_next()
        window._drain_background_queue()

        self.assertEqual(tuple(context.scheduler._in_flight), ())
        self.assertEqual(window._apply_component.call_count, len(keys))

    def test_hidden_component_render_cannot_finish_new_worker(self) -> None:
        window = test_window.AppWindowTests.make_window()
        window.analyzer = Mock()
        window.analyzer.component_summary.return_value = make_summary("cpu", "CPU")
        window._ui_coordinator = UICoordinator()
        window._ui_coordinator.set_visible("component:cpu", False)
        window._apply_component = Mock()
        window._schedule_component_poll = Mock()
        runner = DeferredRunner()
        window._coordinator = AppCoordinator(runner=runner, deliver=window._submit_ui)
        window._launch_component_scan("cpu")
        runner.run_next()
        window._drain_background_queue()
        self.assertFalse(window._component_scheduler.in_flight("cpu"))
        window._component_scheduler.request_refresh("cpu")
        window._launch_component_scan("cpu")
        window._ui_coordinator.set_visible("component:cpu", True)
        self.assertTrue(window._component_scheduler.in_flight("cpu"))
        window._apply_component.assert_called_once()

    def test_hidden_dashboard_completion_settles_before_render(self) -> None:
        window = test_window.AppWindowTests.make_window()
        window.analyzer = Mock()
        window._ui_coordinator = UICoordinator()
        window._ui_coordinator.set_visible("dashboard-snapshot", False)
        window._run_in_background = Mock()
        window._show_snapshot = Mock()
        window.handle_analyze()
        snapshot = make_snapshot()
        window._run_in_background.call_args.kwargs["on_success"](snapshot)
        self.assertFalse(window._scan_coordinator.active)
        self.assertIsNone(window._scan_timeout_id)
        window._show_snapshot.assert_not_called()
        window._ui_coordinator.set_visible("dashboard-snapshot", True)
        window._show_snapshot.assert_called_once_with(snapshot)

    def test_dashboard_thread_start_failure_releases_admission_and_timeout(
        self,
    ) -> None:
        window = test_window.AppWindowTests.make_window()
        window.analyzer = Mock()
        window._resource_governor = ResourceGovernor(clock=lambda: 100.0)
        window._run_daemon = Mock(side_effect=RuntimeError("no threads"))
        window._show_error = Mock()
        with patch.object(
            window._resource_governor, "request_pressure_sample", return_value=False
        ):
            window.handle_analyze()
        self.assertFalse(window._scan_coordinator.active)
        self.assertEqual(window._resource_governor._active, {})
        self.assertEqual(window._background_tasks, 0)
        self.assertIsNone(window._scan_timeout_id)
        window._show_error.assert_called_once_with("no threads")

    def test_discovery_post_never_calls_tk_from_worker(self) -> None:
        window = test_window.AppWindowTests.make_window()
        window._discovery_tick_id = "discovery-active"
        window._coordinator = AppCoordinator(
            deliver=window._submit_ui, on_activity=window._start_background_poll
        )
        callback = Mock()
        thread = threading.Thread(target=lambda: window._coordinator.post(callback))
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(window.master.scheduled, [])
        window._drain_background_queue()
        callback.assert_called_once_with()
        self.assertIsNotNone(window._background_poll_id)

    def test_manual_dashboard_starts_once_and_delivers_on_ui_thread(self) -> None:
        for system in ("Darwin", "Linux"):
            with (
                self.subTest(system=system),
                patch("platform.system", return_value=system),
            ):
                window = test_window.AppWindowTests.make_window()
                governor = ResourceGovernor(clock=lambda: 100.0)
                window._resource_governor = governor
                window._component_scheduler.mark_all_refreshed(10**12)
                window._set_busy = Mock()
                window._show_progress = Mock()
                window._show_snapshot = Mock()
                window._schedule_component_poll = Mock()
                window.analyzer = Mock()
                snapshot = make_snapshot()

                def scan(snapshot: object = snapshot, **kwargs: object) -> object:
                    progress = kwargs["progress_callback"]
                    assert callable(progress)
                    progress("Scanning CPU...")
                    return snapshot

                window.analyzer.dashboard_snapshot.side_effect = scan
                launched = Mock()
                window._run_daemon = launched
                with patch.object(
                    governor, "request_pressure_sample", return_value=False
                ):
                    window.handle_analyze()
                    self.assertEqual(launched.call_count, 1)
                    window.handle_analyze()
                    self.assertEqual(launched.call_count, 1)
                    task = launched.call_args.args[0]
                    success = launched.call_args.args[1]
                    finished = launched.call_args.kwargs["on_finished"]

                    def worker(
                        success: Callable[[object], None] = success,
                        task: Callable[[], object] = task,
                        finished: Callable[[], None] = finished,
                    ) -> None:
                        success(task())
                        finished()

                    thread = threading.Thread(target=worker)
                    thread.start()
                    thread.join(2)
                    self.assertFalse(thread.is_alive())
                    window._show_progress.assert_not_called()
                    window._show_snapshot.assert_not_called()
                    self.assertIn("dashboard", governor._active)
                    window._drain_background_queue()
                    window._show_progress.assert_called_once_with("Scanning CPU...")
                    window._show_snapshot.assert_called_once_with(snapshot)
                    self.assertFalse(window._scan_coordinator.active)
                    self.assertEqual(window._background_tasks, 0)
                    self.assertEqual(governor._active, {})

    def test_delayed_dashboard_render_drops_old_generation(self) -> None:
        window = test_window.AppWindowTests.make_window()
        window.analyzer = Mock()
        window._ui_coordinator = UICoordinator()
        window._ui_coordinator.set_visible("dashboard-snapshot", False)
        window._run_in_background = Mock()
        window._show_snapshot = Mock()
        window.handle_analyze()
        snapshot = make_snapshot()
        window._run_in_background.call_args.kwargs["on_success"](snapshot)
        window._scan_coordinator_state().begin()
        window._ui_coordinator.set_visible("dashboard-snapshot", True)
        window._show_snapshot.assert_not_called()

    def test_pressure_missing_after_overload_recovers_without_cadence_storm(
        self,
    ) -> None:
        governor = ResourceGovernor(clock=lambda: 100.0)
        clock = ClockCoordinator({"cpu": 1.0}, clock=lambda: 100.0)
        clock.mark_all_refreshed(100.0)
        job = JobProfile("cpu")
        with patch.object(governor, "request_pressure_sample", return_value=False):
            governor._apply_pressure_snapshot(
                PressureSnapshot(101.0, memory_percent=96.0, available=True)
            )
            self.assertEqual(clock.collect_due(101.0), ("cpu",))
            decision = governor.admit(job, 101.0)
            self.assertFalse(decision.admitted)
            assert decision.retry_at is not None
            clock.defer("cpu", decision.retry_at)
            self.assertEqual(clock.collect_due(101.0), ())
            governor._apply_pressure_snapshot(PressureSnapshot(102.0, available=False))
            self.assertFalse(governor.pressure.degraded)
            self.assertTrue(governor.admit(job, 103.0).admitted)
            self.assertTrue(clock.begin("cpu", 103.0))
            self.assertFalse(clock.begin("cpu", 103.0))
            clock.finish("cpu")
            governor.release("cpu")
            self.assertEqual(clock.next_deadline(103.0), 104.0)
            self.assertEqual(clock.collect_due(103.0), ())

    def test_missing_darwin_metrics_do_not_poison_pressure(self) -> None:
        fake = SimpleNamespace(
            virtual_memory=Mock(side_effect=AttributeError("unsupported")),
            swap_memory=Mock(side_effect=NotImplementedError),
            Process=Mock(side_effect=PermissionError),
            cpu_percent=Mock(return_value=0.0),
        )
        governor = ResourceGovernor(clock=lambda: 100.0)
        with (
            patch("platform.system", return_value="Darwin"),
            patch.dict("sys.modules", {"psutil": fake}),
        ):
            governor._apply_pressure_snapshot(
                PressureSnapshot(99.0, memory_percent=96.0, available=True)
            )
            pressure = governor.refresh_pressure()
        self.assertFalse(pressure.degraded)
        self.assertIsNone(pressure.rss_bytes)
        self.assertEqual(pressure.cpu_percent, 0.0)

    def test_pressure_sampler_start_failure_does_not_stick_busy(self) -> None:
        governor = ResourceGovernor(clock=lambda: 100.0)
        with patch("threading.Thread.start", side_effect=RuntimeError("no threads")):
            self.assertFalse(governor.request_pressure_sample())
        self.assertFalse(governor._pressure_sampling)

    def test_clock_uses_seconds_and_skips_missed_intervals_after_suspend(self) -> None:
        clock = ClockCoordinator({"cpu": 1.0}, clock=lambda: 10_000.25)
        clock.mark_all_refreshed(10_000.25)
        self.assertEqual(clock.next_deadline(), 10_001.25)
        self.assertEqual(clock.collect_due(10_001.24), ())
        self.assertTrue(clock.begin("cpu", 20_000.25))
        self.assertEqual(clock.state("cpu").next_due, 20_001.25)
        self.assertEqual(clock.collect_due(20_000.25), ())
        clock.finish("cpu")
        self.assertEqual(clock.collect_due(20_000.25), ())


if __name__ == "__main__":
    unittest.main()
