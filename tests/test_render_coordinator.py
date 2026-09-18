"""Focused tests for the UI presentation coordinator."""

import unittest
from threading import current_thread
from typing import Any

from maintenance.observability import ObservabilityWatcher
from maintenance.ui.render_coordinator import RenderIntent, UICoordinator


class UICoordinatorTests(unittest.TestCase):
    def test_render_commits_are_recorded_by_shared_observer(self) -> None:
        observer = ObservabilityWatcher()
        coordinator = UICoordinator(observer=observer)

        self.assertTrue(coordinator.request(RenderIntent("dashboard"), lambda _: None))

        metric = observer.snapshot().metrics[0]
        self.assertEqual(metric.target, "ui:render:dashboard")
        self.assertEqual(metric.count, 1)
        self.assertEqual(metric.successes, 1)

    def test_render_coalescing_stale_and_rejected_events_are_observed(self) -> None:
        observer = ObservabilityWatcher()
        coordinator = UICoordinator(observer=observer)
        coordinator.begin_batch()
        coordinator.request(RenderIntent("dashboard"), lambda _: None)
        coordinator.request(RenderIntent("dashboard"), lambda _: None)
        coordinator.end_batch()
        coordinator.request(RenderIntent("dashboard", generation=-1), lambda _: None)
        coordinator.shutdown()
        coordinator.request(RenderIntent("dashboard"), lambda _: None)

        metric = observer.snapshot().metrics[0]
        self.assertEqual(metric.coalesced, 1)
        self.assertEqual(metric.stale, 1)
        self.assertEqual(metric.rejected, 1)

    def test_batched_requests_coalesce_latest_payload_and_fields(self) -> None:
        coordinator = UICoordinator()
        received: list[RenderIntent] = []

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(
                target="dashboard",
                payload="first",
                payload_set=True,
                components=frozenset({"cpu"}),
            ),
            received.append,
        )
        coordinator.request(
            RenderIntent(
                target="dashboard",
                payload="second",
                payload_set=True,
                components=frozenset({"network"}),
                layout_changed=True,
                priority=2,
            ),
            received.append,
        )

        self.assertEqual(received, [])
        self.assertEqual(coordinator.pending_count, 1)
        self.assertEqual(coordinator.coalesced_requests, 1)

        coordinator.end_batch()

        self.assertEqual(len(received), 1)
        intent = received[0]
        self.assertEqual(intent.payload, "second")
        self.assertEqual(intent.components, frozenset({"cpu", "network"}))
        self.assertTrue(intent.layout_changed)
        self.assertEqual(coordinator.render_commits, 1)

    def test_late_generation_is_rejected_and_does_not_retain_pending(self) -> None:
        coordinator = UICoordinator()
        coordinator.invalidate("dashboard", 2)
        received: list[RenderIntent] = []

        accepted = coordinator.request(
            RenderIntent(
                target="dashboard",
                generation=1,
                payload="old",
                payload_set=True,
            ),
            received.append,
        )

        self.assertFalse(accepted)
        self.assertEqual(received, [])
        self.assertEqual(coordinator.pending_count, 0)
        self.assertEqual(coordinator.stale_rejections, 1)

    def test_hidden_target_defers_until_visible(self) -> None:
        coordinator = UICoordinator()
        coordinator.set_visible("dashboard", False)
        received: list[str] = []

        coordinator.request(
            RenderIntent(target="dashboard", payload="cached", payload_set=True),
            lambda intent: received.append(str(intent.payload)),
        )

        self.assertEqual(received, [])
        self.assertEqual(coordinator.pending_count, 1)

        coordinator.set_visible("dashboard", True)

        self.assertEqual(received, ["cached"])
        self.assertEqual(coordinator.pending_count, 0)

    def test_repeated_requests_stay_bounded_to_one_pending_entry(self) -> None:
        coordinator = UICoordinator()
        received: list[str] = []

        coordinator.begin_batch()
        for index in range(100):
            coordinator.request(
                RenderIntent(
                    target="dashboard",
                    payload=f"value-{index}",
                    payload_set=True,
                ),
                lambda intent: received.append(str(intent.payload)),
            )

        self.assertEqual(coordinator.pending_count, 1)
        coordinator.end_batch()

        self.assertEqual(received, ["value-99"])
        self.assertEqual(coordinator.pending_count, 0)
        self.assertEqual(coordinator.render_commits, 1)

    def test_requests_during_flush_wait_for_the_same_batch(self) -> None:
        coordinator = UICoordinator()
        received: list[str] = []

        def apply_dashboard(_intent: RenderIntent) -> None:
            received.append("dashboard")
            coordinator.request(
                RenderIntent(
                    target="thermals",
                    payload="latest",
                    payload_set=True,
                ),
                lambda intent: received.append(str(intent.payload)),
            )

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(target="dashboard", payload_set=True),
            apply_dashboard,
        )
        coordinator.end_batch()

        self.assertEqual(received, ["dashboard", "latest"])
        self.assertEqual(coordinator.pending_count, 0)
        self.assertEqual(coordinator.render_commits, 2)

    def test_shutdown_clears_pending_and_rejects_later_requests(self) -> None:
        coordinator = UICoordinator()
        received: list[str] = []

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(target="dashboard", payload="queued", payload_set=True),
            lambda intent: received.append(str(intent.payload)),
        )

        self.assertEqual(coordinator.pending_count, 1)
        coordinator.shutdown()

        self.assertEqual(coordinator.pending_count, 0)
        self.assertFalse(
            coordinator.request(
                RenderIntent(target="dashboard", payload="late", payload_set=True),
                lambda intent: received.append(str(intent.payload)),
            )
        )
        coordinator.end_batch()

        self.assertEqual(received, [])

    def test_explicit_none_payload_clears_previous_payload(self) -> None:
        coordinator = UICoordinator()
        received: list[RenderIntent] = []

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(target="dashboard", payload="value", payload_set=True),
            received.append,
        )
        coordinator.request(
            RenderIntent(target="dashboard", payload=None, payload_set=True),
            received.append,
        )
        coordinator.end_batch()

        self.assertEqual(len(received), 1)
        self.assertIsNone(received[0].payload)
        self.assertTrue(received[0].payload_set)

    def test_node_mismatch_rejects_stale_pending_render(self) -> None:
        coordinator = UICoordinator()
        received: list[RenderIntent] = []

        coordinator.invalidate("component:cpu", generation=0, node_id="node-a")
        coordinator.request(
            RenderIntent(
                target="component:cpu",
                node_id="node-a",
                payload="old",
                payload_set=True,
            ),
            received.append,
        )
        coordinator.invalidate("component:cpu", generation=0, node_id="node-b")
        accepted = coordinator.request(
            RenderIntent(
                target="component:cpu",
                node_id="node-a",
                payload="stale",
                payload_set=True,
            ),
            received.append,
        )

        self.assertFalse(accepted)
        self.assertEqual(coordinator.pending_count, 0)

    def test_node_switch_resets_generation_namespace(self) -> None:
        coordinator = UICoordinator()
        received: list[str] = []

        coordinator.invalidate("component:cpu", generation=5, node_id="node-a")
        coordinator.invalidate("component:cpu", generation=0, node_id="node-b")
        accepted = coordinator.request(
            RenderIntent(
                target="component:cpu",
                generation=1,
                node_id="node-b",
                payload="new",
                payload_set=True,
            ),
            lambda intent: received.append(str(intent.payload)),
        )

        self.assertTrue(accepted)
        self.assertEqual(received, ["new"])

    def test_render_metrics_capture_pending_peak_and_commit_duration(self) -> None:
        coordinator = UICoordinator()

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(target="dashboard", payload="latest", payload_set=True),
            lambda _intent: None,
        )
        coordinator.end_batch()

        self.assertEqual(coordinator.pending_peak, 1)
        self.assertGreaterEqual(coordinator.last_commit_seconds, 0.0)

    def test_render_metrics_count_failed_commits(self) -> None:
        coordinator = UICoordinator()

        coordinator.request(
            RenderIntent(target="dashboard", payload_set=True),
            lambda _intent: (_ for _ in ()).throw(RuntimeError("widget gone")),
        )

        self.assertEqual(coordinator.render_failures, 1)

    def test_render_commits_run_on_the_requesting_ui_thread(self) -> None:
        coordinator = UICoordinator()
        committed_on = []

        coordinator.request(
            RenderIntent(target="dashboard", payload_set=True),
            lambda _intent: committed_on.append(current_thread()),
        )

        self.assertEqual(committed_on, [current_thread()])

    def test_flush_commits_higher_priority_targets_first(self) -> None:
        coordinator = UICoordinator()
        committed: list[str] = []

        coordinator.begin_batch()
        coordinator.request(
            RenderIntent(target="dashboard", priority=1),
            lambda _intent: committed.append("dashboard"),
        )
        coordinator.request(
            RenderIntent(target="scan-status", priority=2),
            lambda _intent: committed.append("scan-status"),
        )
        coordinator.end_batch()

        self.assertEqual(committed, ["scan-status", "dashboard"])


