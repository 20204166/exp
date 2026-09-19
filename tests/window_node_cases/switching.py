"""Window node switching test cases."""

import threading
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

from maintenance.cluster import ClusterState, PeerGrantRecord, trusted_node_record
from maintenance.components.cluster_roles import ClusterRole, RoleAssignment
from maintenance.components.coordinator import AppCoordinator, ComponentRefreshScheduler
from maintenance.nodes import (
    LOCAL_NODE_ID,
    ConnectionState,
    NodeCapability,
    NodeId,
    NodePermission,
    NodeStatus,
    NodeTrustState,
    node_operation_key,
)
from maintenance.remote import RemoteAuthError, RemoteRequest
from maintenance.ui import window_discovery as ui_window_discovery
from maintenance.ui import window_node_actions
from maintenance.ui.render_coordinator import UICoordinator
from maintenance.ui.window_supports import node_specs
from tests.support.models import make_snapshot
from tests.support.nodes import make_remote_context
from tests.support.scheduling import DeferredRunner
from tests.test_window_nodes import (
    _make_window,
    _summary,
    _trusted_context,
)
from window import AppWindow


def _role_request(
    op: str, caller_node_id: NodeId, params: dict[str, Any]
) -> RemoteRequest:
    return RemoteRequest(
        node_id=NodeId("local"),
        caller_node_id=caller_node_id,
        op=op,
        params=params,
        request_id="test-request",
        nonce="test-nonce",
        timestamp=0.0,
    )


