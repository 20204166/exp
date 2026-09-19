"""Focused tests for trusted-peer connection lifecycle and retry policy."""

import unittest
from unittest.mock import Mock

from maintenance.components.coordinator import AppCoordinator
from maintenance.components.peer_connection import PeerConnectionManager
from maintenance.nodes import (
    ConnectionState,
    NodeConnectionStatus,
    NodeContext,
    NodeId,
    NodeRegistry,
    NodeTrustState,
    PeerFailure,
    RetryState,
)
from maintenance.remote_support.protocol import RemoteAuthError, RemoteTransportError
from tests.support.nodes import make_local_context, make_remote_context


def remote_context(node_id: str = "peer") -> NodeContext:
    return make_remote_context(node_id)


class PeerConnectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = NodeRegistry(
            make_local_context(
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

    def test_discovery_loss_marks_online_peer_offline_and_retries(self) -> None:
        self.manager.reconcile(0.0)

        self.assertTrue(self.manager.mark_disconnected(self.peer.node_id))
        self.assertEqual(self.peer.connection.status, NodeConnectionStatus.OFFLINE)
        self.assertIsNotNone(self.peer.retry.next_attempt_at)

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

    def test_manual_disconnect_suppresses_reconcile(self) -> None:
        self.manager.disconnect_manual(self.peer.node_id)

        self.assertIsNone(self.manager.reconcile(0.0))
        self.assertEqual(self.connect.call_count, 0)
        self.assertTrue(self.manager.is_manual_disconnected(self.peer.node_id))

    def test_reconnect_restores_automatic_reconcile(self) -> None:
        self.manager.disconnect_manual(self.peer.node_id)
        self.manager.reconnect(self.peer.node_id)

        self.assertFalse(self.manager.is_manual_disconnected(self.peer.node_id))
        self.assertIsNone(self.manager.reconcile(0.0))
        self.assertEqual(self.connect.call_count, 1)

    def test_manual_disconnect_cancels_pending_attempt(self) -> None:
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

        self.manager.disconnect_manual(self.peer.node_id)

        self.assertIsNotNone(cancel_event)
        assert cancel_event is not None
        self.assertTrue(cancel_event.is_set())
        self.assertFalse(self.manager.complete(self.peer.node_id, generation))

    def test_disconnect_manual_local_node_is_noop(self) -> None:
        local_id = self.registry.local_id()
        assert local_id is not None
        self.manager.disconnect_manual(local_id)
        self.assertTrue(self.manager.is_manual_disconnected(local_id))

    def test_disconnect_manual_unknown_node_does_not_raise(self) -> None:
        self.manager.disconnect_manual(NodeId("ghost"))
        self.assertTrue(self.manager.is_manual_disconnected(NodeId("ghost")))

    def test_disconnect_manual_suppresses_reconnect_after_deadline(self) -> None:
        self.manager.disconnect_manual(self.peer.node_id)
        self.clock = 100.0
        self.assertIsNone(self.manager.reconcile(100.0))
        self.assertEqual(self.connect.call_count, 0)

    def test_reconnect_then_complete_clears_disconnect_state(self) -> None:
        self.manager.disconnect_manual(self.peer.node_id)
        self.manager.reconnect(self.peer.node_id)
        self.assertIsNone(self.manager.reconcile(0.0))
        self.assertFalse(self.manager.is_manual_disconnected(self.peer.node_id))
        self.assertEqual(self.connect.call_count, 1)

    def test_disconnect_manual_is_idempotent(self) -> None:
        self.manager.disconnect_manual(self.peer.node_id)
        self.manager.disconnect_manual(self.peer.node_id)
        self.assertTrue(self.manager.is_manual_disconnected(self.peer.node_id))
        self.assertIsNone(self.manager.reconcile(0.0))
        self.assertEqual(self.connect.call_count, 0)


class TrustSurvivalTests(unittest.TestCase):
    """TRUST != CONNECTION.

    A transient inability to reach a previously trusted peer MUST NOT destroy
    trust.  These tests lock in that invariant so it cannot regress silently.
    """

    def setUp(self) -> None:
        self.registry = NodeRegistry(
            make_local_context(
                provider=Mock(),
                process_manager=Mock(),
                file_manager=Mock(),
                scheduler=Mock(),
                coordinator=Mock(),
            )
        )
        self.peer = make_remote_context("trusted-peer")
        self.registry.register_context(self.peer)
        self.revoke_calls: list[tuple[NodeContext, PeerFailure]] = []
        self.coordinator = AppCoordinator(
            runner=lambda worker: worker(),
            deliver=lambda callback: callback(),
        )
        self.manager = PeerConnectionManager(
            registry=self.registry,
            coordinator=self.coordinator,
            connect=Mock(return_value=object()),
            on_failed=lambda context, failure: self.revoke_calls.append(
                (context, failure)
            ),
        )

    def _initial_trust(self) -> NodeTrustState:
        return self.peer.descriptor.trust

    def test_remote_transport_error_does_not_revoke_trust(self) -> None:
        self.manager._connect = Mock(  # type: ignore[attr-defined]
            side_effect=RemoteTransportError(
                "remote transport failed: TimeoutError: timed out"
            )
        )
        initial_trust = self._initial_trust()

        self.manager.reconcile(0.0)

        self.assertEqual(self.peer.descriptor.trust, initial_trust)
        self.assertEqual(self.peer.connection.status, NodeConnectionStatus.OFFLINE)
        self.assertEqual(len(self.revoke_calls), 1)
        self.assertEqual(self.revoke_calls[0][1], PeerFailure.TIMEOUT)

    def test_remote_auth_error_does_not_revoke_trust(self) -> None:
        # "certificate fingerprint" now classifies as AUTHENTICATION_FAILED
        # (matches the "certificate" marker added to classify_peer_failure).
        self.manager._connect = Mock(  # type: ignore[attr-defined]
            side_effect=RemoteAuthError("peer certificate fingerprint changed")
        )
        initial_trust = self._initial_trust()

        self.manager.reconcile(0.0)

        self.assertEqual(self.peer.descriptor.trust, initial_trust)
        self.assertEqual(
            self.peer.connection.status, NodeConnectionStatus.AUTHENTICATION_FAILED
        )
        self.assertFalse(
            self.peer.retry.automatic_retry,
            "auth failure should stop automatic retry to avoid hammering the peer",
        )
        self.assertEqual(len(self.revoke_calls), 1)
        self.assertEqual(self.revoke_calls[0][1], PeerFailure.AUTHENTICATION_FAILED)

    def test_on_failed_callback_receives_failure_but_trust_state_is_unchanged(
        self,
    ) -> None:
        """on_failed signals the caller (e.g. detach_peer) but MUST NOT revoke trust."""
        self.manager._connect = Mock(  # type: ignore[attr-defined]
            side_effect=RemoteTransportError(
                "remote transport failed: ConnectionRefusedError: [Errno 111] Connection refused"
            )
        )
        self.manager.reconcile(0.0)

        failure_context, failure_reason = self.revoke_calls[0]
        self.assertIs(failure_context, self.peer)
        self.assertIn(
            failure_reason,
            {
                PeerFailure.CONNECTION_REFUSED,
                PeerFailure.ROUTE_FAILURE,
                PeerFailure.TIMEOUT,
            },
        )
        self.assertEqual(failure_context.descriptor.trust, NodeTrustState.TRUSTED)

    def test_multiple_transport_failures_do_not_revoke_trust(self) -> None:
        self.manager._connect = Mock(  # type: ignore[attr-defined]
            side_effect=RemoteTransportError(
                "remote transport failed: TimeoutError: timed out"
            )
        )

        for tick in (0.0, 2.0, 4.0, 8.0, 16.0):
            self.manager.reconcile(tick)

        self.assertEqual(self.peer.descriptor.trust, NodeTrustState.TRUSTED)


if __name__ == "__main__":
    unittest.main()
