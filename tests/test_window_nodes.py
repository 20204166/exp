"""Window node integration tests: selector, switching, isolation, discovery."""

import threading
import unittest
from dataclasses import replace
from queue import Queue
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call, patch

from maintenance.cluster import ClusterState, trusted_node_record
from maintenance.components import ScanCoordinator
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
    DiscoveredNodeCandidate,
    NodeCapability,
    NodeContext,
    NodeDescriptor,
    NodeId,
    NodeIdentityStatus,
    NodePermission,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
    local_node_descriptor,
    node_identity_fingerprint,
    node_operation_key,
)
from maintenance.ui.render_coordinator import UICoordinator
from tests.support.models import make_snapshot, make_summary
from tests.support.scheduling import TimerMaster
from window import AppWindow


def _summary(key: str, value: str = "10%") -> Any:
    return make_summary(key, key, value=value, capability=CapabilityState.SUPPORTED)


def _local_context(analyzer: Any = None) -> NodeContext:
    return NodeContext(
        descriptor=local_node_descriptor(),
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
    return NodeContext(
        descriptor=NodeDescriptor(
            id=NodeId(node_id),
            display_name=display_name,
            hostname=node_id,
            is_local=False,
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            capabilities=capabilities,
            platform="Linux",
            permissions=frozenset(NodePermission),
        ),
        provider=Mock(),
        process_manager=Mock(),
        file_manager=Mock(),
        scheduler=ComponentRefreshScheduler(),
        coordinator=AppCoordinator(),
        snapshot=make_snapshot(_summary("cpu", cpu_value), system_label=host_label),
        capabilities={"cpu": CapabilityState.SUPPORTED},
    )


def _make_window(
    *contexts: NodeContext,
    start_discovery: bool = True,
) -> Any:
    window: Any = object.__new__(AppWindow)
    window.master = TimerMaster()
    window._is_closing = False
    window._pending_after_ids = set()
    window._background_poll_id = None
    window._background_tasks = 0
    window._scan_coordinator = ScanCoordinator()
    window._analysis_cancel_event = None
    window._scan_timeout_id = None
    window._lease_grace_id = None
    window._timed_out_generation = None
    window._resolved_scan_generation = 0
    window._background_queue = Queue()
    window._feature_catalog = Mock()
    window._feature_catalog.all = list
    window._component_poll_id = None
    window._component_queue = Queue()
    window._coordinator = AppCoordinator(deliver=lambda callback: None)
    window._capabilities = {}
    window._preferences = Mock()
    window._preferences.refresh_intervals.as_dict = dict
    window._preferences.visible_cards = frozenset()
    window._preferences.hide_unavailable_cards = False
    window._discovery_tick_id = None

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


class WindowNodeSwitchingTests(unittest.TestCase):
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
        provider.hello.return_value = {"ok": True, "node_id": "peer-a"}
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
        with patch("window.AuthenticatedNodeProvider", return_value=Mock()):
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

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        records = window._cluster_state.trusted_nodes
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].identity_fingerprint, "replacement")
        self.assertIs(window._cluster_state.record("peer-a"), records[0])

    def test_discovery_status_lists_untrusted_peers_and_hides_when_lost(self) -> None:
        window = _make_window()
        window.discovery_status_label = Mock()

        window._on_discovered_candidate(_candidate("peer-b"))
        window._on_discovered_candidate(_candidate("peer-a"))

        window.discovery_status_label.config.assert_called_with(
            text="Discovered 2 untrusted peers: peer-a-host, peer-b-host"
        )
        window._on_discovered_lost("peer-a")
        window._on_discovered_lost("peer-b")
        window.discovery_status_label.pack_forget.assert_called_once()

    def test_shutdown_stops_discovery(self) -> None:
        window = _make_window()
        window._stop_discovery = Mock()
        window._finalize_shutdown()
        window._stop_discovery.assert_called_once()


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
    from maintenance.nodes import DiscoveredNodeCandidate

    return DiscoveredNodeCandidate(
        stable_id=stable_id,
        hostname=f"{stable_id}-host",
        addresses=("192.168.1.10",),
        port=5000,
        service_name=f"{stable_id}._system-analyzer._tcp.local.",
        app_version="1.2.2.0",
        protocol_version="1",
        platform="Linux",
        connectable=False,
        compatible=True,
        last_seen=1.0,
        identity_fingerprint=fingerprint,
    )


if __name__ == "__main__":
    unittest.main()
