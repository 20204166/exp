"""Window node integration tests: selector, switching, isolation, discovery."""

import unittest
from dataclasses import replace
from typing import Any
from unittest.mock import ANY, Mock, patch

from maintenance.cluster import (
    ClusterState,
    trusted_node_record,
)
from maintenance.components.cluster_roles import ClusterRole, RoleAssignment
from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
)
from maintenance.models import CapabilityState
from maintenance.nodes import (
    LOCAL_NODE_ID,
    NodeCapability,
    NodeContext,
    NodeId,
    NodePermission,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
)
from maintenance.remote import RemoteRequest
from maintenance.ui import window_node_actions
from tests.support.models import make_snapshot, make_summary
from tests.support.nodes import (
    make_candidate,
    make_local_context,
    make_remote_context,
)
from tests.support.scheduling import DeferredRunner
from tests.support.window import make_window as make_bare_window


def _summary(key: str, value: str = "10%") -> Any:
    return make_summary(key, key, value=value, capability=CapabilityState.SUPPORTED)


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


def _local_context(analyzer: Any = None) -> NodeContext:
    return make_local_context(
        provider=analyzer,
        process_manager=Mock(),
        file_manager=Mock(),
        scheduler=ComponentRefreshScheduler(),
        coordinator=AppCoordinator(),
        snapshot=make_snapshot(_summary("cpu", "local-cpu"), system_label="local-host"),
        capabilities={"cpu": CapabilityState.SUPPORTED},
    )


def _trusted_context(
    node_id: str,
    display_name: str,
    *,
    cpu_value: str,
    host_label: str,
    capabilities: frozenset[NodeCapability] = frozenset(),
) -> NodeContext:
    context = make_remote_context(
        node_id,
        trust=NodeTrustState.TRUSTED,
        status=NodeStatus.ONLINE,
        display_name=display_name,
        hostname=node_id,
        capabilities=capabilities,
        platform="Linux",
        permissions=frozenset(NodePermission),
        provider=Mock(),
        process_manager=Mock(),
        file_manager=Mock(),
        scheduler=ComponentRefreshScheduler(),
        coordinator=AppCoordinator(),
        snapshot=make_snapshot(_summary("cpu", cpu_value), system_label=host_label),
    )
    context.capabilities = {"cpu": CapabilityState.SUPPORTED}
    return context


def _make_window(
    *contexts: NodeContext,
    start_discovery: bool = True,
) -> Any:
    window = make_bare_window(
        _feature_catalog=Mock(),
        _coordinator=AppCoordinator(deliver=lambda callback: callback()),
        _cluster_state=ClusterState(),
        _manual_host_ids=set(),
        _capabilities={},
        _preferences=Mock(),
        _discovery_tick_id=None,
    )
    window._feature_catalog.all = list
    window._preferences.refresh_intervals.as_dict = dict
    window._preferences.visible_cards = frozenset()
    window._preferences.hide_unavailable_cards = False

    registry = NodeRegistry()
    local_ctx = _local_context()
    registry.register_context(local_ctx)
    for context in contexts:
        registry.register_context(context)
    registry.select(local_ctx.node_id)
    window._node_registry = registry
    window._selected_node_id = registry.selected_id()
    window.analyzer = local_ctx.provider
    window.process_manager = local_ctx.process_manager
    window.file_manager = local_ctx.file_manager
    window.snapshot = local_ctx.snapshot
    window._reconcile_intervals = Mock()
    window._reconcile_cards_and_polling = Mock()

    window.status_label = Mock()
    window.progress_bar = Mock()
    window.refreshed_label = Mock()
    window.scan_time_label = Mock()
    window.health_label = Mock()
    window.cards = {}
    window._refresh_health = Mock()
    window._schedule_timer = Mock(return_value="timer-1")
    window._cancel_timer = Mock(return_value=True)
    window._schedule_component_poll = Mock()
    window.handle_analyze = Mock()
    window._start_background_poll = Mock()
    window._show_progress = Mock()
    window._set_busy = Mock()
    window._reset_progress_bar = Mock()
    window._completion_transition = Mock()
    window._cancel_pending_timers = Mock()
    window._layout_dashboard_cards = Mock()
    window._refresh_cards_scrollbar = Mock()

    if start_discovery:
        window._start_discovery()
    return window