class UICoordinatorTransitionTests(unittest.TestCase):
    """UICoordinator must manage named PendingTransition slots."""

    def _make_coordinator(
        self,
    ) -> "tuple[UICoordinator, list[tuple[int, Any]], list[Any]]":
        scheduled: list[tuple[int, Any]] = []
        cancelled: list[Any] = []
        timer_id = 0

        def fake_schedule(delay: int, callback: Any) -> int:
            nonlocal timer_id
            timer_id += 1
            scheduled.append((delay, callback))
            return timer_id

        def fake_cancel(identifier: Any) -> bool:
            cancelled.append(identifier)
            return True

        coordinator = UICoordinator(schedule=fake_schedule, cancel=fake_cancel)
        return coordinator, scheduled, cancelled

    def test_schedule_transition_fires_after_delay(self) -> None:
        coordinator, scheduled, _ = self._make_coordinator()
        applied: list[str] = []

        coordinator.schedule_transition("status", 200, lambda: applied.append("done"))

        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], 200)
        self.assertEqual(applied, [])

        scheduled[0][1]()  # fire the timer
        self.assertEqual(applied, ["done"])

    def test_schedule_transition_supersedes_pending(self) -> None:
        coordinator, scheduled, cancelled = self._make_coordinator()
        applied: list[str] = []

        coordinator.schedule_transition("status", 200, lambda: applied.append("first"))
        coordinator.schedule_transition("status", 200, lambda: applied.append("second"))

        self.assertEqual(len(cancelled), 1, "first timer must be cancelled")
        self.assertEqual(len(scheduled), 2)

        scheduled[1][1]()  # fire only the second timer
        self.assertEqual(applied, ["second"])

    def test_schedule_transition_different_names_are_independent(self) -> None:
        coordinator, scheduled, cancelled = self._make_coordinator()

        coordinator.schedule_transition("status", 200, lambda: None)
        coordinator.schedule_transition("peer", 100, lambda: None)

        self.assertEqual(len(cancelled), 0, "different names must not cancel each other")
        self.assertEqual(len(scheduled), 2)

    def test_cancel_transition_cancels_the_timer(self) -> None:
        coordinator, scheduled, cancelled = self._make_coordinator()

        coordinator.schedule_transition("status", 200, lambda: None)
        coordinator.cancel_transition("status")

        self.assertEqual(len(scheduled), 1)
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0], 1, "cancel must be called with the scheduled timer id")

    def test_cancel_transition_unknown_name_is_safe(self) -> None:
        coordinator, _, _ = self._make_coordinator()
        coordinator.cancel_transition("nonexistent")  # must not raise

    def test_shutdown_cancels_all_pending_transitions(self) -> None:
        coordinator, scheduled, cancelled = self._make_coordinator()

        coordinator.schedule_transition("status", 200, lambda: None)
        coordinator.schedule_transition("peer", 100, lambda: None)

        coordinator.shutdown()

        self.assertEqual(len(cancelled), 2, "shutdown must cancel all pending transitions")

    def test_no_schedule_callable_means_transitions_are_noop(self) -> None:
        coordinator = UICoordinator()  # no schedule/cancel injected
        coordinator.schedule_transition("status", 200, lambda: None)  # must not raise
        coordinator.cancel_transition("status")  # must not raise
        coordinator.shutdown()  # must not raise

    def test_completion_slot_cancel_on_new_scan(self) -> None:
        """Models the scan-complete → new-scan flow: the hold timer is cancelled."""
        coordinator, scheduled, cancelled = self._make_coordinator()

        coordinator.schedule_transition("completion", 3000, lambda: None)
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][0], 3000)

        coordinator.cancel_transition("completion")

        self.assertEqual(len(cancelled), 1, "cancel must be called when a new scan starts")


if __name__ == "__main__":
    unittest.main()
