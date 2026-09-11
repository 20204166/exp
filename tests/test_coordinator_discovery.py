"""AppCoordinator discovery-lifecycle tests.

These prove the coordinator owns discovery start/stop/event-delivery without
real threads or a LAN: the discovery component is a fake driven by the test,
and delivery is synchronous so registry updates are deterministic.
"""

import unittest
from typing import Any

from maintenance.components.coordinator import AppCoordinator
from maintenance.nodes import DiscoveredNodeCandidate
from tests.support.nodes import make_candidate


class FakeDiscovery:
    def __init__(self, *, available: bool = True) -> None:
        self.available_flag = available
        self.on_event: Any = None
        self.started = False
        self.stopped = False
        self.unavailable_reason_value = None if available else "no transport"
        self.expiries = 0

    @property
    def available(self) -> bool:
        return self.available_flag

    @property
    def unavailable_reason(self) -> str | None:
        return self.unavailable_reason_value

    def start(self) -> bool:
        self.started = True
        return self.available_flag

    def stop(self) -> None:
        self.stopped = True

    def expire_stale(self) -> None:
        self.expiries += 1

    def emit(self, kind: str, payload: Any) -> None:
        if self.on_event is not None:
            self.on_event(kind, payload)


class RetryDiscovery(FakeDiscovery):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_start = True

    def start(self) -> bool:
        self.started = True
        if self.fail_next_start:
            self.fail_next_start = False
            return False
        return True


def _candidate() -> DiscoveredNodeCandidate:
    return make_candidate(last_seen=1.0)


