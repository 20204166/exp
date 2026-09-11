"""Bounded synthetic workload coverage for the shared multi-node scheduler."""

import unittest
from unittest.mock import Mock

from maintenance.components.coordinator import AppCoordinator
from maintenance.components.peer_connection import PeerConnectionManager
from maintenance.nodes import (
    NodeContext,
    NodeId,
    NodeRegistry,
    node_operation_key,
)
from tests.support.nodes import make_local_context, make_remote_context
from tests.support.scheduling import DeferredRunner


def _remote_context(node_id: str) -> NodeContext:
    return make_remote_context(
        node_id,
        provider=Mock(),
        process_manager=Mock(),
        file_manager=Mock(),
        scheduler=Mock(),
        coordinator=Mock(),
    )


class MultiNodeConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = DeferredRunner()
        self.deliveries: list[object] = []
        self.coordinator = AppCoordinator(
            runner=self.runner,
            deliver=self.deliveries.append,
        )

    def _run(self, key: str, value: str) -> int | None:
        return self.coordinator.run(
            key,
            lambda _cancel, _progress: value,
        )

    def _deliver_all(self) -> None:
        while self.deliveries:
            callback = self.deliveries.pop(0)
            callback()  # type: ignore[operator]

    def test_local_result_is_not_blocked_by_three_slow_peers(self) -> None:
        slow_keys = tuple(
            node_operation_key(NodeId(f"peer-{i}"), "snapshot") for i in range(3)
        )
        local_key = node_operation_key(NodeId("local"), "snapshot")
        results: list[tuple[str, str]] = []

        for key in slow_keys:
            self.coordinator.run(
                key,
                lambda cancel, _progress: (
                    "slow" if not cancel.is_set() else "cancelled"
                ),
                on_result=lambda operation, value: results.append((operation, value)),
            )
        self.coordinator.run(
            local_key,
            lambda _cancel, _progress: "local",
            on_result=lambda operation, value: results.append((operation, value)),
        )

        self.assertEqual(self.runner.pending, 4)
        self.runner.run(3)
        self._deliver_all()

        self.assertEqual(results, [(local_key, "local")])
        self.assertTrue(all(self.coordinator.in_flight(key) for key in slow_keys))
        self.assertFalse(self.coordinator.in_flight(local_key))

    def test_burst_manual_actions_and_periodic_refresh_have_one_rerun_per_key(
        self,
    ) -> None:
        keys = (
            node_operation_key(NodeId("local"), "snapshot"),
            node_operation_key(NodeId("peer-a"), "component:cpu"),
            node_operation_key(NodeId("peer-b"), "process"),
            node_operation_key(NodeId("peer-c"), "storage"),
        )
        for key in keys:
            self.assertIsNotNone(self._run(key, key))
            for _ in range(25):
                self.assertIsNone(self._run(key, "coalesced"))

        self.assertEqual(self.runner.pending, len(keys))
        self.assertTrue(
            all(self.coordinator.state(key).rerun_requested for key in keys)
        )
        self.assertEqual(
            len({key for key, _state in self.coordinator._states.items()}), len(keys)
        )

        for _ in keys:
            self.runner.run()
            self._deliver_all()
        self.assertEqual(self.runner.pending, len(keys))
        self.assertTrue(all(self.coordinator.in_flight(key) for key in keys))

        # A second burst while each coalesced rerun is active does not grow work.
        for key in keys:
            for _ in range(25):
                self.assertIsNone(self._run(key, "second-coalesced"))
        self.assertEqual(self.runner.pending, len(keys))

    def test_shutdown_and_switching_reject_stale_deliveries(self) -> None:
        key = node_operation_key(NodeId("peer-a"), "node_snapshot")
        results: list[str] = []
        self.coordinator.run(
            key,
            lambda _cancel, _progress: "stale",
            on_result=lambda _key, value: results.append(value),
        )
        self.coordinator.cancel(key)
        self.runner.run()
        self._deliver_all()

        self.assertEqual(results, [])
        self.assertFalse(self.coordinator.in_flight(key))
        self.assertIsNone(self.coordinator.state(key).cancel_event)

        replacement = node_operation_key(NodeId("peer-b"), "node_snapshot")
        self.assertNotEqual(key, replacement)
        self.coordinator.run(replacement, lambda _cancel, _progress: "replacement")
        self.coordinator.cancel_all()
        self.runner.run()
        self._deliver_all()
        self.coordinator.shutdown()
        self.assertFalse(self.coordinator.has_pending_work)

    def test_peer_reconciliation_uses_shared_keys_without_per_node_workers_or_timers(
        self,
    ) -> None:
        registry = NodeRegistry(
            make_local_context(
                provider=Mock(),
                process_manager=Mock(),
                file_manager=Mock(),
                scheduler=Mock(),
                coordinator=Mock(),
            )
        )
        peers = [_remote_context(f"peer-{i}") for i in range(4)]
        for peer in peers:
            registry.register_context(peer)

        manager = PeerConnectionManager(
            registry=registry,
            coordinator=self.coordinator,
            connect=lambda _context, _cancel, _progress: object(),
            clock=lambda: 0.0,
        )
        manager.reconcile(0.0)

        expected = {node_operation_key(peer.node_id, "connect") for peer in peers}
        self.assertEqual(set(self.coordinator._states), expected)
        self.assertEqual(self.runner.pending, len(peers))
        self.assertNotIn("_thread", vars(manager))
        self.assertNotIn("_timer", vars(manager))
        self.assertEqual(manager.reconcile(0.0), None)


if __name__ == "__main__":
    unittest.main()
