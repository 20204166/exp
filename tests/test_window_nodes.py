"""Window node integration tests: selector, switching, isolation, discovery."""

import threading
import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, Mock, call, patch

from maintenance.cluster import (
    ClusterState,
    PeerGrantRecord,
    decode_invite_blob,
    encode_invite_blob,
    trusted_node_record,
)
from maintenance.components.cluster_roles import ClusterRole, RoleAssignment
from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
)
from maintenance.components.network_discovery import (
    NetworkDiscovery,
)
from maintenance.models import CapabilityState
from maintenance.nodes import (
    LOCAL_NODE_ID,
    READ_PERMISSIONS,
    ConnectionState,
    DiscoveredNodeCandidate,
    NodeCapability,
    NodeContext,
    NodeId,
    NodeIdentityStatus,
    NodePermission,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
    node_identity_fingerprint,
    node_operation_key,
)
from maintenance.remote import RemoteAuthError, RemoteRequest
from maintenance.ui import window_discovery as ui_window_discovery
from maintenance.ui import window_node_actions, window_pages
from maintenance.ui.cluster_page import ClusterNodeSpec
from maintenance.ui.nodes_connections import DiscoveredPeerSpec, TrustedNodeSpec
from maintenance.ui.render_coordinator import UICoordinator
from maintenance.ui.window_supports import node_specs
from tests.support.models import make_snapshot, make_summary
from tests.support.nodes import (
    make_candidate,
    make_local_context,
    make_remote_context,
)
from tests.support.scheduling import DeferredRunner
from tests.support.window import make_window as make_bare_window
from window import AppWindow


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