# Preserve the extracted case bodies exactly as they were in the facade.
# fmt: off
class WindowNodeSwitchingTests(unittest.TestCase):
    def test_role_revoke_removes_role_trust_grant_and_provider(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("peer-a")),
        )
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
        state.peer_grants = (
            PeerGrantRecord(
                caller_node_id="peer-a",
                secret="a" * 64,
                permissions=frozenset({NodePermission.DASHBOARD_READ}),
            ),
        )
        window._cluster_state = state

        def save_state(saved: ClusterState) -> bool:
            window._cluster_state = saved
            return True

        window._save_cluster_state = Mock(side_effect=save_state)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._invalidate_node_render_targets = Mock()
        provider = window._node_registry.context(NodeId("peer-a")).provider
        window._coordinator = AppCoordinator(runner=lambda w: w(), deliver=lambda cb: cb())

        window_node_actions.revoke_node(
            window, "peer-a",
            messagebox_module=Mock(return_value=True),
            provider_cls=Mock(return_value=Mock(revoke_worker=Mock(return_value={"ok": True}))),
            transport_cls=Mock,
        )

        peer_assignment = next(
            item
            for item in window._cluster_state.role_assignments
            if item.node_id == NodeId("peer-a")
        )
        self.assertTrue(peer_assignment.revoked)
        self.assertIsNone(window._cluster_state.record("peer-a"))
        self.assertIsNone(window._cluster_state.grant("peer-a"))
        provider.invalidate.assert_called_once_with()
        window._refresh_nodes_page.assert_called()
        window._refresh_cluster_page.assert_called()
        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))

    def test_revoke_removes_node_from_cluster_connection_specs(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("peer-a")),
        )
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

        def save_state(saved: ClusterState) -> bool:
            window._cluster_state = saved
            return True

        window._save_cluster_state = Mock(side_effect=save_state)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._invalidate_node_render_targets = Mock()
        window._coordinator = AppCoordinator(runner=lambda w: w(), deliver=lambda cb: cb())

        specs = node_specs.cluster_node_specs(window._node_registry)
        self.assertIn("peer-a", {spec.node_id for spec in specs})

        window_node_actions.revoke_node(
            window, "peer-a",
            messagebox_module=Mock(return_value=True),
            provider_cls=Mock(return_value=Mock(revoke_worker=Mock(return_value={"ok": True}))),
            transport_cls=Mock,
        )

        specs = node_specs.cluster_node_specs(window._node_registry)
        self.assertNotIn("peer-a", {spec.node_id for spec in specs})
        self.assertIn("local", {spec.node_id for spec in specs})

    def test_revoke_already_revoked_assignment_removes_connection(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(
                frozenset({ClusterRole.WORKER}),
                node_id=NodeId("peer-a"),
                revoked=True,
            ),
        )
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

        def save_state(saved: ClusterState) -> bool:
            window._cluster_state = saved
            return True

        window._save_cluster_state = Mock(side_effect=save_state)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._invalidate_node_render_targets = Mock()

        specs = node_specs.cluster_node_specs(window._node_registry)
        self.assertIn("peer-a", {spec.node_id for spec in specs})

        window_node_actions.revoke_node(
            window, "peer-a", messagebox_module=Mock(return_value=True)
        )

        window._nodes_error.assert_not_called()
        self.assertIsNone(window._cluster_state.record("peer-a"))
        specs = node_specs.cluster_node_specs(window._node_registry)
        self.assertNotIn("peer-a", {spec.node_id for spec in specs})
        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))

    def test_handle_remove_job_clears_target_assignment(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("peer-a")),
        )
        window._cluster_state = state

        def save_state(saved: ClusterState) -> bool:
            window._cluster_state = saved
            return True

        window._save_cluster_state = Mock(side_effect=save_state)
        request = _role_request(
            "remove_job",
            NodeId("local"),
            {
                "target_node_id": "peer-a",
                "cluster_id": state.cluster_id,
                "epoch": 1,
                "fencing_token": "t",
            },
        )

        result = ui_window_discovery.handle_role_request(window, request)

        self.assertEqual(result, {"ok": True})
        peer = next(
            item
            for item in window._cluster_state.role_assignments
            if item.node_id == NodeId("peer-a")
        )
        self.assertFalse(peer.has_active_job)

    def test_handle_remove_connection_detaches_caller(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("peer-a")),
        )
        window._cluster_state = state
        manager = Mock()
        window._peer_connection_manager = manager
        request = _role_request(
            "remove_connection",
            NodeId("peer-a"),
            {
                "target_node_id": "peer-a",
                "cluster_id": state.cluster_id,
                "epoch": 1,
                "fencing_token": "t",
            },
        )

        result = ui_window_discovery.handle_role_request(window, request)

        self.assertEqual(result, {"ok": True})
        manager.disconnect_manual.assert_called_once_with(NodeId("peer-a"))

    def test_handle_remove_connection_rejects_wrong_target(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        window._cluster_state = state
        request = _role_request(
            "remove_connection",
            NodeId("peer-a"),
            {
                "target_node_id": "other",
                "cluster_id": state.cluster_id,
                "epoch": 1,
                "fencing_token": "t",
            },
        )

        with self.assertRaises(RemoteAuthError):
            ui_window_discovery.handle_role_request(window, request)

    def test_upload_gate_idle_worker_uploads_one_in_five(self) -> None:
        from maintenance.ui.window_discovery import should_upload_job

        self.assertTrue(should_upload_job(1, True))
        self.assertTrue(should_upload_job(3, True))
        self.assertTrue(should_upload_job(5, True))
        self.assertFalse(should_upload_job(1, False))
        self.assertFalse(should_upload_job(2, False))
        self.assertFalse(should_upload_job(3, False))
        self.assertFalse(should_upload_job(4, False))
        self.assertTrue(should_upload_job(5, False))
        self.assertTrue(should_upload_job(10, False))

    def test_open_remote_node_does_not_enroll_into_cluster(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
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
        window._activate_remote_node = Mock()
        window._show_dashboard_page = Mock()
        before_assignments = state.role_assignments
        before_grants = state.peer_grants

        window_node_actions.open_cluster_node(window, "peer-a")

        self.assertEqual(window._cluster_state.role_assignments, before_assignments)
        self.assertEqual(window._cluster_state.peer_grants, before_grants)
        window._activate_remote_node.assert_not_called()
        window._show_dashboard_page.assert_called()

    def test_revoke_confirmation_cancel_keeps_state(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
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
        window._save_cluster_state = Mock(return_value=True)
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        messagebox_module = Mock()
        messagebox_module.askyesno.return_value = False

        window_node_actions.revoke_node(
            window, "peer-a", messagebox_module=messagebox_module
        )

        self.assertIsNotNone(window._cluster_state.record("peer-a"))
        window._save_cluster_state.assert_not_called()

    def test_remove_job_worker_actor_is_rejected(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState(
            role_assignments=(
                RoleAssignment(
                    frozenset({ClusterRole.WORKER}), node_id=NodeId("local")
                ),
                RoleAssignment(
                    frozenset({ClusterRole.WORKER}), node_id=NodeId("peer-a")
                ),
            ),
            coordinator_epoch=None,
        )
        window._cluster_state = state
        window._save_cluster_state = Mock(return_value=True)
        window._nodes_status = Mock()
        window._nodes_error = Mock()

        window_node_actions.remove_job_node(
            window, "peer-a", messagebox_module=Mock(return_value=True)
        )

        window._nodes_error.assert_called_once()

    def test_handle_remove_job_worker_actor_is_rejected(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState(
            role_assignments=(
                RoleAssignment(
                    frozenset({ClusterRole.WORKER}), node_id=NodeId("local")
                ),
                RoleAssignment(
                    frozenset({ClusterRole.WORKER}), node_id=NodeId("peer-a")
                ),
            ),
            coordinator_epoch=None,
        )
        window._cluster_state = state
        window._save_cluster_state = Mock(return_value=True)
        request = _role_request(
            "remove_job",
            NodeId("local"),
            {
                "target_node_id": "peer-a",
                "cluster_id": "c",
                "epoch": 0,
                "fencing_token": "t",
            },
        )

        with self.assertRaises(ValueError):
            ui_window_discovery.handle_role_request(window, request)

    def test_handle_remove_job_unenrolled_target_is_rejected(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        window._cluster_state = state
        window._save_cluster_state = Mock(return_value=True)
        request = _role_request(
            "remove_job",
            NodeId("local"),
            {
                "target_node_id": "ghost",
                "cluster_id": "c",
                "epoch": 1,
                "fencing_token": "t",
            },
        )

        with self.assertRaises(ValueError):
            ui_window_discovery.handle_role_request(window, request)

    def test_handle_remove_connection_unenrolled_caller_is_rejected(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        window._cluster_state = state
        request = _role_request(
            "remove_connection",
            NodeId("ghost"),
            {
                "target_node_id": "ghost",
                "cluster_id": "c",
                "epoch": 1,
                "fencing_token": "t",
            },
        )

        with self.assertRaises(RemoteAuthError):
            ui_window_discovery.handle_role_request(window, request)

    def test_handle_role_request_rejects_caller_without_role_assignment(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = ()
        window._cluster_state = state
        request = _role_request(
            "remove_connection",
            NodeId("local"),
            {
                "target_node_id": "local",
                "cluster_id": state.cluster_id,
                "epoch": 1,
                "fencing_token": "t",
            },
        )

        with self.assertRaises(RemoteAuthError):
            ui_window_discovery.handle_role_request(window, request)

    def test_consume_invite_admits_caller_as_worker_and_returns_full_fence(
        self,
    ) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        invite = state.create_invite(target_node_id="peer-a")
        window._cluster_state = state

        def save_state(saved: ClusterState) -> bool:
            window._cluster_state = saved
            return True

        window._save_cluster_state = Mock(side_effect=save_state)
        request = _role_request(
            "consume_invite",
            NodeId("peer-a"),
            {
                "token": invite.token,
                "cluster_id": invite.cluster_id,
                "epoch": invite.epoch,
                "fencing_token": invite.fencing_token,
            },
        )

        result = ui_window_discovery.handle_role_request(window, request)

        assert state.coordinator_epoch is not None
        self.assertEqual(
            result,
            {
                "target_node_id": "peer-a",
                "expires_at": invite.expires_at,
                "cluster_id": state.cluster_id,
                "coordinator_id": "local",
                "epoch": state.coordinator_epoch.epoch,
                "fencing_token": state.coordinator_epoch.fencing_token,
            },
        )
        joined = next(
            item
            for item in window._cluster_state.role_assignments
            if item.node_id == NodeId("peer-a")
        )
        self.assertEqual(joined.roles, frozenset({ClusterRole.WORKER}))
        self.assertFalse(joined.revoked)

    def test_consume_invite_is_idempotent_for_an_already_admitted_member(
        self,
    ) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("peer-a")),
        )
        invite = state.create_invite(target_node_id="peer-a")
        window._cluster_state = state
        window._save_cluster_state = Mock(return_value=True)
        request = _role_request(
            "consume_invite",
            NodeId("peer-a"),
            {
                "token": invite.token,
                "cluster_id": invite.cluster_id,
                "epoch": invite.epoch,
                "fencing_token": invite.fencing_token,
            },
        )

        result = ui_window_discovery.handle_role_request(window, request)

        self.assertEqual(result["target_node_id"], "peer-a")

    def test_consume_invite_re_admits_a_role_revoked_member(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(
                frozenset({ClusterRole.WORKER}), node_id=NodeId("peer-a"), revoked=True
            ),
        )
        invite = state.create_invite(target_node_id="peer-a")
        window._cluster_state = state

        def save_state(saved: ClusterState) -> bool:
            window._cluster_state = saved
            return True

        window._save_cluster_state = Mock(side_effect=save_state)
        request = _role_request(
            "consume_invite",
            NodeId("peer-a"),
            {
                "token": invite.token,
                "cluster_id": invite.cluster_id,
                "epoch": invite.epoch,
                "fencing_token": invite.fencing_token,
            },
        )

        ui_window_discovery.handle_role_request(window, request)

        joined = next(
            item
            for item in window._cluster_state.role_assignments
            if item.node_id == NodeId("peer-a")
        )
        self.assertFalse(joined.revoked)

    def test_consume_invite_rejects_when_local_node_lost_coordinator_role(
        self,
    ) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        invite = state.create_invite(target_node_id="peer-a")
        state.role_assignments = (
            RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("local")),
        )
        window._cluster_state = state
        window._save_cluster_state = Mock(return_value=True)
        request = _role_request(
            "consume_invite",
            NodeId("peer-a"),
            {
                "token": invite.token,
                "cluster_id": invite.cluster_id,
                "epoch": invite.epoch,
                "fencing_token": invite.fencing_token,
            },
        )

        with self.assertRaises(RemoteAuthError):
            ui_window_discovery.handle_role_request(window, request)
        self.assertFalse(
            any(
                item.node_id == NodeId("peer-a")
                for item in window._cluster_state.role_assignments
            )
        )
        window._save_cluster_state.assert_not_called()

    def test_consume_invite_save_failure_leaves_invite_and_roles_unchanged(
        self,
    ) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        invite = state.create_invite(target_node_id="peer-a")
        window._cluster_state = state
        window._save_cluster_state = Mock(return_value=False)
        request = _role_request(
            "consume_invite",
            NodeId("peer-a"),
            {
                "token": invite.token,
                "cluster_id": invite.cluster_id,
                "epoch": invite.epoch,
                "fencing_token": invite.fencing_token,
            },
        )

        with self.assertRaises(RemoteAuthError):
            ui_window_discovery.handle_role_request(window, request)

        self.assertEqual(len(window._cluster_state.active_invites), 1)
        self.assertFalse(
            any(
                item.node_id == NodeId("peer-a")
                for item in window._cluster_state.role_assignments
            )
        )

    def test_remove_connection_on_manual_host_is_allowed(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        manager = Mock()
        window._peer_connection_manager = manager
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        window._manual_host_ids = {"peer-a"}

        window_node_actions.remove_connection_node(
            window, "peer-a", messagebox_module=Mock(return_value=True)
        )

        manager.disconnect_manual.assert_called_once_with(NodeId("peer-a"))

    def test_upload_gate_idle_worker_uploads_two_of_ten(self) -> None:
        from maintenance.ui.window_discovery import should_upload_job

        uploads = [
            sequence for sequence in range(1, 11) if should_upload_job(sequence, False)
        ]
        self.assertEqual(uploads, [5, 10])

    def test_revoke_trusted_node_without_role_falls_back_to_trusted_revoke(
        self,
    ) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
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

        def save_state(saved: ClusterState) -> bool:
            window._cluster_state = saved
            return True

        window._save_cluster_state = Mock(side_effect=save_state)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._invalidate_node_render_targets = Mock()

        window_node_actions.revoke_node(
            window, "peer-a", messagebox_module=Mock(return_value=True)
        )

        self.assertIsNone(window._cluster_state.record("peer-a"))
        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))

    def test_remove_connection_confirms_and_detaches(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        manager = Mock()
        window._peer_connection_manager = manager
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        node = NodeId("peer-a")
        context = window._node_registry.context(node)
        context.provider = Mock()

        window_node_actions.remove_connection_node(
            window, "peer-a", messagebox_module=Mock(return_value=True)
        )

        manager.disconnect_manual.assert_called_once_with(node)
        self.assertIsNone(context.provider)
        window._refresh_cluster_page.assert_called()

    def test_remove_connection_cancel_keeps_relationship(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        manager = Mock()
        window._peer_connection_manager = manager
        node = NodeId("peer-a")
        context = window._node_registry.context(node)
        provider = context.provider
        messagebox_module = Mock()
        messagebox_module.askyesno.return_value = False

        window_node_actions.remove_connection_node(
            window, "peer-a", messagebox_module=messagebox_module
        )

        manager.disconnect_manual.assert_not_called()
        self.assertIs(context.provider, provider)

    def test_remove_job_confirms_and_clears_assignment(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(
                frozenset({ClusterRole.WORKER}),
                node_id=NodeId("peer-a"),
                has_active_job=True,
            ),
        )
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
        window._coordinator = AppCoordinator(runner=lambda w: w(), deliver=lambda cb: cb())

        def save_state(saved: ClusterState) -> bool:
            window._cluster_state = saved
            return True

        window._save_cluster_state = Mock(side_effect=save_state)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        mock_provider = Mock()
        mock_provider.remove_job.return_value = {"ok": True}

        window_node_actions.remove_job_node(
            window, "peer-a",
            messagebox_module=Mock(return_value=True),
            provider_cls=Mock(return_value=mock_provider),
            transport_cls=Mock,
        )

        peer = next(
            item
            for item in window._cluster_state.role_assignments
            if item.node_id == NodeId("peer-a")
        )
        self.assertFalse(peer.has_active_job)
        window._nodes_status.assert_called_once_with("Removed job for peer-a")

    def test_remove_job_cancel_keeps_assignment(self) -> None:
        window = _make_window(start_discovery=False)
        state = ClusterState.create_local(local_node_id="local")
        state.role_assignments = state.role_assignments + (
            RoleAssignment(
                frozenset({ClusterRole.WORKER}),
                node_id=NodeId("peer-a"),
                has_active_job=True,
            ),
        )
        window._cluster_state = state
        window._save_cluster_state = Mock(return_value=True)
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        messagebox_module = Mock()
        messagebox_module.askyesno.return_value = False

        window_node_actions.remove_job_node(
            window, "peer-a", messagebox_module=messagebox_module
        )

        peer = next(
            item
            for item in window._cluster_state.role_assignments
            if item.node_id == NodeId("peer-a")
        )
        self.assertTrue(peer.has_active_job)
        window._save_cluster_state.assert_not_called()

    def test_role_less_trusted_node_can_still_be_revoked(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
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

        def save_state(saved: ClusterState) -> bool:
            window._cluster_state = saved
            return True

        window._save_cluster_state = Mock(side_effect=save_state)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._invalidate_node_render_targets = Mock()
        provider = window._node_registry.context(NodeId("peer-a")).provider

        window_node_actions.revoke_node(
            window, "peer-a", messagebox_module=Mock(return_value=True)
        )

        self.assertIsNone(window._cluster_state.record("peer-a"))
        self.assertIsNone(window._cluster_state.grant("peer-a"))
        provider.invalidate.assert_called_once_with()
        window._nodes_error.assert_not_called()
        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))

    def test_revoke_selected_node_returns_to_local_without_render_crash(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        window._cluster_state = ClusterState(
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

        def save_state(state: ClusterState) -> bool:
            window._cluster_state = state
            return True

        window._save_cluster_state = Mock(side_effect=save_state)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._switch_selected_node(NodeId("peer-a"))
        provider = window._node_registry.context(NodeId("peer-a")).provider

        window._revoke_trusted_node("peer-a")

        self.assertEqual(window._node_registry.selected_id(), NodeId(LOCAL_NODE_ID))
        self.assertEqual(window._selected_node_id, NodeId(LOCAL_NODE_ID))
        self.assertIsNone(window._cluster_state.record("peer-a"))
        provider.invalidate.assert_called_once_with()
        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))

        window._revoke_trusted_node("peer-a")

        window._nodes_status.assert_called_with("Node is already revoked")

    def test_switching_swaps_analyzer_and_scheduler_mirrors(self) -> None:
        window = _make_window(
            _trusted_context(
                "dev", "Dev Node", cpu_value="dev-cpu", host_label="dev-host"
            )
        )
        registry = window._node_registry
        dev = registry.context(NodeId("dev"))

        window._switch_selected_node(NodeId("dev"))

        self.assertEqual(window._selected_node_id, NodeId("dev"))
        self.assertIs(window.analyzer, dev.provider)
        self.assertIs(window.snapshot, dev.snapshot)
        self.assertIs(window._component_scheduler, dev.scheduler)

    def test_switching_refreshes_thermals_from_selected_node_context(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="dev-cpu", host_label="dev")
        )
        window.thermals_page = Mock()
        window._page_router = Mock()
        window._page_router.is_mapped.return_value = True

        window._switch_selected_node(NodeId("dev"))

        dev = window._node_registry.context(NodeId("dev"))
        window.thermals_page.render.assert_called_once_with(
            dev.telemetry.render_state(("cpu", "gpu", "storage", "battery")),
            dev.capabilities,
        )

    def test_switching_same_node_is_a_noop(self) -> None:
        window = _make_window()
        handle = Mock()
        window.handle_analyze = handle
        window._switch_selected_node(NodeId(LOCAL_NODE_ID))
        handle.assert_not_called()

    def test_hidden_thermals_page_defers_render_until_visible(self) -> None:
        window = _make_window()
        window._ui_coordinator = UICoordinator()
        window._ui_coordinator.set_visible("thermals", False)
        window.thermals_page = Mock()

        window._refresh_thermals_page()

        window.thermals_page.render.assert_not_called()
        self.assertEqual(window._ui_coordinator.pending_count, 1)
        window._ui_coordinator.set_visible("thermals", True)
        window.thermals_page.render.assert_called_once()

    def test_switching_ignores_unknown_node(self) -> None:
        window = _make_window()
        window._switch_selected_node(NodeId("nope"))
        self.assertEqual(window._selected_node_id, NodeId(LOCAL_NODE_ID))

    def test_snapshots_stay_isolated_per_node(self) -> None:
        window = _make_window(
            _trusted_context(
                "dev", "Dev Node", cpu_value="dev-cpu", host_label="dev-host"
            )
        )
        registry = window._node_registry
        window._switch_selected_node(NodeId("dev"))
        self.assertEqual(window.snapshot.get("cpu").value, "dev-cpu")

        window._switch_selected_node(NodeId(LOCAL_NODE_ID))
        local_cpu = window.snapshot.get("cpu").value
        self.assertEqual(local_cpu, "local-cpu")
        # The dev node still owns its own snapshot.
        dev_snapshot = registry.context(NodeId("dev")).snapshot
        self.assertEqual(dev_snapshot.get("cpu").value, "dev-cpu")

    def test_operation_keys_are_node_qualified(self) -> None:
        window = _make_window()
        self.assertEqual(
            window._operation_key("component:cpu"),
            "node:local:component:cpu",
        )
        self.assertEqual(window._operation_key("process"), "node:local:process")

    def test_cancelled_node_a_snapshot_cannot_update_node_b(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="dev", host_label="dev")
        )
        window._show_snapshot = Mock()
        generation, started = window._scan_coordinator.begin()
        self.assertTrue(started)
        window._analysis_cancel_event = threading.Event()

        window._switch_selected_node(NodeId("dev"))
        window._show_snapshot_for_generation(
            generation,
            make_snapshot(_summary("cpu", "old-local")),
            node_id=NodeId(LOCAL_NODE_ID),
        )

        window._show_snapshot.assert_not_called()
        self.assertEqual(window._selected_node_id, NodeId("dev"))

    def test_old_node_timeout_cannot_cancel_the_replacement_scan(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="dev", host_label="dev")
        )
        old_generation, started = window._scan_coordinator.begin()
        self.assertTrue(started)
        window._analysis_cancel_event = threading.Event()

        window._switch_selected_node(NodeId("dev"))
        _new_generation, started = window._scan_coordinator.begin()
        self.assertTrue(started)
        replacement_cancel_event = threading.Event()
        window._analysis_cancel_event = replacement_cancel_event

        window._handle_scan_timeout(old_generation)

        self.assertFalse(replacement_cancel_event.is_set())
        self.assertIsNone(window._timed_out_generation)

    def test_dashboard_worker_keeps_its_source_provider_after_switch(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="dev", host_label="dev")
        )
        local = window._node_registry.context(NodeId(LOCAL_NODE_ID))
        local.provider = Mock()
        local.provider.dashboard_snapshot.return_value = make_snapshot(
            _summary("cpu", "local")
        )
        window.analyzer = local.provider
        window._set_busy = Mock()
        window._run_in_background = Mock()

        AppWindow.handle_analyze(window)
        task = window._run_in_background.call_args.args[0]
        window._switch_selected_node(NodeId("dev"))
        task()

        local.provider.dashboard_snapshot.assert_called_once()
        window._node_registry.context(
            NodeId("dev")
        ).provider.dashboard_snapshot.assert_not_called()

    def test_old_component_result_finishes_source_scheduler_without_touching_new_node(
        self,
    ) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="dev", host_label="dev")
        )
        registry = window._node_registry
        local = registry.context(NodeId(LOCAL_NODE_ID))
        self.assertTrue(local.scheduler.begin("cpu", 0.0))
        window._switch_selected_node(NodeId("dev"))
        dev = registry.context(NodeId("dev"))
        dev_before = dev.snapshot
        window._apply_component = Mock()

        window._queue_component_result(
            "cpu",
            1.0,
            _summary("cpu", "old-local"),
            node_id=NodeId(LOCAL_NODE_ID),
            scheduler=local.scheduler,
        )

        self.assertFalse(local.scheduler.in_flight("cpu"))
        self.assertIs(window.snapshot, dev_before)
        window._apply_component.assert_not_called()

    def test_component_worker_keeps_its_source_provider_after_switch(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="dev", host_label="dev")
        )
        local = window._node_registry.context(NodeId(LOCAL_NODE_ID))
        local.provider = Mock()
        local.provider.component_summary.return_value = _summary("cpu", "local")
        window.analyzer = local.provider
        window._component_scheduler = local.scheduler
        coordinator = Mock()
        coordinator.in_flight.return_value = False
        window._coordinator = coordinator

        window._launch_component_scan("cpu")
        task = coordinator.run.call_args.args[1]
        window._switch_selected_node(NodeId("dev"))
        task(threading.Event(), lambda _message: None)

        local.provider.component_summary.assert_called_once()
        args, kwargs = local.provider.component_summary.call_args
        self.assertEqual(args, ("cpu",))
        self.assertIn("cancel_event", kwargs)
        self.assertIsInstance(kwargs["cancel_event"], threading.Event)
        window._node_registry.context(
            NodeId("dev")
        ).provider.component_summary.assert_not_called()

    def test_component_trigger_during_worker_requests_one_refresh(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="dev", host_label="dev")
        )
        window._coordinator = Mock()
        window._coordinator.in_flight.return_value = True
        window._component_scheduler = window._node_registry.context(
            NodeId(LOCAL_NODE_ID)
        ).scheduler
        window._component_scheduler.mark_all_refreshed(0.0)
        self.assertTrue(window._component_scheduler.begin("cpu", 1_000_000.0))
        window._component_scheduler.request_refresh = Mock()

        window._launch_component_scan("cpu")

        window._component_scheduler.request_refresh.assert_called_once_with("cpu")

    def test_component_scan_is_rejected_for_a_target_missing_component_read(
        self,
    ) -> None:
        remote = make_remote_context(
            "dev",
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            connection=ConnectionState.online(),
            permissions=frozenset(NodePermission),
            provider=Mock(),
            process_manager=Mock(),
            file_manager=Mock(),
            scheduler=ComponentRefreshScheduler(),
            coordinator=AppCoordinator(),
        )
        window = _make_window(remote)
        window._switch_selected_node(NodeId("dev"))

        window._launch_component_scan("cpu")

        remote.provider.component_summary.assert_not_called()
        in_flight, _paused, _last_success, last_error = (
            remote.scheduler.diagnostic_state("cpu")
        )
        self.assertFalse(in_flight)
        self.assertIsNotNone(last_error)
        self.assertEqual(last_error[0], "placement_rejected")

    def test_component_scan_still_proceeds_for_an_eligible_target(self) -> None:
        runner = DeferredRunner()
        remote = make_remote_context(
            "dev",
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            connection=ConnectionState.online(),
            capabilities=[NodeCapability.COMPONENT_READ],
            permissions=frozenset(NodePermission),
            provider=Mock(),
            process_manager=Mock(),
            file_manager=Mock(),
            scheduler=ComponentRefreshScheduler(),
            coordinator=AppCoordinator(),
        )
        remote.provider.component_summary.return_value = _summary("cpu", "dev-cpu")
        window = _make_window(remote)
        window._switch_selected_node(NodeId("dev"))
        window._coordinator = AppCoordinator(
            runner=runner, deliver=lambda callback: callback()
        )

        window._launch_component_scan("cpu")
        self.assertEqual(runner.pending, 1)
        runner.run_next()

        remote.provider.component_summary.assert_called_once()

    def test_cancel_node_operations_preserves_running_operation_state(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="dev", host_label="dev")
        )
        dev = window._node_registry.context(NodeId("dev"))
        window._feature_catalog.all = lambda: [
            SimpleNamespace(key="cpu"),
            SimpleNamespace(key="gpu"),
        ]
        window._coordinator = Mock()
        window._coordinator.in_flight.return_value = True

        window._cancel_node_operations(dev)

        window._coordinator.cancel.assert_has_calls(
            [
                call(node_operation_key(NodeId("dev"), "component:cpu")),
                call(node_operation_key(NodeId("dev"), "component:gpu")),
            ]
        )

    def test_switch_to_unscanned_node_clears_dashboard_cards(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="dev", host_label="dev")
        )
        window._node_registry.context(NodeId("dev")).snapshot = None
        window.cards = {"cpu": Mock(), "memory": Mock()}
        window.node_title_label = Mock()

        window._switch_selected_node(NodeId("dev"))

        for card in window.cards.values():
            card.reset_summary.assert_called_once()
        window.node_title_label.config.assert_called_once_with(text="DEV NODE")

    def test_remove_connection_on_selected_node_reverts_to_local(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer"),
            start_discovery=False,
        )
        registry = window._node_registry
        registry.select(NodeId("peer-a"))
        window._selected_node_id = NodeId("peer-a")
        window._cluster_state = ClusterState.create_local(local_node_id="local")
        window._save_cluster_state = Mock(return_value=True)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._sync_selected_context_mirrors = Mock()
        window._render_selected_node = Mock()
        manager = Mock()
        window._peer_connection_manager = manager

        window_node_actions.remove_connection_node(
            window, "peer-a", messagebox_module=Mock(return_value=True)
        )

        self.assertEqual(window._selected_node_id, NodeId(LOCAL_NODE_ID))
        self.assertEqual(registry.selected_id(), NodeId(LOCAL_NODE_ID))
        window._rebuild_node_selector.assert_called_once()


# fmt: on
