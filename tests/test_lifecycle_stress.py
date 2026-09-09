"""Bounded lifecycle/stress tests for the scheduler and coordinators.

These prove that repeated cycles keep the coordinator and scheduler state
bounded (one worker per key, one rerun bit, cleared subscribers, settled
cancel events) without claiming memory-leak proof. All timing is synthetic
(deferred runners / explicit ``now`` values), so the tests are deterministic.
"""

import unittest

from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
    ScanCoordinator,
)
from tests.support.scheduling import DeferredRunner

KEYS = ("cpu", "network", "memory", "gpu", "storage", "battery")


class ComponentRefreshSchedulerStressTests(unittest.TestCase):
    def test_thousand_operations_keep_state_bounded(self) -> None:
        scheduler = ComponentRefreshScheduler()
        keys = set(KEYS)

        for step in range(1000):
            key = KEYS[step % len(KEYS)]
            now = float(step)
            operation = step % 7

            if operation == 0:
                scheduler.begin(key, now)
            elif operation == 1:
                scheduler.finish(key)
            elif operation == 2:
                scheduler.pause(key)
            elif operation == 3:
                scheduler.resume(key)
            elif operation == 4:
                scheduler.request_refresh(key)
            elif operation == 5:
                scheduler.set_interval(key, 2000 + step, now)
            elif operation == 6:
                scheduler.mark_all_refreshed(now)

            self.assertTrue(all(key in keys for key in scheduler.intervals))
            self.assertEqual(len(scheduler.intervals), len(keys))

        # finish is idempotent and never leaves a stale in-flight lease.
        scheduler = ComponentRefreshScheduler()
        for _ in range(10):
            scheduler.request_refresh("cpu")
            self.assertTrue(scheduler.begin("cpu", 0.0))
            scheduler.finish("cpu")
            scheduler.finish("cpu")
        self.assertFalse(scheduler.in_flight("cpu"))

    def test_stuck_component_does_not_block_others(self) -> None:
        scheduler = ComponentRefreshScheduler()
        scheduler.begin("cpu", 0.0)  # cpu never finishes
        cycles = {"memory": 0, "storage": 0}

        for cycle in range(200):
            for key in ("memory", "storage"):
                scheduler.finish(key)
                scheduler.request_refresh(key)
                if scheduler.begin(key, float(cycle)):
                    cycles[key] += 1

        self.assertTrue(scheduler.in_flight("cpu"))
        self.assertGreater(cycles["memory"], 150)
        self.assertGreater(cycles["storage"], 150)


class ScanCoordinatorStressTests(unittest.TestCase):
    def test_five_hundred_generations_with_duplicate_triggers(self) -> None:
        coordinator = ScanCoordinator()

        for _ in range(500):
            generation, started = coordinator.begin()
            self.assertTrue(started)
            for _ in range(20):
                duplicate_generation, duplicate_started = coordinator.begin()
                self.assertEqual(duplicate_generation, generation)
                self.assertFalse(duplicate_started)

            finished, rerun_requested = coordinator.finish(generation)
            self.assertTrue(finished)
            self.assertTrue(rerun_requested)
            self.assertFalse(coordinator.active)

            # A stale finish for a previous generation is always dropped.
            stale_finished, _stale_rerun = coordinator.finish(generation - 1)
            self.assertFalse(stale_finished)

        self.assertFalse(coordinator.active)
        self.assertFalse(coordinator.rerun_requested)


class AppCoordinatorStressTests(unittest.TestCase):
    def _make(self) -> tuple[AppCoordinator, DeferredRunner]:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        return coordinator, runner

    def test_two_hundred_cycles_keep_state_bounded(self) -> None:
        coordinator, runner = self._make()
        results: dict[str, int] = {}

        for cycle in range(200):
            key = KEYS[cycle % len(KEYS)]
            coordinator.run(
                key,
                lambda _event, _progress, value=cycle: value,  # type: ignore[misc]
            )
            if runner.pending:
                runner.run_next()
            self.assertLessEqual(len(coordinator._states), len(KEYS))
            self.assertEqual(
                coordinator.has_pending_work,
                any(state.in_flight for state in coordinator._states.values()),
            )
            last = coordinator.last_result(key)
            if last is not None:
                results[key] = last

        self.assertEqual(len(coordinator._states), len(KEYS))

        # Drain any remaining work; every run settles with no in-flight lease.
        while runner.pending:
            runner.run_next()
        self.assertFalse(coordinator.has_pending_work)
        for key in KEYS:
            state = coordinator.state(key)
            self.assertIsNone(state.cancel_event)
            self.assertFalse(state.in_flight)
            self.assertIsNotNone(coordinator.last_result(key))

    def test_cancel_is_idempotent_for_owner_and_subscribers(self) -> None:
        coordinator, runner = self._make()
        owner_notices: list[str] = []
        subscriber_wakes: list[object] = []

        coordinator.run(
            "storage",
            lambda _event, _progress: ["x"],
            on_error=lambda _key, message: owner_notices.append(message),
        )
        coordinator.subscribe(
            "storage", lambda _key, result: subscriber_wakes.append(result)
        )

        for _ in range(10):
            coordinator.cancel("storage", cancellation_message="cancelled")

        self.assertEqual(owner_notices, ["cancelled"])
        self.assertEqual(subscriber_wakes, [None])
        self.assertTrue(coordinator.in_flight("storage"))

        runner.run_next()  # worker releases the lease
        self.assertFalse(coordinator.in_flight("storage"))
        self.assertEqual(owner_notices, ["cancelled"])

    def test_repeated_unsubscribe_with_distinct_bound_methods(self) -> None:
        """A closed dialog's fresh bound-method access must remove its subscription."""

        class DummyDialog:
            def __init__(self, coordinator: AppCoordinator) -> None:
                self.coordinator = coordinator

            def _on_shared_result(self, _key: str, _result: object) -> None:
                pass

            def _close(self) -> None:
                self.coordinator.unsubscribe("storage", self._on_shared_result)

        coordinator, _runner = self._make()
        dialog = DummyDialog(coordinator)
        coordinator.subscribe("storage", dialog._on_shared_result)

        dialog._close()

        state = coordinator.state("storage")
        self.assertTrue(state.subscribers in (None, []))

    def test_two_hundred_open_close_cycles_clear_subscribers(self) -> None:
        coordinator, _runner = self._make()

        class DummyDialog:
            def __init__(self, coordinator: AppCoordinator) -> None:
                self.coordinator = coordinator

            def _on_shared_result(self, _key: str, _result: object) -> None:
                pass

        for _ in range(200):
            dialog = DummyDialog(coordinator)
            coordinator.subscribe("storage", dialog._on_shared_result)
            coordinator.unsubscribe("storage", dialog._on_shared_result)

        state = coordinator.state("storage")
        self.assertTrue(state.subscribers in (None, []))
        self.assertEqual(len(coordinator._states), 1)

    def test_cancel_all_wakes_each_tracked_operation_once(self) -> None:
        coordinator, runner = self._make()
        notices: list[tuple[str, str]] = []

        coordinator.run(
            "storage",
            lambda _event, _progress: ["x"],
            on_error=lambda key, message: notices.append((key, message)),
        )
        coordinator.run(
            "process",
            lambda _event, _progress: ["y"],
            on_error=lambda key, message: notices.append((key, message)),
        )

        coordinator.cancel_all("stopped")

        self.assertEqual(notices, [("storage", "stopped"), ("process", "stopped")])
        runner.run_next()
        runner.run_next()
        self.assertFalse(coordinator.has_pending_work)


if __name__ == "__main__":
    unittest.main()
