"""Window node integration tests: selector, switching, isolation, discovery."""

import threading
import unittest
from queue import Queue
from typing import Any
from unittest.mock import Mock, patch

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
    NodeCapability,
    NodeContext,
    NodeDescriptor,
    NodeId,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
    local_node_descriptor,
)
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

    def test_switching_same_node_is_a_noop(self) -> None:
        window = _make_window()
        handle = Mock()
        window.handle_analyze = handle
        window._switch_selected_node(NodeId(LOCAL_NODE_ID))
        handle.assert_not_called()

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
        window._coordinator = coordinator

        window._launch_component_scan("cpu")
        task = coordinator.run.call_args.args[1]
        window._switch_selected_node(NodeId("dev"))
        task(threading.Event(), lambda _message: None)

        local.provider.component_summary.assert_called_once_with("cpu")
        window._node_registry.context(
            NodeId("dev")
        ).provider.component_summary.assert_not_called()

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

    def test_discovered_candidate_never_becomes_selectable(self) -> None:
        window = _make_window()
        window._on_discovered_candidate(_candidate("peer-a"))
        self.assertNotIn(
            NodeId("peer-a"),
            {d.id for d in window._node_registry.selectable_descriptors()},
        )

    def test_discovered_lost_removes_candidate(self) -> None:
        window = _make_window()
        window._on_discovered_candidate(_candidate("peer-a"))
        window._on_discovered_lost("peer-a")
        self.assertEqual(window._node_registry.discovered_candidates(), ())

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


def _candidate(stable_id: str) -> Any:
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
    )


if __name__ == "__main__":
    unittest.main()