class WindowNodeSelectorTests(unittest.TestCase):
    def test_app_window_owns_one_dialog_per_node_workflow(self) -> None:
        window = _make_window(start_discovery=False)
        window._page_router = Mock()
        router = window._page_router
        coordinator = window._coordinator
        window.master = Mock()
        trusted = TrustedNodeSpec(
            node_id="peer-a",
            display_name="Peer A",
            hostname="peer-a.local",
            color=None,
            status="online",
            host="192.0.2.10",
            port=5000,
            selectable=True,
            openable=True,
        )
        discovered = DiscoveredPeerSpec(
            node_id="peer-a",
            hostname="peer-a.local",
            app_version="1",
            compatible=True,
            connectable=True,
            port=5000,
            identity_fingerprint="identity",
        )
        cluster = ClusterNodeSpec(
            node_id="local",
            display_name="This system",
            hostname="local",
            color=None,
            trust="local",
            status="online",
            capabilities=(),
            is_local=True,
            selectable=True,
            share_active=True,
        )

        with (
            patch("window.ConnectionDialog") as connection,
            patch("window.PairingDialog") as pairing,
            patch("window.NodeDetailsDialog") as details,
            patch("window.SharingDialog") as sharing,
        ):
            for dialog in (connection, pairing, details, sharing):
                dialog.return_value.window = Mock()
            window._open_connection_dialog(None)
            window._open_connection_dialog(None)
            window._open_connection_dialog(trusted)
            window._open_pairing_dialog(discovered)
            window._open_node_details_dialog(trusted)
            window._open_sharing_dialog(cluster)

        connection.assert_called_once()
        pairing.assert_called_once()
        details.assert_called_once()
        sharing.assert_called_once()
        self.assertIs(connection.call_args.args[0], window.master)
        self.assertEqual(
            connection.call_args.kwargs["on_add"].__func__,
            window._add_manual_host.__func__,
        )
        self.assertEqual(
            pairing.call_args.kwargs["on_pair"].__func__,
            window._pair_discovered_node.__func__,
        )
        self.assertIs(window._page_router, router)
        self.assertIs(window._coordinator, coordinator)

    def test_discovered_peer_details_use_presentation_safe_spec(self) -> None:
        window = _make_window(start_discovery=False)
        window.master = Mock()
        discovered = DiscoveredPeerSpec(
            node_id="peer-a",
            hostname="peer-a.local",
            app_version="1",
            compatible=True,
            connectable=True,
            port=5000,
            identity_fingerprint="identity",
            transport_fingerprint="tls",
            pairing_state="discovered",
        )

        with patch("window.NodeDetailsDialog") as details:
            details.return_value.window = Mock()
            window._open_node_details_dialog(discovered)

        spec = details.call_args.kwargs["spec"]
        self.assertEqual(spec.node_id, "peer-a")
        self.assertEqual(spec.display_name, "peer-a.local")
        self.assertEqual(spec.hostname, "peer-a.local")
        self.assertEqual(spec.host, "peer-a.local")
        self.assertEqual(spec.port, 5000)
        self.assertEqual(spec.pairing_state, "discovered")
        self.assertEqual(spec.identity_fingerprint, "identity")
        self.assertEqual(spec.transport_fingerprint, "tls")
        self.assertFalse(spec.openable)
        self.assertFalse(spec.selectable)
        self.assertFalse(spec.role_editable)
        self.assertFalse(spec.is_manual)

    def test_dialog_destroy_clears_controller_reference(self) -> None:
        window = _make_window(start_discovery=False)
        dialog = Mock()
        dialog.window = Mock()
        with patch("window.ConnectionDialog", return_value=dialog):
            window._open_connection_dialog(None)

        self.assertIs(window._connection_dialog, dialog)
        dialog.close()
        self.assertIsNone(window._connection_dialog)

    def test_nodes_and_cluster_pages_receive_dialog_openers(self) -> None:
        window = _make_window(start_discovery=False)
        window.ttk = Mock()
        window._button_coordinator = Mock()
        window._cluster_state = ClusterState()
        with (
            patch.object(window_pages.ui_nodes, "NodesConnectionsPage") as nodes,
            patch.object(window_pages.ui_cluster, "ClusterPage") as cluster,
        ):
            window_pages.build_nodes(window, Mock())
            window_pages.build_cluster(window, Mock())

        self.assertEqual(
            nodes.call_args.kwargs["callbacks"].on_open_connection.__func__,
            window._open_connection_dialog.__func__,
        )
        self.assertEqual(
            cluster.call_args.kwargs["callbacks"].on_open_sharing.__func__,
            window._open_sharing_dialog.__func__,
        )

    def test_peer_reconciliation_owns_one_replacement_timer(self) -> None:
        window = _make_window(start_discovery=False)
        manager = Mock()
        manager.reconcile.return_value = time.monotonic() + 1.0
        window._peer_connection_manager = manager
        window._peer_reconcile_timer_id = "old-timer"

        window._reconcile_peer_connections()

        window._cancel_timer.assert_called_once_with("old-timer")
        window._schedule_timer.assert_called_once()
        self.assertEqual(window._peer_reconcile_timer_id, "timer-1")

    def test_cluster_specs_disambiguate_duplicate_display_names(self) -> None:
        local = _local_context()
        peer = _trusted_context(
            "peer", "This System", cpu_value="peer", host_label="peer"
        )
        registry = NodeRegistry()
        registry.register_context(local)
        registry.register_context(peer)

        specs = node_specs.cluster_node_specs(registry)

        self.assertEqual(
            [spec.display_name for spec in specs],
            ["This System (local)", "This System (peer)"],
        )
        self.assertEqual([spec.selectable for spec in specs], [True, True])

    def test_identity_mismatch_is_not_openable(self) -> None:
        context = _trusted_context("peer", "Peer", cpu_value="peer", host_label="peer")
        context.descriptor = replace(
            context.descriptor,
            identity_status=NodeIdentityStatus.MISMATCH,
        )
        window = _make_window(context, start_discovery=False)
        state = ClusterState(
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer",
                    display_name="Peer",
                    hostname="peer",
                    host="peer",
                    port=1234,
                ),
            )
        )

        specs = node_specs.trusted_node_specs(window._node_registry, state)

        self.assertEqual(len(specs), 1)
        self.assertFalse(specs[0].openable)

    def test_permission_toggle_preserves_unmanaged_permissions(self) -> None:
        context = _trusted_context("peer", "Peer", cpu_value="peer", host_label="peer")
        context.descriptor = replace(
            context.descriptor,
            permissions=frozenset(
                {
                    NodePermission.DASHBOARD_READ,
                    NodePermission.COMPONENT_READ,
                    NodePermission.PROCESS_REVIEW,
                    NodePermission.STORAGE_REVIEW,
                }
            ),
        )
        window = _make_window(context, start_discovery=False)
        window._cluster_state = ClusterState(
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer",
                    display_name="Peer",
                    hostname="peer",
                    host="peer",
                    permissions=context.descriptor.permissions,
                ),
            )
        )
        window._save_cluster_state = Mock(return_value=True)

        window._set_node_permissions("peer", frozenset({"process_termination"}))

        self.assertEqual(
            window._node_registry.context(NodeId("peer")).descriptor.permissions,
            frozenset(
                {
                    NodePermission.DASHBOARD_READ,
                    NodePermission.COMPONENT_READ,
                    NodePermission.PROCESS_TERMINATION,
                    NodePermission.STORAGE_REVIEW,
                }
            ),
        )

    def test_color_save_failure_restores_previous_color(self) -> None:
        context = _trusted_context("peer", "Peer", cpu_value="peer", host_label="peer")
        context.descriptor = replace(context.descriptor, color="rose")
        window = _make_window(context, start_discovery=False)
        window._cluster_state = ClusterState()
        window._save_cluster_state = Mock(return_value=False)
        window._nodes_error = Mock()

        window._set_node_color("peer", "sky")

        self.assertEqual(
            window._node_registry.context(NodeId("peer")).descriptor.color,
            "rose",
        )

    def test_invalid_manual_port_is_rejected(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._nodes_error = Mock()

        window._add_manual_host("Peer", "peer", 70000)

        window._nodes_error.assert_called_once_with("Port must be between 0 and 65535")
        self.assertIsNone(window._cluster_state.record("manual-peer:70000"))

    def test_non_integer_manual_port_is_rejected_at_controller_boundary(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._nodes_error = Mock()

        window._add_manual_host("Peer", "peer", "5000")

        window._nodes_error.assert_called_once_with("Port must be between 0 and 65535")

    def test_remove_manual_host_prompts_before_revoking(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_status = Mock()
        window._add_manual_host("Lab Box", "lab-box.local", None)
        node_id = "manual-lab-box.local"
        self.assertIsNotNone(window._cluster_state.record(node_id))

        with patch("window.messagebox.askyesno", return_value=False) as confirm:
            window._remove_manual_host(node_id)

        confirm.assert_called_once()
        self.assertIsNotNone(window._cluster_state.record(node_id))

    def test_remove_manual_host_revokes_after_confirmation(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_status = Mock()
        window._add_manual_host("Lab Box", "lab-box.local", None)
        node_id = "manual-lab-box.local"

        with patch("window.messagebox.askyesno", return_value=True):
            window._remove_manual_host(node_id)

        self.assertIsNone(window._cluster_state.record(node_id))

    def test_selector_absent_for_single_local_node(self) -> None:
        window = _make_window()
        window._build_node_selector(Mock())
        self.assertIsNone(window._node_selector)

    def test_selector_built_for_multiple_selectable_nodes(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="x", host_label="dev")
        )
        with patch("window.ttk") as ttk, patch("window.tk") as tk:
            ttk.Frame.return_value = Mock()
            ttk.Label.return_value = Mock()
            combobox = Mock()
            ttk.Combobox.return_value = combobox
            tk.StringVar.return_value = Mock()
            window._build_node_selector(Mock())
        self.assertIsNotNone(window._node_selector)
        self.assertIsNotNone(window._node_selector_var)

    def test_selector_ignores_discovered_candidates(self) -> None:
        window = _make_window()
        window._node_registry.update_discovered(_candidate("peer-a"))
        window._build_node_selector(Mock())
        self.assertIsNone(window._node_selector)

    def test_selector_disambiguates_duplicate_display_names_by_stable_id(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Same Name", cpu_value="a", host_label="a"),
            _trusted_context("peer-b", "Same Name", cpu_value="b", host_label="b"),
        )
        with patch("window.ttk") as ttk, patch("window.tk") as tk:
            ttk.Frame.return_value = Mock()
            ttk.Label.return_value = Mock()
            ttk.Combobox.return_value = Mock()
            tk.StringVar.return_value = Mock()
            window._build_node_selector(Mock())

        self.assertEqual(
            set(window._node_selector_values.values()),
            {NodeId(LOCAL_NODE_ID), NodeId("peer-a"), NodeId("peer-b")},
        )
        self.assertEqual(len(window._node_selector_values), 3)

    def test_multi_node_selectable_false_for_one_node(self) -> None:
        window = _make_window()
        self.assertFalse(window._multi_node_selectable())

    def test_multi_node_selectable_true_for_trusted_second_node(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="x", host_label="dev")
        )
        self.assertTrue(window._multi_node_selectable())


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
                RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("local")),
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
            window, "peer-a", blob, provider_cls=Mock(return_value=provider), transport_cls=Mock
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
            RoleAssignment(frozenset({ClusterRole.WORKER}), node_id=NodeId("peer-a")),
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


class WindowDiscoveryIntegrationTests(unittest.TestCase):
    def test_migrated_local_identity_uses_matching_fingerprint(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState(local_node_id="node-persisted")
        window._node_registry = NodeRegistry()
        window._component_scheduler = ComponentRefreshScheduler()

        window._build_local_node_context()

        descriptor = window._node_registry.selected_context().descriptor
        self.assertEqual(descriptor.id, NodeId("node-persisted"))
        self.assertEqual(
            descriptor.identity_fingerprint,
            node_identity_fingerprint("node-persisted"),
        )

    def test_start_discovery_registers_local_advertisement(self) -> None:
        with patch(
            "window.NetworkDiscovery",
            side_effect=lambda *args, **kwargs: Mock(spec=NetworkDiscovery),
        ) as factory:
            _make_window()
        factory.assert_called_once()
        _, kwargs = factory.call_args
        self.assertEqual(kwargs["advertisement"].stable_id, LOCAL_NODE_ID)
        self.assertFalse(kwargs["advertisement"].connectable)

    def test_manual_hostname_and_ip_fallback_registers_trusted_endpoint(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_status = Mock()

        window._add_manual_host("Lab Box", "lab-box.local", None)
        window._add_manual_host("IP Box", "192.168.1.20", 5000)

        hostname_record = window._cluster_state.record("manual-lab-box.local")
        ip_record = window._cluster_state.record("manual-192.168.1.20:5000")
        self.assertIsNotNone(hostname_record)
        self.assertIsNotNone(ip_record)
        assert hostname_record is not None
        assert ip_record is not None
        self.assertEqual(
            window._node_registry.contexts()[-1].descriptor.trust,
            NodeTrustState.TRUSTED,
        )
        self.assertEqual(hostname_record.host, "lab-box.local")
        self.assertEqual(ip_record.host, "192.168.1.20")

    def test_discovered_candidate_never_becomes_selectable(self) -> None:
        window = _make_window()
        window._on_discovered_candidate(_candidate("peer-a"))
        self.assertNotIn(
            NodeId("peer-a"),
            {d.id for d in window._node_registry.selectable_descriptors()},
        )

    def test_reject_discovered_node_clears_only_the_candidate(self) -> None:
        window = _make_window()
        window._on_discovered_candidate(_candidate("peer-a"))

        window._reject_discovered_node("peer-a")

        self.assertEqual(window._node_registry.discovered_candidates(), ())
        self.assertEqual(window._selected_node_id, NodeId(LOCAL_NODE_ID))

    def test_discovered_lost_removes_candidate(self) -> None:
        window = _make_window()
        window._on_discovered_candidate(_candidate("peer-a"))
        window._on_discovered_lost("peer-a")
        self.assertEqual(window._node_registry.discovered_candidates(), ())

    def test_discovery_presentation_waits_for_session_stabilization(self) -> None:
        window = _make_window()
        window._queue_discovery_presentation = Mock()
        session = window._discovery_session

        window._on_discovered_candidate(_candidate("peer-a"))

        window._queue_discovery_presentation.assert_not_called()
        session._on_stabilized()
        window._queue_discovery_presentation.assert_called_once_with(False)

    def test_trusted_rediscovery_updates_saved_endpoint_after_hello(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer")
        )
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._cluster_state = ClusterState(
            discovery_enabled=True,
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.168.1.10",
                    port=5000,
                    secret="a" * 64,
                ),
            ),
        )
        provider = Mock()
        provider.hello.return_value = {
            "ok": True,
            "node_id": "peer-a",
            "identity_fingerprint": node_identity_fingerprint("peer-a"),
            "app_version": "1.2.2.0",
            "capabilities": ["dashboard_read"],
        }

        candidate = DiscoveredNodeCandidate(
            stable_id="peer-a",
            hostname="new-host",
            addresses=("192.168.1.20",),
            port=6000,
            service_name="peer-a._system-analyzer._tcp.local.",
            app_version="1.2.4.0",
            protocol_version="1",
            platform="Linux",
            connectable=False,
            compatible=True,
            last_seen=1.0,
        )

        with patch(
            "window.AuthenticatedNodeProvider", return_value=provider
        ) as factory:
            window._on_discovered_candidate(candidate)

        factory.assert_called_once()
        record = window._cluster_state.record("peer-a")
        assert record is not None
        self.assertEqual(record.host, "192.168.1.20")
        self.assertEqual(record.port, 6000)
        self.assertEqual(record.hostname, "new-host")

    def test_rediscovery_never_replaces_persisted_tls_pin(self) -> None:
        fingerprint = node_identity_fingerprint("peer-a")
        context = _trusted_context(
            "peer-a", "Peer A", cpu_value="peer", host_label="peer"
        )
        context.descriptor = replace(
            context.descriptor,
            identity_fingerprint=fingerprint,
            identity_status=NodeIdentityStatus.VERIFIED,
        )
        window = _make_window(context, start_discovery=False)
        window._cluster_state = ClusterState(
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.168.1.10",
                    port=5000,
                    identity_fingerprint=fingerprint,
                    transport_fingerprint="tls-x",
                ),
            )
        )
        window._nodes_error = Mock()
        candidate = replace(
            _candidate("peer-a", fingerprint), transport_fingerprint="tls-y"
        )

        with patch("maintenance.ui.window_discovery.build_trusted_transport") as build:
            window._on_discovered_candidate(candidate)

        record = window._cluster_state.record("peer-a")
        assert record is not None
        self.assertEqual(record.transport_fingerprint, "tls-x")
        self.assertEqual(
            window._node_registry.context(NodeId("peer-a")).descriptor.identity_status,
            NodeIdentityStatus.MISMATCH,
        )
        build.assert_not_called()

    def test_legacy_trusted_rediscovery_hydrates_live_fingerprint(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer")
        )
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._cluster_state = ClusterState(
            discovery_enabled=True,
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.168.1.10",
                    port=5000,
                    secret="a" * 64,
                ),
            ),
        )
        provider = Mock()
        provider.hello.return_value = {
            "ok": True,
            "node_id": "peer-a",
            "identity_fingerprint": node_identity_fingerprint("peer-a"),
        }
        candidate = DiscoveredNodeCandidate(
            stable_id="peer-a",
            hostname="peer-a",
            addresses=("192.168.1.10",),
            port=5000,
            service_name="peer-a._system-analyzer._tcp.local.",
            app_version="1.2.4.0",
            protocol_version="1",
            platform="Linux",
            connectable=False,
            compatible=True,
            last_seen=1.0,
            identity_fingerprint=node_identity_fingerprint("peer-a"),
        )

        with patch("window.AuthenticatedNodeProvider", return_value=provider):
            window._on_discovered_candidate(candidate)

        descriptor = window._node_registry.context(NodeId("peer-a")).descriptor
        self.assertEqual(
            descriptor.identity_fingerprint,
            node_identity_fingerprint("peer-a"),
        )
        self.assertEqual(descriptor.identity_status, NodeIdentityStatus.VERIFIED)
        record = window._cluster_state.record("peer-a")
        assert record is not None
        self.assertEqual(
            record.identity_fingerprint,
            node_identity_fingerprint("peer-a"),
        )
        provider.hello.assert_called_once()

    def test_trusted_rediscovery_rejects_identity_mismatch(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer")
        )
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._cluster_state = ClusterState(
            discovery_enabled=True,
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.168.1.10",
                    port=5000,
                    secret="a" * 64,
                    identity_fingerprint="original",
                ),
            ),
        )
        candidate = DiscoveredNodeCandidate(
            stable_id="peer-a",
            hostname="new-host",
            addresses=("192.168.1.20",),
            port=6000,
            service_name="peer-a._system-analyzer._tcp.local.",
            app_version="1.2.4.0",
            protocol_version="1",
            platform="Linux",
            connectable=False,
            compatible=True,
            last_seen=1.0,
            identity_fingerprint="changed",
        )

        with patch("window.AuthenticatedNodeProvider") as factory:
            window._on_discovered_candidate(candidate)

        factory.assert_not_called()
        record = window._cluster_state.record("peer-a")
        assert record is not None
        self.assertEqual(record.host, "192.168.1.10")
        self.assertEqual(
            window._node_registry.context(
                NodeId("peer-a")
            ).descriptor.identity_status.value,
            "mismatch",
        )

        matching = replace(candidate, identity_fingerprint="original")
        provider = Mock()
        provider.hello.return_value = {
            "ok": True,
            "node_id": "peer-a",
            "identity_fingerprint": "original",
        }
        with patch("window.AuthenticatedNodeProvider", return_value=provider):
            window._on_discovered_candidate(matching)

        self.assertEqual(
            window._node_registry.context(NodeId("peer-a")).descriptor.identity_status,
            NodeIdentityStatus.VERIFIED,
        )

    def test_confirmed_mismatch_repair_replaces_trust_record(self) -> None:
        context = _trusted_context(
            "peer-a", "Peer A", cpu_value="peer", host_label="peer"
        )
        context.descriptor = replace(
            context.descriptor,
            identity_fingerprint="original",
            identity_status=NodeIdentityStatus.VERIFIED,
        )
        window = _make_window(context)
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._cluster_state = ClusterState(
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.168.1.10",
                    port=5000,
                    secret="a" * 64,
                    identity_fingerprint="original",
                ),
            )
        )
        window._node_registry.update_discovered(_candidate("peer-a", "replacement"))
        provision = Mock(return_value=True)
        window._provision_target_grant = provision

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        records = window._cluster_state.trusted_nodes
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].identity_fingerprint, "replacement")
        self.assertIs(window._cluster_state.record("peer-a"), records[0])
        self.assertEqual(provision.call_args.args[0].caller_node_id, "local")
        self.assertEqual(window._cluster_state.peer_grants, ())

    def test_pairing_without_target_grant_is_not_marked_trusted(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._nodes_error = Mock()
        window._refresh_nodes_page = Mock()
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        self.assertIsNone(window._cluster_state.record("peer-a"))
        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))
        window._nodes_error.assert_called_once_with(
            "Pairing requires explicit target-side grant provisioning"
        )

    def test_pairing_provisions_grant_through_coordinator_before_persisting(
        self,
    ) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(
            runner=runner,
            deliver=deliveries.append,
        )
        provision = Mock(return_value=True)
        window._provision_target_grant = provision

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        self.assertEqual(runner.pending, 1)
        self.assertIsNone(window._cluster_state.record("peer-a"))
        window._pairing_dialog.set_pending.assert_called_once_with()
        self.assertEqual(
            window._coordinator.generation(
                node_operation_key(NodeId("peer-a"), "pair")
            ),
            1,
        )

        runner.run_next()
        self.assertEqual(len(deliveries), 1)
        deliveries[0]()

        provision.assert_called_once()
        self.assertEqual(len(provision.call_args.args), 1)
        self.assertIsNotNone(window._cluster_state.record("peer-a"))
        window._pairing_dialog.complete.assert_called_once_with()

    def test_revoke_cancels_pairing_before_late_success_delivery(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        window._provision_target_grant = Mock(return_value=True)

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        runner.run_next()
        window_node_actions.revoke_trusted_node(window, "peer-a")
        deliveries[0]()

        self.assertIsNone(window._cluster_state.record("peer-a"))
        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))

    def test_revoke_save_failure_keeps_pairing_state_consistent(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._pairing_dialog = Mock()
        window._nodes_error = Mock()
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        window._provision_target_grant = Mock(return_value=True)

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        window._save_cluster_state = Mock(return_value=False)
        window_node_actions.revoke_trusted_node(window, "peer-a")

        self.assertIsNotNone(window._node_registry.context(NodeId("peer-a")))
        self.assertIn(NodeId("peer-a"), window.__dict__["_pairing_attempts"])
        self.assertEqual(
            window._coordinator.generation(
                node_operation_key(NodeId("peer-a"), "pair")
            ),
            1,
        )
        window._nodes_error.assert_called_once_with(
            "Cluster settings could not be saved"
        )

    def test_pairing_success_after_worker_cancellation_is_not_persisted(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        provision = Mock(return_value=True)

        def provision_and_cancel(grant: PeerGrantRecord) -> bool:
            result = provision(grant)
            cancel_event = window._coordinator.state(
                node_operation_key(NodeId("peer-a"), "pair")
            ).cancel_event
            assert cancel_event is not None
            cancel_event.set()
            return result

        window._provision_target_grant = provision_and_cancel
        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        runner.run_next()
        deliveries[0]()

        self.assertIsNone(window._cluster_state.record("peer-a"))
        window._pairing_dialog.complete.assert_not_called()

    def test_default_target_grant_provisioner_receives_cancel_event(self) -> None:
        window = _make_window(start_discovery=False)
        candidate = replace(
            _candidate("peer-a", node_identity_fingerprint("peer-a")),
            transport_fingerprint="target-tls",
        )
        window._node_registry.update_discovered(candidate)
        grant = PeerGrantRecord(
            caller_node_id="local",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
        )
        cancel_event = threading.Event()

        with patch.object(
            window_node_actions.AuthenticatedNodeProvider,
            "request_pairing",
            return_value=True,
        ) as request_pairing:
            window_node_actions.request_target_grant(
                window, candidate, grant, cancel_event=cancel_event
            )

        self.assertIs(request_pairing.call_args.kwargs["cancel_event"], cancel_event)

    def test_default_pairing_returns_target_transaction_for_confirm(self) -> None:
        window = _make_window(start_discovery=False)
        candidate = replace(
            _candidate("peer-a", node_identity_fingerprint("peer-a")),
            transport_fingerprint="target-tls",
        )
        window._node_registry.update_discovered(candidate)
        grant = PeerGrantRecord(
            caller_node_id="local",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
        )
        transaction = {
            "transaction_id": "tx-1",
            "caller_node_id": "local",
            "identity_fingerprint": window._node_registry.context(
                NodeId("local")
            ).descriptor.identity_fingerprint,
            "transport_fingerprint": "",
            "secret": grant.secret,
            "permissions": [permission.value for permission in grant.permissions],
            "expires_at": time.time() + 3600.0,
        }

        with patch.object(
            window_node_actions.AuthenticatedNodeProvider,
            "request_pairing",
            return_value=transaction,
        ):
            result = window_node_actions.request_target_grant(window, candidate, grant)

        self.assertIsInstance(result, window_node_actions.PairingTransaction)
        assert isinstance(result, window_node_actions.PairingTransaction)
        self.assertEqual(result.transaction_id, "tx-1")
        self.assertGreater(result.expires_at, time.time())

    def test_default_pairing_rejects_returned_binding_mismatch(self) -> None:
        window = _make_window(start_discovery=False)
        candidate = replace(
            _candidate("peer-a", node_identity_fingerprint("peer-a")),
            transport_fingerprint="target-tls",
        )
        window._node_registry.update_discovered(candidate)
        grant = PeerGrantRecord(
            caller_node_id="local",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
        )
        requested_expiry = time.time() + 3600.0
        mismatches = {
            "caller_node_id": "other-caller",
            "identity_fingerprint": "other-id",
            "transport_fingerprint": "other-tls",
            "secret": "c" * 64,
            "permissions": [],
            "expires_at": time.time() - 1.0,
        }
        window._save_cluster_state = Mock()

        for field, mismatch in mismatches.items():
            returned = {
                "transaction_id": "tx-1",
                "caller_node_id": grant.caller_node_id,
                "identity_fingerprint": window._node_registry.context(
                    NodeId("local")
                ).descriptor.identity_fingerprint,
                "transport_fingerprint": "",
                "secret": grant.secret,
                "permissions": [permission.value for permission in grant.permissions],
                "expires_at": requested_expiry,
            }
            returned[field] = mismatch
            with (
                self.subTest(field=field),
                patch.object(
                    window_node_actions.AuthenticatedNodeProvider,
                    "request_pairing",
                    return_value=returned,
                ),
                patch.object(window_node_actions, "confirm_target_pairing") as confirm,
                patch.object(window_node_actions, "abort_target_pairing") as abort,
            ):
                result = window_node_actions.request_target_grant(
                    window, candidate, grant
                )

            self.assertFalse(result)
            confirm.assert_not_called()
            if field == "expires_at":
                abort.assert_called_once()
            else:
                abort.assert_not_called()
        window._save_cluster_state.assert_not_called()

    def test_pairing_control_uses_same_pinned_transport(self) -> None:
        transport = Mock()
        transport.request.return_value = '{"approved": true}'
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=123.0,
            transport=transport,
        )

        self.assertTrue(window_node_actions.confirm_target_pairing(transaction))
        self.assertEqual(transport.request.call_args.args[0].__class__, str)
        self.assertIn("pair_confirm", transport.request.call_args.args[0])

        self.assertTrue(window_node_actions.abort_target_pairing(transaction))
        self.assertIn("pair_abort", transport.request.call_args.args[0])

    def test_network_pairing_saves_locally_before_confirming_target(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._pairing_dialog = Mock()
        candidate = replace(
            _candidate("peer-a", node_identity_fingerprint("peer-a")),
            transport_fingerprint="target-tls",
        )
        window._node_registry.update_discovered(candidate)
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)

        def save(state: ClusterState) -> bool:
            window._cluster_state = state
            return True

        window._save_cluster_state = Mock(side_effect=save)
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=123.0,
            transport=Mock(),
        )
        with (
            patch.object(
                window_node_actions, "request_target_grant", return_value=transaction
            ) as approval,
            patch.object(
                window_node_actions, "confirm_target_pairing", return_value=True
            ) as confirm,
        ):
            window_node_actions.pair_discovered_node_async(
                window,
                "peer-a",
                messagebox_module=Mock(askyesno=Mock(return_value=True)),
                dialog=window._pairing_dialog,
            )
            runner.run_next()
            self.assertEqual(window._cluster_state.record("peer-a"), None)
            deliveries.pop(0)()

            record = window._cluster_state.record("peer-a")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.node_id, "peer-a")
            confirm.assert_not_called()
            while runner.pending:
                runner.run_next()
                while deliveries:
                    deliveries.pop(0)()

        approval.assert_called_once()
        confirm.assert_called_once()
        self.assertIs(confirm.call_args.args[0], transaction)
        self.assertIsNotNone(confirm.call_args.kwargs["cancel_event"])
        window._pairing_dialog.complete.assert_called_once_with()

    def test_cancel_network_pairing_restores_saved_state_before_confirm_delivery(
        self,
    ) -> None:
        window = _make_window(start_discovery=False)
        previous_state = ClusterState()
        window._cluster_state = previous_state
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            replace(
                _candidate("peer-a", node_identity_fingerprint("peer-a")),
                transport_fingerprint="target-tls",
            )
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)

        def save(state: ClusterState) -> bool:
            window._cluster_state = state
            return True

        window._save_cluster_state = Mock(side_effect=save)
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=123.0,
            transport=Mock(),
        )
        with (
            patch.object(
                window_node_actions, "request_target_grant", return_value=transaction
            ),
            patch.object(
                window_node_actions, "confirm_target_pairing", return_value=True
            ),
        ):
            window_node_actions.pair_discovered_node_async(
                window,
                "peer-a",
                messagebox_module=Mock(askyesno=Mock(return_value=True)),
                dialog=window._pairing_dialog,
            )
            runner.run_next()
            deliveries.pop(0)()

            self.assertIsNotNone(window._cluster_state.record("peer-a"))
            window_node_actions.cancel_pairing(window, "peer-a")
            while deliveries:
                deliveries.pop(0)()

        self.assertEqual(window._cluster_state, previous_state)
        self.assertIs(
            window._save_cluster_state.call_args_list[-1].args[0], previous_state
        )
        self.assertGreaterEqual(runner.pending, 2)
        window._pairing_dialog.complete.assert_not_called()

    def test_cancel_during_target_confirmation_keeps_committed_local_trust(
        self,
    ) -> None:
        window = _make_window(start_discovery=False)
        previous_state = ClusterState()
        window._cluster_state = previous_state
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            replace(
                _candidate("peer-a", node_identity_fingerprint("peer-a")),
                transport_fingerprint="target-tls",
            )
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)

        def save(state: ClusterState) -> bool:
            window._cluster_state = state
            return True

        window._save_cluster_state = Mock(side_effect=save)
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=123.0,
            transport=Mock(),
        )

        def confirm(_transaction: Any, *, cancel_event: Any = None) -> bool:
            self.assertIsNotNone(cancel_event)
            window_node_actions.cancel_pairing(window, "peer-a")
            return True

        with (
            patch.object(
                window_node_actions, "request_target_grant", return_value=transaction
            ),
            patch.object(
                window_node_actions, "confirm_target_pairing", side_effect=confirm
            ),
            patch.object(
                window_node_actions, "abort_target_pairing", return_value=True
            ) as abort,
        ):
            window_node_actions.pair_discovered_node_async(
                window,
                "peer-a",
                messagebox_module=Mock(askyesno=Mock(return_value=True)),
                dialog=window._pairing_dialog,
            )
            while runner.pending or deliveries:
                if runner.pending:
                    runner.run_next()
                while deliveries:
                    deliveries.pop(0)()

        self.assertIsNotNone(window._cluster_state.record("peer-a"))
        abort.assert_not_called()
        window._pairing_dialog.complete.assert_called_once_with()

    def test_network_confirmation_failure_restores_local_trust_and_aborts(self) -> None:
        window = _make_window(start_discovery=False)
        previous_state = ClusterState()
        window._cluster_state = previous_state
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            replace(
                _candidate("peer-a", node_identity_fingerprint("peer-a")),
                transport_fingerprint="target-tls",
            )
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)

        def save(state: ClusterState) -> bool:
            window._cluster_state = state
            return True

        window._save_cluster_state = Mock(side_effect=save)
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=123.0,
            transport=Mock(),
        )
        with (
            patch.object(
                window_node_actions, "request_target_grant", return_value=transaction
            ),
            patch.object(
                window_node_actions, "confirm_target_pairing", return_value=False
            ),
            patch.object(
                window_node_actions, "abort_target_pairing", return_value=True
            ) as abort,
        ):
            window_node_actions.pair_discovered_node_async(
                window,
                "peer-a",
                messagebox_module=Mock(askyesno=Mock(return_value=True)),
                dialog=window._pairing_dialog,
            )
            while runner.pending or deliveries:
                if runner.pending:
                    runner.run_next()
                while deliveries:
                    deliveries.pop(0)()

        self.assertIsNone(window._cluster_state.record("peer-a"))
        self.assertEqual(
            window._save_cluster_state.call_args_list[-1].args[0], previous_state
        )
        abort.assert_called_once_with(transaction)
        window._pairing_dialog.complete.assert_not_called()
        window._pairing_dialog.show_error.assert_called_once_with(
            "Target pairing confirmation failed"
        )

    def test_async_pairing_failure_restores_discovered_candidate(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._pairing_dialog = Mock()
        candidate = _candidate("peer-a", node_identity_fingerprint("peer-a"))
        window._node_registry.update_discovered(candidate)
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(
            runner=runner,
            deliver=deliveries.append,
        )
        window._provision_target_grant = Mock(return_value=False)

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")
        runner.run_next()
        deliveries[0]()

        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))
        self.assertEqual(
            window._node_registry.discovered_candidates(),
            (candidate,),
        )
        window._pairing_dialog.complete.assert_not_called()
        window._pairing_dialog.show_error.assert_called_once_with(
            "Target did not provision the peer grant"
        )

    def test_pairing_clears_stale_revoked_role_assignment(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState(
            role_assignments=(
                RoleAssignment(
                    frozenset({ClusterRole.COORDINATOR, ClusterRole.WORKER}),
                    node_id=NodeId("local"),
                ),
                RoleAssignment(
                    frozenset({ClusterRole.WORKER}),
                    node_id=NodeId("peer-a"),
                    revoked=True,
                ),
            )
        )
        window._cluster_store = Mock()
        window._nodes_error = Mock()
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._provision_target_grant = Mock(return_value=True)
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        stale = next(
            (
                item
                for item in window._cluster_state.role_assignments
                if item.node_id == NodeId("peer-a")
            ),
            None,
        )
        self.assertIsNone(stale)

        window._set_node_roles("peer-a", frozenset({"worker"}))

        window._nodes_error.assert_not_called()
        assignment = next(
            item
            for item in window._cluster_state.role_assignments
            if item.node_id == NodeId("peer-a")
        )
        self.assertFalse(assignment.revoked)

    def test_activation_result_is_ignored_after_record_replacement(self) -> None:
        window = _make_window(start_discovery=False)
        context = _trusted_context(
            "peer-a", "Peer A", cpu_value="peer", host_label="peer"
        )
        context.provider = None
        context.descriptor = replace(
            context.descriptor,
            identity_fingerprint=node_identity_fingerprint("peer-a"),
            identity_status=NodeIdentityStatus.VERIFIED,
        )
        window._node_registry.register_context(context)
        record = trusted_node_record(
            node_id="peer-a",
            display_name="Peer A",
            hostname="peer-a",
            host="peer-a",
            port=5000,
            identity_fingerprint=node_identity_fingerprint("peer-a"),
        )
        window._cluster_state = ClusterState(trusted_nodes=(record,))
        workers: list[Any] = []
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(
            runner=lambda worker: workers.append(worker),
            deliver=lambda callback: deliveries.append(callback),
        )
        provider = Mock()
        provider.hello.return_value = {
            "node_id": "peer-a",
            "identity_fingerprint": record.identity_fingerprint,
            "capabilities": ["dashboard_read"],
        }

        with patch("window.AuthenticatedNodeProvider", return_value=provider):
            window._activate_remote_node(NodeId("peer-a"))
        workers[0]()
        window._cluster_state = ClusterState(
            trusted_nodes=(replace(record, secret="b" * 64),)
        )
        deliveries[0]()

        self.assertIsNone(context.provider)

    def test_discovery_status_lists_untrusted_peers_and_hides_when_lost(self) -> None:
        window = _make_window()
        window._discovery_pages_visible = True
        window.discovery_status_label = Mock()

        window._on_discovered_candidate(_candidate("peer-b"))
        window._on_discovered_candidate(_candidate("peer-a"))
        window._discovery_session._on_stabilized()

        window.discovery_status_label.config.assert_called_with(
            text="Discovered 2 untrusted peers: peer-a-host, peer-b-host"
        )
        window._on_discovered_lost("peer-a")
        window._on_discovered_lost("peer-b")
        window._discovery_session._on_stabilized()
        window.discovery_status_label.pack_forget.assert_called_once()

    def test_shutdown_stops_discovery(self) -> None:
        window = _make_window()
        window._stop_discovery = Mock()
        window._finalize_shutdown()
        window._stop_discovery.assert_called_once()

    def test_shutdown_drops_pending_pairing_worker_delivery(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            replace(
                _candidate("peer-a", node_identity_fingerprint("peer-a")),
                transport_fingerprint="target-tls",
            )
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=time.time() + 300,
            transport=Mock(),
        )
        window._save_cluster_state = Mock(return_value=True)

        with patch.object(
            window_node_actions, "request_target_grant", return_value=transaction
        ):
            window_node_actions.pair_discovered_node_async(
                window,
                "peer-a",
                messagebox_module=Mock(askyesno=Mock(return_value=True)),
                dialog=window._pairing_dialog,
            )

        runner.run_next()
        window._finalize_shutdown()
        while deliveries:
            deliveries.pop(0)()

        self.assertIsNone(window._cluster_state.record("peer-a"))
        window._pairing_dialog.complete.assert_not_called()


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


if __name__ == "__main__":
    unittest.main()
