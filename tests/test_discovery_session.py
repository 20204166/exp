"""Focused tests for application-level discovery lifecycle delegation."""

import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.cluster import ClusterState
from maintenance.components.discovery_session import DiscoverySession
from maintenance.nodes import NodeContext, NodeRegistry, local_node_descriptor


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
        context = NodeContext(
            descriptor=local_node_descriptor(),
            provider=object(),
            process_manager=object(),
            file_manager=object(),
            scheduler=object(),
            coordinator=object(),
        )
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
        self.schedule = Mock(side_effect=lambda _delay, _callback: "timer-1")
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

    def test_stop_cancels_timer_before_coordinator_and_is_idempotent(self) -> None:
        self.session.start()
        self.events.clear()

        self.session.stop()
        self.session.stop()

        self.assertEqual(
            self.events,
            ["timer.cancel", "coordinator.stop", "timer.cancel", "coordinator.stop"],
        )


if __name__ == "__main__":
    unittest.main()
