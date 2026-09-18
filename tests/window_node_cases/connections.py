"""Window node connection test cases."""

import time
import unittest
from dataclasses import replace
from typing import Any
from unittest.mock import Mock

from maintenance.cluster import (
    ClusterState,
    decode_invite_blob,
    encode_invite_blob,
    trusted_node_record,
)
from maintenance.components.cluster_roles import ClusterRole, RoleAssignment
from maintenance.components.coordinator import AppCoordinator
from maintenance.nodes import NodeId
from maintenance.ui import window_discovery as ui_window_discovery
from maintenance.ui import window_node_actions
from tests.support.scheduling import DeferredRunner
from tests.test_window_nodes import _make_window, _trusted_context


class WindowNodeConnectionTests(unittest.TestCase):
    def _window(self, runner: DeferredRunner) -> Any:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState(
            local_node_id="local",
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.0.2.10",
                    port=5000,
                    secret="secret",
                    transport_fingerprint="tls-pin",
                ),
            ),
        )
        window._coordinator = AppCoordinator(
            runner=runner,
            deliver=lambda callback: callback(),
        )
        return window

    @staticmethod
    def _provider(result: dict[str, Any]) -> Mock:
        provider = Mock()
        provider.hello.return_value = result
        return provider

    def test_test_connection_submits_node_qualified_coordinator_run(self) -> None:
        runner = DeferredRunner()
        window = self._window(runner)
        provider_cls = Mock(return_value=self._provider({"node_id": "peer-a"}))

        window_node_actions.test_connection(
            window,
            "peer-a",
            provider_cls=provider_cls,
            transport_cls=Mock,
        )

        key = "node:peer-a:test_connection"
        self.assertEqual(runner.pending, 1)
        self.assertTrue(window._coordinator.in_flight(key))

    def test_test_connection_passes_persisted_tls_fingerprint(self) -> None:
        runner = DeferredRunner()
        window = self._window(runner)
        record = replace(
            window._cluster_state.trusted_nodes[0],
            transport_fingerprint="tls-pin",
        )
        window._cluster_state = replace(
            window._cluster_state,
            trusted_nodes=(record,),
        )
        transport_cls = Mock()
        provider_cls = Mock(return_value=self._provider({"node_id": "peer-a"}))

        window_node_actions.test_connection(
            window,
            "peer-a",
            provider_cls=provider_cls,
            transport_cls=transport_cls,
        )
        runner.run_next()

        transport_cls.assert_called_once_with(
            "192.0.2.10", 5000, expected_fingerprint="tls-pin"
        )

    def test_test_connection_delivers_success(self) -> None:
        runner = DeferredRunner()
        window = self._window(runner)
        messages = Mock()
        provider_cls = Mock(
            return_value=self._provider({"node_id": "peer-a", "app_version": "x"})
        )

        window_node_actions.test_connection(
            window,
            "peer-a",
            messagebox_module=messages,
            provider_cls=provider_cls,
            transport_cls=Mock,
        )
        runner.run_next()

        messages.showinfo.assert_called_once()
        messages.showerror.assert_not_called()

    def test_test_connection_delivers_provider_error(self) -> None:
        runner = DeferredRunner()
        window = self._window(runner)
        messages = Mock()
        provider_cls = Mock(side_effect=RuntimeError("connection refused"))

        window_node_actions.test_connection(
            window,
            "peer-a",
            messagebox_module=messages,
            provider_cls=provider_cls,
            transport_cls=Mock,
        )
        runner.run_next()

        messages.showerror.assert_called_once()
        self.assertIn("connection refused", messages.showerror.call_args.args[1])

    def test_cancelled_test_connection_drops_late_success(self) -> None:
        runner = DeferredRunner()
        window = self._window(runner)
        messages = Mock()
        provider_cls = Mock(
            return_value=self._provider({"node_id": "peer-a", "app_version": "x"})
        )
        key = "node:peer-a:test_connection"

        window_node_actions.test_connection(
            window,
            "peer-a",
            messagebox_module=messages,
            provider_cls=provider_cls,
            transport_cls=Mock,
        )
        cancel_event = window._coordinator.state(key).cancel_event
        self.assertIsNotNone(cancel_event)
        window._coordinator.cancel(key)
        self.assertTrue(cancel_event.is_set())  # type: ignore[union-attr]
        runner.run_next()

        messages.showinfo.assert_not_called()

    def test_stale_test_connection_result_cannot_replace_cancelled_run(self) -> None:
        runner = DeferredRunner()
        window = self._window(runner)
        messages = Mock()
        first = self._provider({"node_id": "peer-a", "app_version": "old"})
        replacement = self._provider(
            {"node_id": "peer-a", "app_version": "replacement"}
        )
        provider_cls = Mock(side_effect=[first, replacement])
        key = "node:peer-a:test_connection"

        window_node_actions.test_connection(
            window,
            "peer-a",
            messagebox_module=messages,
            provider_cls=provider_cls,
            transport_cls=Mock,
        )
        window._coordinator.cancel(key)
        window_node_actions.test_connection(
            window,
            "peer-a",
            messagebox_module=messages,
            provider_cls=provider_cls,
            transport_cls=Mock,
        )

        runner.run_next()
        messages.showinfo.assert_not_called()
        self.assertEqual(runner.pending, 1)
        runner.run_next()

        messages.showinfo.assert_called_once()
        self.assertIn("replacement", messages.showinfo.call_args.args[1])

    def _join_window(self, runner: DeferredRunner) -> Any:
        window = self._window(runner)
        state = ClusterState.create_local(local_node_id="local")
        state.trusted_nodes = (
            trusted_node_record(
                node_id="peer-a",
                display_name="Peer A",
                hostname="peer-a",
                host="192.0.2.10",
                port=5000,
                secret="secret",
                transport_fingerprint="tls-pin",
            ),
        )
        window._cluster_state = state

        def save(saved: Any) -> bool:
            window._cluster_state = saved
            return True

        window._save_cluster_state = Mock(side_effect=save)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        return window

    @staticmethod
    def _remote_invite_blob(coordinator_id: str = "peer-a") -> str:
        remote_state = ClusterState.create_local(local_node_id=coordinator_id)
        invite = remote_state.create_invite(target_node_id="local")
        return encode_invite_blob(invite)

    def test_join_cluster_via_invite_adopts_the_returned_fence(self) -> None:
        runner = DeferredRunner()
        window = self._join_window(runner)
        blob = self._remote_invite_blob()
        provider = Mock()
        provider.consume_invite.return_value = {
            "target_node_id": "local",
            "expires_at": time.time() + 300.0,
            "cluster_id": "remote-cluster",
            "coordinator_id": "peer-a",
            "epoch": 3,
            "fencing_token": "fence-token",
        }
        provider_cls = Mock(return_value=provider)

        window_node_actions.join_cluster_via_invite(
            window, "peer-a", blob, provider_cls=provider_cls, transport_cls=Mock
        )
        runner.run_next()

        window._nodes_error.assert_not_called()
        self.assertEqual(window._cluster_state.cluster_id, "remote-cluster")
        epoch = window._cluster_state.coordinator_epoch
        assert epoch is not None
        self.assertEqual(epoch.coordinator_id, NodeId("peer-a"))
        self.assertEqual(epoch.epoch, 3)
        self.assertEqual(epoch.fencing_token, "fence-token")
        self.assertEqual(
            window._cluster_state.role_assignments,
            (
                RoleAssignment(
                    frozenset({ClusterRole.COORDINATOR, ClusterRole.WORKER}),
                    node_id=NodeId("peer-a"),
                ),
                RoleAssignment(
                    frozenset({ClusterRole.WORKER}), node_id=NodeId("local")
                ),
            ),
        )
        self.assertEqual(window._cluster_state.capability_grants, ())
        self.assertEqual(window._cluster_state.promotion_epochs, frozenset())

    def test_join_cluster_via_invite_rejects_a_non_solo_local_cluster(self) -> None:
        runner = DeferredRunner()
        window = self._join_window(runner)
        original = window._cluster_state
        original.role_assignments = original.role_assignments + (
            RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("other")),
        )
        blob = self._remote_invite_blob()
        provider_cls = Mock()

        window_node_actions.join_cluster_via_invite(
            window, "peer-a", blob, provider_cls=provider_cls, transport_cls=Mock
        )

        window._nodes_error.assert_called_once()
        provider_cls.assert_not_called()
        self.assertIs(window._cluster_state, original)

    def test_join_cluster_via_invite_rejects_a_malformed_blob(self) -> None:
        runner = DeferredRunner()
        window = self._join_window(runner)
        provider_cls = Mock()

        window_node_actions.join_cluster_via_invite(
            window,
            "peer-a",
            "not-a-real-invite",
            provider_cls=provider_cls,
            transport_cls=Mock,
        )

        window._nodes_error.assert_called_once()
        provider_cls.assert_not_called()

    def test_join_cluster_via_invite_rejects_unknown_target(self) -> None:
        runner = DeferredRunner()
        window = self._join_window(runner)
        blob = self._remote_invite_blob(coordinator_id="ghost")
        provider_cls = Mock()

        window_node_actions.join_cluster_via_invite(
            window, "ghost", blob, provider_cls=provider_cls, transport_cls=Mock
        )

        window._nodes_error.assert_called_once()
        provider_cls.assert_not_called()

    def test_join_cluster_via_invite_target_error_leaves_state_unchanged(self) -> None:
        runner = DeferredRunner()
        window = self._join_window(runner)
        original = window._cluster_state
        blob = self._remote_invite_blob()
        provider_cls = Mock(side_effect=RuntimeError("cluster identity is invalid"))

        window_node_actions.join_cluster_via_invite(
            window, "peer-a", blob, provider_cls=provider_cls, transport_cls=Mock
        )
        runner.run_next()

        self.assertIs(window._cluster_state, original)
        window._nodes_error.assert_called_once()

    def test_join_cluster_via_invite_save_failure_reports_error(self) -> None:
        runner = DeferredRunner()
        window = self._join_window(runner)
        original = window._cluster_state
        window._save_cluster_state = Mock(return_value=False)
        blob = self._remote_invite_blob()
        provider = Mock()
        provider.consume_invite.return_value = {
            "target_node_id": "local",
            "expires_at": time.time() + 300.0,
            "cluster_id": "remote-cluster",
            "coordinator_id": "peer-a",
            "epoch": 3,
            "fencing_token": "fence-token",
        }
        provider_cls = Mock(return_value=provider)

        window_node_actions.join_cluster_via_invite(
            window, "peer-a", blob, provider_cls=provider_cls, transport_cls=Mock
        )
        runner.run_next()

        self.assertIs(window._cluster_state, original)
        window._nodes_error.assert_called_once()

    def test_join_cluster_via_invite_includes_coordinator_in_role_assignments(
        self,
    ) -> None:
        runner = DeferredRunner()
        window = self._join_window(runner)
        blob = self._remote_invite_blob()
        provider = Mock()
        provider.consume_invite.return_value = {
            "target_node_id": "local",
            "expires_at": time.time() + 300.0,
            "cluster_id": "remote-cluster",
            "coordinator_id": "peer-a",
            "epoch": 3,
            "fencing_token": "fence-token",
        }

        window_node_actions.join_cluster_via_invite(
            window,
            "peer-a",
            blob,
            provider_cls=Mock(return_value=provider),
            transport_cls=Mock,
        )
        runner.run_next()

        assignments = {
            a.node_id.value: a
            for a in window._cluster_state.role_assignments
            if a.node_id is not None
        }
        self.assertIn("peer-a", assignments)
        self.assertIn(ClusterRole.COORDINATOR, assignments["peer-a"].roles)

    def test_create_cluster_invite_requires_local_coordinator_role(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = (
            RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("local")),
        )
        window._cluster_state = state
        window._nodes_error = Mock()
        window._save_cluster_state = Mock(return_value=True)

        blob = window_node_actions.create_cluster_invite(window)

        self.assertIsNone(blob)
        window._nodes_error.assert_called_once()
        window._save_cluster_state.assert_not_called()

    def test_create_cluster_invite_returns_a_decodable_blob(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        window._cluster_state = state
        window._nodes_error = Mock()
        window._save_cluster_state = Mock(return_value=True)

        blob = window_node_actions.create_cluster_invite(window)

        self.assertIsNotNone(blob)
        assert blob is not None
        decoded = decode_invite_blob(blob)
        self.assertEqual(decoded.cluster_id, state.cluster_id)
        window._save_cluster_state.assert_called_once()
        window._nodes_error.assert_not_called()

    def test_create_cluster_invite_rolls_back_on_save_failure(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        window._cluster_state = state
        window._nodes_error = Mock()
        window._save_cluster_state = Mock(return_value=False)

        blob = window_node_actions.create_cluster_invite(window)

        self.assertIsNone(blob)
        self.assertEqual(window._cluster_state.active_invites, ())
        window._nodes_error.assert_called_once()

    def test_reconcile_does_not_promote_when_local_is_coordinator(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(
                frozenset({ClusterRole.SUBCOORDINATOR}),
                node_id=NodeId("peer-a"),
            ),
        )
        epoch = state.coordinator_epoch
        assert epoch is not None
        state.coordinator_epoch = replace(
            epoch,
            issued_at=time.time() - 130.0,
            lease_expires_at=time.time() - 10.0,
        )
        window._cluster_state = state
        manager = Mock()
        manager.promote_if_due.return_value = None
        window._peer_connection_manager = manager
        window._cluster_store = Mock()
        window._schedule_peer_reconciliation = Mock()
        window.snapshot = None

        window._reconcile_peer_connections()

        manager.promote_if_due.assert_not_called()

    def test_reconcile_renews_local_coordinator_lease(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        epoch = state.coordinator_epoch
        assert epoch is not None
        state.coordinator_epoch = replace(epoch, lease_expires_at=time.time() + 15.0)
        window._cluster_state = state
        manager = Mock()
        manager.renew_cluster_lease = Mock(
            side_effect=lambda state_, **kwargs: setattr(
                state_,
                "coordinator_epoch",
                replace(
                    state_.coordinator_epoch,
                    lease_expires_at=time.time() + 120.0,
                ),
            )
        )
        window._peer_connection_manager = manager
        window._cluster_store = Mock()
        window._schedule_peer_reconciliation = Mock()
        window.snapshot = None

        epoch_before = state.coordinator_epoch
        assert epoch_before is not None
        before = epoch_before.lease_expires_at
        window._reconcile_peer_connections()
        epoch_after = state.coordinator_epoch
        assert epoch_after is not None
        after = epoch_after.lease_expires_at

        self.assertGreater(after, before)
        manager.renew_cluster_lease.assert_called_once()

    def test_can_connect_peer_requires_identity_fingerprint(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        context = window._node_registry.context(NodeId("peer-a"))
        context.descriptor = replace(context.descriptor, identity_fingerprint=None)
        state = ClusterState(
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.0.2.10",
                    port=5000,
                    secret="secret",
                    transport_fingerprint="tls-pin",
                ),
            )
        )
        window._cluster_state = state

        self.assertFalse(ui_window_discovery.can_connect_peer(window, context))


class PeerOfflineDebounceTests(unittest.TestCase):
    def _window_with_peer(self) -> tuple[Any, Any]:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="0%", host_label="peer"),
            start_discovery=False,
        )
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        context = window._node_registry.context(NodeId("peer-a"))
        return window, context

    def test_detach_peer_schedules_transition_not_immediate_refresh(self) -> None:
        window, context = self._window_with_peer()
        render = Mock()
        window._render_coordinator = Mock(return_value=render)

        ui_window_discovery.detach_peer(window, context)

        window._refresh_nodes_page.assert_not_called()
        render.schedule_transition.assert_called_once_with(
            "peer-offline:peer-a",
            300,
            window._refresh_nodes_page,
        )

    def test_detach_peer_falls_back_to_immediate_refresh_without_coordinator(
        self,
    ) -> None:
        window, context = self._window_with_peer()
        window._render_coordinator = Mock(return_value=None)

        ui_window_discovery.detach_peer(window, context)

        window._refresh_nodes_page.assert_called_once()

    def test_attach_peer_cancels_offline_transition_before_refresh(self) -> None:
        window, context = self._window_with_peer()
        render = Mock()
        window._render_coordinator = Mock(return_value=render)
        context.descriptor = replace(context.descriptor, identity_fingerprint="fp-1")
        provider = Mock()
        cancelled: list[str] = []
        refreshed: list[int] = []
        render.cancel_transition.side_effect = lambda name: cancelled.append(name)
        window._refresh_nodes_page.side_effect = lambda: refreshed.append(
            len(cancelled)
        )

        ui_window_discovery.attach_peer(window, context, (provider, frozenset(), "fp-1"))

        self.assertEqual(cancelled, ["peer-offline:peer-a"])
        self.assertEqual(refreshed, [1], "refresh must happen after cancel")

    def test_detach_peer_skips_local_context(self) -> None:
        from tests.support.nodes import make_local_context

        window, _ = self._window_with_peer()
        local = make_local_context()
        render = Mock()
        window._render_coordinator = Mock(return_value=render)

        ui_window_discovery.detach_peer(window, local)

        render.schedule_transition.assert_not_called()
        window._refresh_nodes_page.assert_not_called()
