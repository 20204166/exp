"""Remote role operation test cases."""

import unittest
from dataclasses import replace
from typing import Any
from unittest.mock import ANY, Mock

from maintenance.cluster import ClusterState, trusted_node_record
from maintenance.components.cluster_roles import ClusterRole, RoleAssignment
from maintenance.components.coordinator import AppCoordinator
from maintenance.nodes import NodeId
from maintenance.ui import window_node_actions
from tests.support.scheduling import DeferredRunner
from tests.test_window_nodes import _make_window, _trusted_context


# Preserve the extracted case bodies exactly as they were in the facade.
# fmt: off
class RemoteRoleOperationTests(unittest.TestCase):
    """Verify role mutations send RPCs to enrolled cluster members before saving locally."""

    def _cluster_window(self, runner: DeferredRunner) -> Any:
        peer_context = _trusted_context(
            "peer-a", "Peer A", cpu_value="peer", host_label="peer"
        )
        window = _make_window(peer_context, start_discovery=False)
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
        window._coordinator = AppCoordinator(runner=runner, deliver=lambda cb: cb())

        def save(s: Any) -> bool:
            window._cluster_state = s
            return True

        window._save_cluster_state = Mock(side_effect=save)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._invalidate_node_render_targets = Mock()
        window._sync_selected_context_mirrors = Mock()
        window._render_selected_node = Mock()
        return window

    @staticmethod
    def _ok_provider() -> Mock:
        provider = Mock()
        provider.assign_role.return_value = {"ok": True}
        provider.pause_worker.return_value = {"ok": True}
        provider.resume_worker.return_value = {"ok": True}
        provider.revoke_worker.return_value = {"ok": True}
        provider.remove_job.return_value = {"ok": True}
        provider.remove_connection.return_value = {"ok": True}
        return provider

    # --- assign_role ---

    def test_set_roles_dispatches_assign_role_rpc_for_enrolled_member(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        provider = self._ok_provider()

        window_node_actions.set_node_roles(
            window, "peer-a", frozenset({"worker"}),
            provider_cls=Mock(return_value=provider), transport_cls=Mock,
        )
        runner.run_next()

        provider.assign_role.assert_called_once()
        call_args = provider.assign_role.call_args
        self.assertEqual(call_args.args[0], "peer-a")
        self.assertEqual(call_args.kwargs["cluster_id"], window._cluster_state.cluster_id)

    def test_set_roles_saves_locally_after_rpc_success(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)

        window_node_actions.set_node_roles(
            window, "peer-a", frozenset({"worker"}),
            provider_cls=Mock(return_value=self._ok_provider()), transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_not_called()
        assignment = next(
            item
            for item in window._cluster_state.role_assignments
            if item.node_id == NodeId("peer-a")
        )
        self.assertEqual(assignment.roles, frozenset({ClusterRole.WORKER}))

    def test_set_roles_reports_error_on_rpc_failure_without_local_save(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        original = window._cluster_state
        provider_cls = Mock(side_effect=RuntimeError("connection refused"))

        window_node_actions.set_node_roles(
            window, "peer-a", frozenset({"worker"}),
            provider_cls=provider_cls, transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_called_once()
        # cluster state unchanged (assignment not modified)
        self.assertIs(window._cluster_state, original)

    def test_set_roles_is_local_only_for_non_enrolled_node(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        provider_cls = Mock()
        # "ghost" is trusted but not enrolled
        window._cluster_state.trusted_nodes = (
            *window._cluster_state.trusted_nodes,
            trusted_node_record(
                node_id="ghost",
                display_name="Ghost",
                hostname="ghost",
                host="192.0.2.20",
                port=5001,
                secret="secret2",
                transport_fingerprint="tls-pin2",
            ),
        )

        window_node_actions.set_node_roles(
            window, "ghost", frozenset({"worker"}),
            provider_cls=provider_cls, transport_cls=Mock,
        )

        provider_cls.assert_not_called()
        self.assertEqual(runner.pending, 0)

    # --- pause_worker ---

    def test_pause_dispatches_pause_worker_rpc_for_enrolled_member(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        provider = self._ok_provider()

        window_node_actions.pause_node(
            window, "peer-a",
            provider_cls=Mock(return_value=provider), transport_cls=Mock,
        )
        runner.run_next()

        provider.pause_worker.assert_called_once_with(
            "peer-a",
            cluster_id=window._cluster_state.cluster_id,
            epoch=window._cluster_state.coordinator_epoch.epoch,
            fencing_token=window._cluster_state.coordinator_epoch.fencing_token,
        )

    def test_pause_saves_locally_after_rpc_success(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)

        window_node_actions.pause_node(
            window, "peer-a",
            provider_cls=Mock(return_value=self._ok_provider()), transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_not_called()
        peer = next(
            a for a in window._cluster_state.role_assignments
            if a.node_id == NodeId("peer-a")
        )
        self.assertTrue(peer.paused)

    def test_pause_reports_error_on_rpc_failure_without_local_save(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        original = window._cluster_state

        window_node_actions.pause_node(
            window, "peer-a",
            provider_cls=Mock(side_effect=RuntimeError("timeout")), transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_called_once()
        self.assertIs(window._cluster_state, original)

    # --- resume_worker ---

    def _paused_cluster_window(self, runner: DeferredRunner) -> Any:
        window = self._cluster_window(runner)
        window._cluster_state = replace(
            window._cluster_state,
            role_assignments=tuple(
                replace(a, paused=True) if a.node_id == NodeId("peer-a") else a
                for a in window._cluster_state.role_assignments
            ),
        )
        return window

    def test_resume_dispatches_resume_worker_rpc(self) -> None:
        runner = DeferredRunner()
        window = self._paused_cluster_window(runner)
        provider = self._ok_provider()

        window_node_actions.resume_node(
            window, "peer-a",
            provider_cls=Mock(return_value=provider), transport_cls=Mock,
        )
        runner.run_next()

        provider.resume_worker.assert_called_once_with(
            "peer-a",
            cluster_id=window._cluster_state.cluster_id,
            epoch=window._cluster_state.coordinator_epoch.epoch,
            fencing_token=window._cluster_state.coordinator_epoch.fencing_token,
        )

    def test_resume_saves_locally_after_rpc_success(self) -> None:
        runner = DeferredRunner()
        window = self._paused_cluster_window(runner)

        window_node_actions.resume_node(
            window, "peer-a",
            provider_cls=Mock(return_value=self._ok_provider()), transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_not_called()
        peer = next(
            a for a in window._cluster_state.role_assignments
            if a.node_id == NodeId("peer-a")
        )
        self.assertFalse(peer.paused)

    def test_resume_reports_error_on_rpc_failure(self) -> None:
        runner = DeferredRunner()
        window = self._paused_cluster_window(runner)
        original = window._cluster_state

        window_node_actions.resume_node(
            window, "peer-a",
            provider_cls=Mock(side_effect=RuntimeError("timeout")), transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_called_once()
        self.assertIs(window._cluster_state, original)

    # --- revoke_worker ---

    def test_revoke_dispatches_revoke_worker_rpc_before_trust_removal(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        provider = self._ok_provider()

        window_node_actions.revoke_node(
            window, "peer-a",
            messagebox_module=Mock(askyesno=Mock(return_value=True)),
            provider_cls=Mock(return_value=provider), transport_cls=Mock,
        )
        runner.run_next()

        provider.revoke_worker.assert_called_once_with(
            "peer-a",
            cluster_id=window._cluster_state.cluster_id,
            epoch=ANY,
            fencing_token=ANY,
        )

    def test_revoke_removes_trust_after_rpc_success(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)

        window_node_actions.revoke_node(
            window, "peer-a",
            messagebox_module=Mock(askyesno=Mock(return_value=True)),
            provider_cls=Mock(return_value=self._ok_provider()), transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_not_called()
        self.assertIsNone(window._cluster_state.record("peer-a"))

    def test_revoke_does_not_remove_trust_on_rpc_failure(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)

        window_node_actions.revoke_node(
            window, "peer-a",
            messagebox_module=Mock(askyesno=Mock(return_value=True)),
            provider_cls=Mock(side_effect=RuntimeError("timeout")), transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_called_once()
        # Trust still intact
        self.assertIsNotNone(window._cluster_state.record("peer-a"))

    # --- remove_job ---

    def _active_job_window(self, runner: DeferredRunner) -> Any:
        window = self._cluster_window(runner)
        window._cluster_state = replace(
            window._cluster_state,
            role_assignments=tuple(
                replace(a, has_active_job=True) if a.node_id == NodeId("peer-a") else a
                for a in window._cluster_state.role_assignments
            ),
        )
        return window

    def test_remove_job_dispatches_remove_job_rpc(self) -> None:
        runner = DeferredRunner()
        window = self._active_job_window(runner)
        provider = self._ok_provider()

        window_node_actions.remove_job_node(
            window, "peer-a",
            messagebox_module=Mock(askyesno=Mock(return_value=True)),
            provider_cls=Mock(return_value=provider), transport_cls=Mock,
        )
        runner.run_next()

        provider.remove_job.assert_called_once_with(
            "peer-a",
            cluster_id=window._cluster_state.cluster_id,
            epoch=window._cluster_state.coordinator_epoch.epoch,
            fencing_token=window._cluster_state.coordinator_epoch.fencing_token,
        )

    def test_remove_job_saves_locally_after_rpc_success(self) -> None:
        runner = DeferredRunner()
        window = self._active_job_window(runner)

        window_node_actions.remove_job_node(
            window, "peer-a",
            messagebox_module=Mock(askyesno=Mock(return_value=True)),
            provider_cls=Mock(return_value=self._ok_provider()), transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_not_called()
        peer = next(
            a for a in window._cluster_state.role_assignments
            if a.node_id == NodeId("peer-a")
        )
        self.assertFalse(peer.has_active_job)

    def test_remove_job_reports_error_on_rpc_failure(self) -> None:
        runner = DeferredRunner()
        window = self._active_job_window(runner)
        original = window._cluster_state

        window_node_actions.remove_job_node(
            window, "peer-a",
            messagebox_module=Mock(askyesno=Mock(return_value=True)),
            provider_cls=Mock(side_effect=RuntimeError("timeout")), transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_called_once()
        self.assertIs(window._cluster_state, original)

    # --- remove_connection ---

    def test_remove_connection_sends_rpc_and_proceeds_locally(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        provider = self._ok_provider()

        window_node_actions.remove_connection_node(
            window, "peer-a",
            messagebox_module=Mock(askyesno=Mock(return_value=True)),
            provider_cls=Mock(return_value=provider), transport_cls=Mock,
        )
        # Local cleanup happens synchronously; RPC runs when dispatched
        runner.run_next()

        provider.remove_connection.assert_called_once()

    def test_remove_connection_proceeds_locally_even_if_rpc_fails(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        provider_cls = Mock(side_effect=RuntimeError("timeout"))

        window_node_actions.remove_connection_node(
            window, "peer-a",
            messagebox_module=Mock(askyesno=Mock(return_value=True)),
            provider_cls=provider_cls, transport_cls=Mock,
        )
        runner.run_next()

        # No user-visible error for fire-and-forget failure
        window._nodes_error.assert_not_called()
        window._refresh_nodes_page.assert_called()

    # --- non-member and no-epoch guard ---

    def test_role_op_for_non_member_is_local_only_no_rpc(self) -> None:
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        provider_cls = Mock()
        # Add a trusted node with no role assignment
        window._cluster_state.trusted_nodes = (
            *window._cluster_state.trusted_nodes,
            trusted_node_record(
                node_id="stranger",
                display_name="Stranger",
                hostname="stranger",
                host="192.0.2.99",
                port=6000,
                secret="s",
                transport_fingerprint="fp",
            ),
        )

        # pause_node for "stranger" should raise locally (not enrolled), no RPC
        window_node_actions.pause_node(
            window, "stranger", provider_cls=provider_cls, transport_cls=Mock
        )

        provider_cls.assert_not_called()
        self.assertEqual(runner.pending, 0)
        window._nodes_error.assert_called_once()

    def test_role_op_without_coordinator_epoch_fails_closed_for_enrolled_member(
        self,
    ) -> None:
        """An enrolled cluster member + no epoch must fail with an error, not mutate locally."""
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        window._cluster_state = replace(window._cluster_state, coordinator_epoch=None)
        provider_cls = Mock()
        original_assignments = window._cluster_state.role_assignments

        window_node_actions.pause_node(
            window, "peer-a", provider_cls=provider_cls, transport_cls=Mock
        )

        # No RPC dispatched, no task queued
        provider_cls.assert_not_called()
        self.assertEqual(runner.pending, 0)
        # Error surfaced — not silently dropped
        window._nodes_error.assert_called()
        # Role state must NOT have been mutated locally
        self.assertEqual(window._cluster_state.role_assignments, original_assignments)

    def test_enrolled_member_without_port_fails_closed_not_silently_local(self) -> None:
        """An enrolled cluster member with no port must fail closed; not mutate locally.

        This was the dangerous silent-fallback bug: peer with a role assignment
        but no reachable endpoint would silently receive a local-only role write,
        diverging from the target's actual state.
        """
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        # Remove port from peer-a's trusted_nodes entry to simulate offline node
        window._cluster_state.trusted_nodes = (
            trusted_node_record(
                node_id="peer-a",
                display_name="Peer A",
                hostname="peer-a",
                host="192.0.2.10",
                port=None,  # no port → endpoint unavailable
                secret="secret",
                transport_fingerprint="tls-pin",
            ),
        )
        provider_cls = Mock()
        original_assignments = window._cluster_state.role_assignments

        window_node_actions.pause_node(
            window, "peer-a", provider_cls=provider_cls, transport_cls=Mock
        )

        # No RPC, no task queued
        provider_cls.assert_not_called()
        self.assertEqual(runner.pending, 0)
        # Error must be surfaced
        window._nodes_error.assert_called()
        error_msg = window._nodes_error.call_args[0][0]
        self.assertIn("unavailable", error_msg)
        # Cluster state must NOT have been mutated locally
        self.assertEqual(window._cluster_state.role_assignments, original_assignments)

    def test_enrolled_member_without_record_fails_closed(self) -> None:
        """Enrolled member with no trusted_nodes entry must fail, not mutate locally."""
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        # Clear trusted_nodes so state.record("peer-a") returns None
        window._cluster_state.trusted_nodes = ()
        provider_cls = Mock()
        original_assignments = window._cluster_state.role_assignments

        window_node_actions.set_node_roles(
            window, "peer-a", frozenset({"worker"}),
            provider_cls=provider_cls, transport_cls=Mock,
        )

        provider_cls.assert_not_called()
        self.assertEqual(runner.pending, 0)
        window._nodes_error.assert_called()
        error_msg = window._nodes_error.call_args[0][0]
        self.assertIn("connection record", error_msg)
        self.assertEqual(window._cluster_state.role_assignments, original_assignments)

    def test_remove_connection_proceeds_locally_even_for_offline_enrolled_member(
        self,
    ) -> None:
        """remove_connection local cleanup must always proceed; RPC is best-effort."""
        runner = DeferredRunner()
        window = self._cluster_window(runner)
        # Remove port so endpoint is unavailable
        window._cluster_state.trusted_nodes = (
            trusted_node_record(
                node_id="peer-a",
                display_name="Peer A",
                hostname="peer-a",
                host="192.0.2.10",
                port=None,
                secret="secret",
                transport_fingerprint="tls-pin",
            ),
        )
        provider_cls = Mock()

        window_node_actions.remove_connection_node(
            window, "peer-a",
            messagebox_module=Mock(askyesno=Mock(return_value=True)),
            provider_cls=provider_cls, transport_cls=Mock,
        )

        # Local cleanup must have run (refresh was called)
        window._refresh_nodes_page.assert_called()
        # No RPC attempt for unreachable node
        provider_cls.assert_not_called()
        self.assertEqual(runner.pending, 0)
        # No error surfaced (fire-and-forget; silently skip when unreachable)
        window._nodes_error.assert_not_called()
# fmt: on