class AppCoordinatorDiscoveryTests(unittest.TestCase):
    def _make(self) -> tuple[AppCoordinator, list[Any], list[Any]]:
        delivered: list[Any] = []
        activity: list[Any] = []

        def deliver(callback: Any) -> None:
            callback()
            delivered.append("delivered")

        coordinator = AppCoordinator(
            deliver=deliver,
            on_activity=lambda: activity.append(True),
        )
        return coordinator, delivered, activity

    def test_start_discovery_runs_and_bridges_candidate_events(self) -> None:
        coordinator, delivered, _activity = self._make()
        discovery = FakeDiscovery()
        candidates: list[Any] = []
        lost: list[str] = []

        self.assertTrue(
            coordinator.start_discovery(
                discovery,
                on_candidate=lambda candidate: candidates.append(candidate),
                on_lost=lambda node_id: lost.append(node_id),
            )
        )
        self.assertTrue(discovery.started)

        discovery.emit("candidate", _candidate())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].stable_id, "peer-a")

        discovery.emit("lost", "peer-a")
        self.assertEqual(lost, ["peer-a"])
        self.assertEqual(delivered, ["delivered", "delivered"])

    def test_start_discovery_is_idempotent(self) -> None:
        coordinator, _delivered, _activity = self._make()
        first = FakeDiscovery()
        second = FakeDiscovery()

        self.assertTrue(
            coordinator.start_discovery(
                first, on_candidate=lambda _c: None, on_lost=lambda _n: None
            )
        )
        self.assertFalse(
            coordinator.start_discovery(
                second, on_candidate=lambda _c: None, on_lost=lambda _n: None
            )
        )
        self.assertTrue(first.started)
        self.assertFalse(second.started)

    def test_unavailable_discovery_keeps_app_in_local_only_mode(self) -> None:
        coordinator, _delivered, _activity = self._make()
        discovery = FakeDiscovery(available=False)

        self.assertFalse(
            coordinator.start_discovery(
                discovery, on_candidate=lambda _c: None, on_lost=lambda _n: None
            )
        )
        self.assertFalse(coordinator.has_pending_work)
        self.assertFalse(coordinator.in_flight("snapshot:dashboard"))

    def test_failed_start_releases_lifecycle_ownership_for_retry(self) -> None:
        coordinator, _delivered, _activity = self._make()
        failed = RetryDiscovery()
        replacement = FakeDiscovery()

        self.assertFalse(
            coordinator.start_discovery(
                failed, on_candidate=lambda _c: None, on_lost=lambda _n: None
            )
        )
        self.assertIsNone(coordinator.discovery)
        self.assertIsNone(failed.on_event)
        self.assertTrue(
            coordinator.start_discovery(
                replacement, on_candidate=lambda _c: None, on_lost=lambda _n: None
            )
        )

    def test_stop_discovery_is_idempotent_and_clears_bridge(self) -> None:
        coordinator, delivered, _activity = self._make()
        discovery = FakeDiscovery()
        coordinator.start_discovery(
            discovery, on_candidate=lambda _c: None, on_lost=lambda _n: None
        )
        coordinator.stop_discovery()
        coordinator.stop_discovery()
        self.assertTrue(discovery.stopped)

        # Late events after stop must not reach the registry handlers.
        discovery.emit("candidate", _candidate())
        self.assertEqual(delivered, [])

    def test_queued_event_is_dropped_after_stop_and_restart(self) -> None:
        queued: list[Any] = []
        coordinator = AppCoordinator(deliver=queued.append)
        discovery = FakeDiscovery()
        candidates: list[Any] = []

        self.assertTrue(
            coordinator.start_discovery(
                discovery,
                on_candidate=candidates.append,
                on_lost=lambda _node_id: None,
            )
        )
        discovery.emit("candidate", _candidate())
        self.assertEqual(len(queued), 1)
        coordinator.stop_discovery()
        self.assertTrue(
            coordinator.start_discovery(
                discovery,
                on_candidate=candidates.append,
                on_lost=lambda _node_id: None,
            )
        )

        queued.pop(0)()
        self.assertEqual(candidates, [])
        discovery.emit("candidate", _candidate())
        queued.pop(0)()
        self.assertEqual(len(candidates), 1)

    def test_discovery_tick_expires_stale_peers(self) -> None:
        coordinator, _delivered, _activity = self._make()
        discovery = FakeDiscovery()
        coordinator.start_discovery(
            discovery, on_candidate=lambda _c: None, on_lost=lambda _n: None
        )
        coordinator.discovery_tick()
        self.assertEqual(discovery.expiries, 1)

    def test_post_routes_through_delivery_and_keeps_poll_alive(self) -> None:
        coordinator, delivered, activity = self._make()
        coordinator.post(lambda: delivered.append("posted"))
        self.assertEqual(delivered, ["posted", "delivered"])
        self.assertEqual(activity, [True])

    def test_post_coalesced_delivers_latest_callback_per_key(self) -> None:
        queued: list[Any] = []
        activity: list[bool] = []
        coordinator = AppCoordinator(
            deliver=queued.append,
            on_activity=lambda: activity.append(True),
        )
        delivered: list[str] = []

        coordinator.post_coalesced("discovery", lambda: delivered.append("old"))
        coordinator.post_coalesced("discovery", lambda: delivered.append("latest"))
        coordinator.post_coalesced("status", lambda: delivered.append("status"))
        self.assertEqual(len(queued), 2)

        queued.pop(0)()
        queued.pop(0)()

        self.assertEqual(delivered, ["latest", "status"])
        self.assertEqual(len(activity), 3)

    def test_post_coalesced_keeps_one_deferred_wrapper_per_key(self) -> None:
        queued: list[Any] = []
        coordinator = AppCoordinator(deliver=queued.append)
        delivered: list[int] = []

        for value in range(100):

            def callback(value: int = value) -> None:
                delivered.append(value)

            coordinator.post_coalesced("discovery", callback)

        self.assertEqual(len(queued), 1)
        queued.pop()()
        self.assertEqual(delivered, [99])

    def test_clear_invalidates_queued_coalesced_callback(self) -> None:
        queued: list[Any] = []
        coordinator = AppCoordinator(deliver=queued.append)
        delivered: list[str] = []

        coordinator.post_coalesced("discovery", lambda: delivered.append("stale"))
        coordinator.clear("discovery")
        coordinator.post_coalesced("discovery", lambda: delivered.append("fresh"))
        self.assertEqual(len(queued), 2)

        queued.pop(0)()
        self.assertEqual(delivered, [])

        queued.pop(0)()
        self.assertEqual(delivered, ["fresh"])


if __name__ == "__main__":
    unittest.main()
