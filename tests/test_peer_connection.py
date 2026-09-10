"""Focused tests for trusted-peer connection lifecycle and retry policy."""

import unittest
from unittest.mock import Mock

from maintenance.components.coordinator import AppCoordinator
from maintenance.components.peer_connection import PeerConnectionManager
from maintenance.nodes import (
    ConnectionState,
    NodeConnectionStatus,
    NodeContext,
    NodeDescriptor,
    NodeId,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
    PeerFailure,
    RetryState,
    local_node_descriptor,
)


def remote_context(node_id: str = "peer") -> NodeContext:
    return NodeContext(
        descriptor=NodeDescriptor(
            id=NodeId(node_id),
            display_name=node_id,
            hostname=f"{node_id}.example",
            is_local=False,
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.UNKNOWN,
            capabilities=frozenset(),
        ),
        provider=None,
        process_manager=None,
        file_manager=None,
        scheduler=None,
        coordinator=None,
    )


class PeerConnectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = NodeRegistry(
            NodeContext(
                descriptor=local_node_descriptor(),
                provider=Mock(),
                process_manager=Mock(),
                file_manager=Mock(),
                scheduler=Mock(),
                coordinator=Mock(),
            )
        )
        self.peer = remote_context()
        self.registry.register_context(self.peer)
        self.clock = 0.0
        self.connect = Mock(return_value=object())
        self.coordinator = AppCoordinator(
            runner=self._run, deliver=lambda callback: callback()
        )
        self.manager = PeerConnectionManager(
            registry=self.registry,
            coordinator=self.coordinator,
            connect=self.connect,
            clock=lambda: self.clock,
            jitter=lambda attempt: attempt * 0.25,
        )

    def _run(self, worker: object) -> None:
        worker()  # type: ignore[operator]

    def test_trusted_peer_can_be_offline_without_losing_trust(self) -> None:
        self.peer.connection = ConnectionState.offline("timeout", now=10.0)

        self.assertEqual(self.peer.descriptor.trust, NodeTrustState.TRUSTED)
        self.assertEqual(self.peer.connection.status, NodeConnectionStatus.OFFLINE)

    def test_retry_is_capped_and_identity_failure_stops_automatic_retry(self) -> None:
        state = RetryState()
        state.record_failure(
            PeerFailure.TIMEOUT,
            now=10.0,
            jitter=lambda _attempt: 0.5,
            base_seconds=2.0,
            max_seconds=5.0,
            max_backoff_exponent=4,
        )
        self.assertEqual(state.next_attempt_at, 12.5)
        for _ in range(10):
            state.record_failure(PeerFailure.TIMEOUT, now=20.0, max_seconds=5.0)
        self.assertEqual(state.next_attempt_at, 25.0)

        state.record_failure(PeerFailure.IDENTITY_CHANGED, now=30.0)
        self.assertIsNone(state.next_attempt_at)
        self.assertFalse(state.automatic_retry)

    def test_reconcile_starts_one_keyed_attempt_and_resets_retry_on_success(
        self,
    ) -> None:
        self.assertIsNone(self.manager.reconcile(0.0))

        self.assertEqual(self.connect.call_count, 1)
        self.assertEqual(self.peer.connection.status, NodeConnectionStatus.ONLINE)
        self.assertEqual(self.peer.retry.attempt, 0)
        self.assertEqual(self.coordinator.generation("node:peer:connect"), 1)

    def test_transient_failure_returns_bounded_deadline(self) -> None:
        self.manager.reconcile(0.0)
        generation = self.peer.connection_generation
        self.clock = 1.0
        self.assertTrue(
            self.manager.failed(
                self.peer.node_id, generation, PeerFailure.ROUTE_FAILURE, "no route"
            )
        )

        self.assertEqual(self.peer.connection.status, NodeConnectionStatus.OFFLINE)
        self.assertEqual(self.manager.reconcile(1.0), 2.25)
        self.assertEqual(self.connect.call_count, 1)
        self.assertIsNone(self.manager.reconcile(2.25))
        self.assertEqual(self.connect.call_count, 2)

    def test_on_error_callback_classifies_authentication_failure_without_retry(
        self,
    ) -> None:
        self.connect.side_effect = RuntimeError("remote authentication failed")

        self.assertIsNone(self.manager.reconcile(0.0))

        self.assertEqual(
            self.peer.connection.status, NodeConnectionStatus.AUTHENTICATION_FAILED
        )
        self.assertFalse(self.peer.retry.automatic_retry)
        self.assertIsNone(self.peer.retry.next_attempt_at)

    def test_cancel_invalidates_late_completion_and_shutdown_stops_reconnect(
        self,
    ) -> None:
        self.coordinator = AppCoordinator(runner=lambda _worker: None)
        self.manager = PeerConnectionManager(
            registry=self.registry,
            coordinator=self.coordinator,
            connect=self.connect,
            clock=lambda: self.clock,
        )
        self.manager.reconcile(0.0)
        generation = self.peer.connection_generation
        cancel_event = self.coordinator.state("node:peer:connect").cancel_event
        self.manager.cancel(self.peer.node_id)
        self.assertIsNotNone(cancel_event)
        assert cancel_event is not None
        self.assertTrue(cancel_event.is_set())
        self.assertFalse(self.manager.complete(self.peer.node_id, generation))

        self.manager.shutdown()
        self.assertFalse(self.manager.complete(self.peer.node_id, generation + 1))


if __name__ == "__main__":
    unittest.main()
