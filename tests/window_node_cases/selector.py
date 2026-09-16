"""Window node selector test cases."""

import time
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from maintenance.cluster import ClusterState, trusted_node_record
from maintenance.nodes import (
    LOCAL_NODE_ID,
    NodeId,
    NodeIdentityStatus,
    NodePermission,
    NodeRegistry,
)
from maintenance.ui import window_pages
from maintenance.ui.cluster_page import ClusterNodeSpec
from maintenance.ui.nodes_connections import DiscoveredPeerSpec, TrustedNodeSpec
from maintenance.ui.window_supports import node_specs
from tests.test_window_nodes import (
    _candidate,
    _local_context,
    _make_window,
    _trusted_context,
)


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

    def _setup_manual_host(
        self, window: object, display_name: str, host: str, port: int | None
    ) -> str:
        from maintenance.nodes import NodeContext, NodeDescriptor, NodeId, NodeTrustState, NodeStatus
        from maintenance.remote_support.protocol import READ_CAPABILITIES
        from maintenance.nodes import READ_PERMISSIONS
        node_id = f"manual-{host}:{port}" if port is not None else f"manual-{host}"
        descriptor = NodeDescriptor(
            id=NodeId(node_id),
            display_name=display_name,
            hostname=host,
            is_local=False,
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.UNKNOWN,
            capabilities=READ_CAPABILITIES,
            platform=None,
            color=None,
            permissions=READ_PERMISSIONS,
        )
        context = NodeContext(
            descriptor=descriptor,
            provider=None,
            process_manager=None,
            file_manager=None,
            scheduler=None,
            coordinator=None,
        )
        record = trusted_node_record(
            node_id=node_id,
            display_name=display_name,
            hostname=host,
            host=host,
            port=port,
            capabilities=READ_CAPABILITIES,
            permissions=READ_PERMISSIONS,
        )
        window._cluster_state = replace(  # type: ignore[attr-defined]
            window._cluster_state,  # type: ignore[attr-defined]
            trusted_nodes=window._cluster_state.trusted_nodes + (record,),  # type: ignore[attr-defined]
        )
        window._node_registry.register_context(context)  # type: ignore[attr-defined]
        manual_ids = getattr(window, "_manual_host_ids", None)
        if manual_ids is None:
            manual_ids = set()
            window._manual_host_ids = manual_ids  # type: ignore[attr-defined]
        manual_ids.add(node_id)
        return node_id

    def test_remove_manual_host_prompts_before_revoking(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_status = Mock()
        node_id = self._setup_manual_host(window, "Lab Box", "lab-box.local", None)
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
        node_id = self._setup_manual_host(window, "Lab Box", "lab-box.local", None)

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