class WindowOpenResourceNodeTests(unittest.TestCase):
    def test_local_dialog_is_not_read_only(self) -> None:
        window = _make_window()
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=_summary("cpu"))
        window._feature_catalog.get = Mock(return_value=Mock(action_kind="process"))
        with patch("window.ProcessDialog") as dialog:
            window.open_resource("cpu")
        self.assertEqual(dialog.call_args.kwargs["read_only"], False)
        self.assertEqual(dialog.call_args.kwargs["node_id"], NodeId(LOCAL_NODE_ID))
        self.assertIs(dialog.call_args.kwargs["provider"], window.analyzer)

    def test_remote_without_termination_capability_is_read_only(self) -> None:
        window = _make_window(
            _trusted_context(
                "dev",
                "Dev Node",
                cpu_value="x",
                host_label="dev",
                capabilities=frozenset({NodeCapability.PROCESS_REVIEW}),
            )
        )
        window._switch_selected_node(NodeId("dev"))
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=_summary("cpu"))
        window._feature_catalog.get = Mock(return_value=Mock(action_kind="process"))
        with patch("window.ProcessDialog") as dialog:
            window.open_resource("cpu")
        self.assertEqual(dialog.call_args.kwargs["read_only"], True)
        self.assertEqual(dialog.call_args.kwargs["node_title"], "Dev Node")
        self.assertIs(dialog.call_args.kwargs["provider"], window.analyzer)

    def test_remote_cleanup_metadata_does_not_enable_storage_mutation(self) -> None:
        window = _make_window(
            _trusted_context(
                "dev",
                "Dev Node",
                cpu_value="x",
                host_label="dev",
                capabilities=frozenset(
                    {NodeCapability.STORAGE_REVIEW, NodeCapability.CLEANUP}
                ),
            )
        )
        window._switch_selected_node(NodeId("dev"))
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=_summary("storage"))
        window._feature_catalog.get = Mock(return_value=Mock(action_kind="storage"))
        with patch("window.StorageDialog") as dialog:
            window.open_resource("storage")
        self.assertEqual(dialog.call_args.kwargs["read_only"], True)

    def test_remote_storage_dialog_never_gets_a_scan_root(self) -> None:
        window = _make_window(
            _trusted_context(
                "dev",
                "Dev Node",
                cpu_value="x",
                host_label="dev",
                capabilities=frozenset({NodeCapability.STORAGE_REVIEW}),
            )
        )
        window._switch_selected_node(NodeId("dev"))
        window._preferences.full_system_scan_enabled = True
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=_summary("storage"))
        window._feature_catalog.get = Mock(return_value=Mock(action_kind="storage"))
        with patch("window.StorageDialog") as dialog:
            window.open_resource("storage")
        self.assertIsNone(dialog.call_args.kwargs["scan_root"])

    def test_dialog_change_callback_does_not_rescan_a_newly_selected_node(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="x", host_label="dev")
        )
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=_summary("cpu"))
        window._feature_catalog.get = Mock(return_value=Mock(action_kind="process"))
        window._rescan_after_change = Mock()
        with patch("window.ProcessDialog") as dialog:
            window.open_resource("cpu")
        on_changed = dialog.call_args.kwargs["on_changed"]

        window._switch_selected_node(NodeId("dev"))
        on_changed()

        window._rescan_after_change.assert_not_called()


def _candidate(stable_id: str, fingerprint: str | None = None) -> Any:
    return make_candidate(
        stable_id,
        hostname=f"{stable_id}-host",
        last_seen=1.0,
        identity_fingerprint=fingerprint,
    )


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
        self.assertIsNotNone(window._cluster_state.record("peer-a"))

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

from tests.window_node_cases.selector import WindowNodeSelectorTests  # noqa: F401, I001
from tests.window_node_cases.connections import WindowNodeConnectionTests  # noqa: F401
from tests.window_node_cases.switching import WindowNodeSwitchingTests  # noqa: F401
from tests.window_node_cases.discovery_pairing import WindowDiscoveryIntegrationTests  # noqa: F401


if __name__ == "__main__":
    unittest.main()
