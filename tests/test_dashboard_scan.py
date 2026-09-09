import unittest
from unittest.mock import Mock

from maintenance.components import DashboardScanLifecycle, ScanCoordinator


class DashboardScanLifecycleTests(unittest.TestCase):
    def make_lifecycle(self) -> tuple[DashboardScanLifecycle, list[tuple[object, ...]]]:
        events: list[tuple[object, ...]] = []
        timers = iter(("timeout", "grace"))

        def schedule_timer(*args: object) -> str:
            events.append(("schedule", *args))
            return next(timers)

        lifecycle = DashboardScanLifecycle(
            coordinator=ScanCoordinator(),
            is_closing=lambda: False,
            schedule_timer=schedule_timer,
            cancel_timer=lambda identifier: events.append(("cancel", identifier)),
            show_timeout_error=lambda message: events.append(("error", message)),
            schedule_rerun=lambda: events.append(("rerun",)),
            timeout_milliseconds=30,
            grace_milliseconds=10,
            timeout_message="timeout",
        )
        return lifecycle, events

    def test_start_orders_state_timer_then_worker_and_coalesces_rerun(self) -> None:
        lifecycle, events = self.make_lifecycle()
        worker = Mock()

        lifecycle.start(
            lambda generation, event: events.append(("started", generation, event)),
            worker,
        )
        lifecycle.start(Mock(), worker)

        self.assertEqual(events[0][0], "started")
        self.assertEqual(events[1][0], "schedule")
        worker.assert_called_once()
        self.assertTrue(lifecycle.coordinator.rerun_requested)
        self.assertEqual(lifecycle.coordinator.generation, 1)

    def test_timeout_reports_immediately_and_worker_completion_releases_lease(
        self,
    ) -> None:
        lifecycle, events = self.make_lifecycle()
        lifecycle.start(Mock(), Mock())
        cancel_event = lifecycle.cancel_event
        lifecycle.handle_timeout(1)

        self.assertIsNotNone(cancel_event)
        assert cancel_event is not None
        self.assertTrue(cancel_event.is_set())
        self.assertEqual(events[-1], ("error", "timeout"))
        self.assertTrue(lifecycle.coordinator.active)
        lifecycle.resolve_completed_worker()
        self.assertFalse(lifecycle.coordinator.active)
        self.assertIsNone(lifecycle.timed_out_generation)

    def test_late_generation_cannot_resolve_current_scan(self) -> None:
        lifecycle, _events = self.make_lifecycle()
        lifecycle.start(Mock(), Mock())
        lifecycle.coordinator.cancel()
        lifecycle.start(Mock(), Mock())

        self.assertEqual(lifecycle.resolution_for_generation(1), None)
        self.assertTrue(lifecycle.coordinator.active)
        self.assertEqual(lifecycle.coordinator.generation, 3)


if __name__ == "__main__":
    unittest.main()
