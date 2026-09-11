"""Focused tests for application-level discovery lifecycle delegation."""

import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.cluster import ClusterState
from maintenance.components.discovery_session import DiscoverySession
from maintenance.nodes import NodeRegistry
from tests.support.nodes import make_local_context


class FakeDiscovery:
    available = True
    unavailable_reason = None

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.on_event: Any = None

    def start(self) -> bool:
        self.events.append("discovery.start")
        return True

    def stop(self) -> None:
        self.events.append("discovery.stop")


class DiscoverySessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[str] = []
        context = make_local_context()
        self.registry = NodeRegistry(context)
        self.state = ClusterState(local_identity_persisted=False)
        self.coordinator = Mock()
        self.coordinator.start_discovery.side_effect = self._start_coordinator
        self.coordinator.discovery_tick.side_effect = lambda: self.events.append(
            "coordinator.tick"
        )
        self.coordinator.stop_discovery.side_effect = lambda: self.events.append(
            "coordinator.stop"
        )
        self.discovery = FakeDiscovery(self.events)
        self.scheduled: list[tuple[int, Any]] = []

        def schedule(delay: int, callback: Any) -> str:
            timer_id = f"timer-{len(self.scheduled) + 1}"
            self.scheduled.append((delay, callback))
            return timer_id

        self.schedule = Mock(side_effect=schedule)
        self.cancel = Mock(
            side_effect=lambda _timer: self.events.append("timer.cancel")
        )
        self.session = DiscoverySession(
            coordinator=self.coordinator,
            registry=self.registry,
            get_cluster_state=lambda: self.state,
            set_cluster_state=self._set_state,
            save_cluster_state=self._save_state,
            schedule_timer=self.schedule,
            cancel_timer=self.cancel,
            start_background_poll=lambda: self.events.append("poll.start"),
            on_candidate=lambda _candidate: None,
            on_lost=lambda _node_id: None,
            discovery_factory=lambda *_args, **_kwargs: self.discovery,
            on_stabilized=lambda: self.events.append("discovery.stabilized"),
        )

    def _set_state(self, state: ClusterState) -> None:
        self.events.append("state.set")
        self.state = state

    def _save_state(self, _state: ClusterState) -> bool:
        self.events.append("state.save")
        return True

    def _start_coordinator(self, *_args: Any, **_kwargs: Any) -> bool:
        self.events.append("coordinator.start")
        return self.discovery.start()

    def test_start_orders_persistence_coordinator_timer_and_poll(self) -> None:
        result = self.session.start()

        self.assertTrue(result.started)
        self.assertEqual(
            self.events,
            [
                "state.save",
                "state.set",
                "coordinator.start",
                "discovery.start",
                "poll.start",
            ],
        )
        self.schedule.assert_called_once()
        self.assertEqual(self.session.timer_id, "timer-1")

    def test_tick_delegates_then_replaces_timer(self) -> None:
        self.session.start()
        self.events.clear()

        self.session.tick()

        self.assertEqual(self.events, ["coordinator.tick"])
        self.assertEqual(self.schedule.call_count, 2)

    def test_discovery_events_schedule_one_bounded_stabilization(self) -> None:
        self.session.start()
        handlers = self.coordinator.start_discovery.call_args.kwargs

        handlers["on_candidate"](object())
        handlers["on_lost"]("peer")

        self.assertEqual(self.schedule.call_count, 2)
        self.assertEqual(self.scheduled[1][0], 100)
        self.scheduled[1][1]()
        self.assertEqual(self.events[-1], "discovery.stabilized")

    def test_stop_cancels_pending_stabilization(self) -> None:
        self.session.start()
        handlers = self.coordinator.start_discovery.call_args.kwargs
        handlers["on_candidate"](object())

        self.session.stop()

        self.cancel.assert_any_call("timer-2")

    def test_restart_rejects_stale_stabilization_callback(self) -> None:
        self.session.start()
        first_handlers = self.coordinator.start_discovery.call_args.kwargs
        first_handlers["on_candidate"](object())
        stale_callback = self.scheduled[1][1]
        self.session.stop()

        self.session.start()
        self.events.clear()
        stale_callback()

        self.assertNotIn("discovery.stabilized", self.events)

    def test_none_timer_id_still_coalesces_stabilization(self) -> None:
        self.session.start()
        self.schedule.side_effect = lambda _delay, _callback: None
        handlers = self.coordinator.start_discovery.call_args.kwargs

        handlers["on_candidate"](object())
        handlers["on_lost"]("peer")

        self.assertEqual(self.schedule.call_count, 2)

    def test_stop_cancels_timer_before_coordinator_and_is_idempotent(self) -> None:
        self.session.start()
        self.events.clear()

        self.session.stop()
        self.session.stop()

        self.assertEqual(
            self.events,
            ["timer.cancel", "coordinator.stop", "timer.cancel", "coordinator.stop"],
        )

    def test_presence_change_notifies_peer_lifecycle_hook(self) -> None:
        presence_changed = Mock()
        session = DiscoverySession(
            coordinator=self.coordinator,
            registry=self.registry,
            get_cluster_state=lambda: self.state,
            set_cluster_state=self._set_state,
            save_cluster_state=self._save_state,
            schedule_timer=self.schedule,
            cancel_timer=self.cancel,
            start_background_poll=Mock(),
            on_candidate=Mock(),
            on_lost=Mock(),
            discovery_factory=lambda *_args, **_kwargs: self.discovery,
            on_presence_changed=presence_changed,
        )
        session.start()
        handlers = self.coordinator.start_discovery.call_args.kwargs

        handlers["on_candidate"](object())
        handlers["on_lost"]("peer")

        self.assertEqual(presence_changed.call_count, 2)


if __name__ == "__main__":
    unittest.main()
