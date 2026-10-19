import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch

import window
from maintenance.nodes import NodeId
from maintenance.ui import (
    window_components,
    window_discovery,
    window_lifecycle,
    window_node_runtime,
    window_scan,
)
from window import AppWindow


class WindowExtractionTests(unittest.TestCase):
    def test_neutral_application_initializer_has_no_tk_import_dependency(self) -> None:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import maintenance.application_state; "
                    "assert 'tkinter' not in sys.modules"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_neutral_initializer_builds_services_for_non_window_owner(self) -> None:
        from maintenance.application_state import initialize_application_state

        preferences = Mock()
        preferences.refresh_intervals.as_dict.return_value = {}
        cluster_state = Mock()
        cluster_state.local_assignment.roles = []
        store = Mock(path=Path("cluster.json"))
        store.load.return_value = cluster_state
        owner = SimpleNamespace(
            _submit_ui=Mock(),
            _submit_latest_progress=Mock(),
            _start_background_poll=Mock(),
            _schedule_timer=Mock(),
            _cancel_timer=Mock(),
            _make_background_orchestrator=Mock(return_value="background"),
            _build_local_node_context=Mock(),
            _restore_trusted_nodes=Mock(),
        )
        factory = Mock(return_value=Mock())
        deps = SimpleNamespace(
            analyzer_factory=factory,
            process_manager_factory=factory,
            file_manager_factory=factory,
            preferences_store_factory=Mock(
                return_value=Mock(load=Mock(return_value=preferences))
            ),
            cluster_store_factory=Mock(return_value=store),
            timeline_factory=factory,
            standby_factory=factory,
            provision_target_grant=None,
            developer_mode=False,
            observer_factory=factory,
            scan_coordinator_factory=factory,
            queue_factory=factory,
            coordinator_factory=factory,
            scheduler_factory=factory,
            button_factory=factory,
            ui_coordinator_factory=factory,
            catalog_factory=factory,
            registry_factory=factory,
        )

        initialize_application_state(owner, dependencies=deps)

        self.assertEqual(owner._background_orchestrator, "background")
        self.assertIsNone(owner._cluster_timeline)
        self.assertIsNone(owner._standby_buffer)
        owner._build_local_node_context.assert_called_once_with()
        owner._restore_trusted_nodes.assert_called_once_with()

    def test_app_window_initialization_preserves_service_order_and_injections(
        self,
    ) -> None:
        events: list[str] = []
        analyzer = Mock()
        analyzer.scanner.downloads_path = "downloads"
        cluster_state = Mock()
        cluster_state.local_assignment.roles = []

        class Store:
            path = __import__("pathlib").Path("cluster.json")

            def load(self):
                events.append("cluster-load")
                return cluster_state

        preferences = Mock()
        preferences.refresh_intervals.as_dict.return_value = {"cpu": 2}
        pref_store = Mock()
        pref_store.load.return_value = preferences

        def record(name, result=None):
            events.append(name)
            return result or Mock()

        with (
            patch(
                "window.algo.Analyzer", side_effect=lambda: record("analyzer", analyzer)
            ),
            patch("window.ProcessManager", side_effect=lambda: record("process")),
            patch("window.FileManager", side_effect=lambda path: record("file")),
            patch("window.PreferencesStore", return_value=pref_store),
            patch("window.ClusterStore", return_value=Store()),
            patch("window.developer_mode_enabled", return_value=False),
            patch(
                "window.ObservabilityWatcher", side_effect=lambda: record("observer")
            ),
            patch("window.ScanCoordinator", side_effect=lambda **kw: record("scan")),
            patch(
                "window.AppCoordinator", side_effect=lambda **kw: record("coordinator")
            ),
            patch(
                "window.ComponentRefreshScheduler",
                side_effect=lambda *a, **kw: record("scheduler"),
            ),
            patch(
                "window.ButtonCoordinator", side_effect=lambda **kw: record("button")
            ),
            patch(
                "window.ui_render.UICoordinator",
                side_effect=lambda **kw: record("ui-coordinator"),
            ),
            patch.object(
                AppWindow,
                "_make_background_orchestrator",
                side_effect=lambda: record("background"),
            ),
            patch(
                "window.ResourceFeatureCatalog", side_effect=lambda: record("catalog")
            ),
            patch("window.NodeRegistry", side_effect=lambda: record("registry")),
            patch.object(
                AppWindow,
                "_build_local_node_context",
                side_effect=lambda: events.append("local-context"),
            ),
            patch.object(
                AppWindow,
                "_restore_trusted_nodes",
                side_effect=lambda: events.append("restore"),
            ),
        ):
            host = Mock()
            AppWindow(
                master=host,
                preferences_store=pref_store,
                cluster_store=cast(Any, Store()),
                initialize_ui=False,
            )

        self.assertEqual(
            events,
            [
                "analyzer",
                "process",
                "file",
                "cluster-load",
                "observer",
                "scan",
                "coordinator",
                "scheduler",
                "button",
                "ui-coordinator",
                "background",
                "catalog",
                "registry",
                "local-context",
                "restore",
            ],
        )

    def test_cluster_save_keeps_window_exception_and_logger_patch_seams(self) -> None:
        controller = object.__new__(AppWindow)
        controller._cluster_store = Mock()

        class PatchedSaveError(Exception):
            pass

        controller._cluster_store.save.side_effect = PatchedSaveError("unavailable")
        logger = Mock()
        with (
            patch.object(window, "ClusterSaveError", PatchedSaveError),
            patch.object(window, "LOGGER", logger),
        ):
            saved = controller._save_cluster_state(Mock())

        self.assertFalse(saved)
        logger.warning.assert_called_once_with(
            "Failed to save cluster settings: %s",
            controller._cluster_store.save.side_effect,
        )

    def test_lifecycle_timer_adapter_delegates_to_existing_delivery(self) -> None:
        controller = object.__new__(AppWindow)
        delivery = Mock()
        controller.__dict__["_timer_delivery"] = delivery

        callback = Mock()
        window_lifecycle.schedule_timer(controller, 25, callback, "value")
        window_lifecycle.cancel_timer(controller, "timer")

        delivery.schedule.assert_called_once_with(25, callback, "value")
        delivery.cancel.assert_called_once_with("timer")

    def test_lifecycle_timer_adapter_lazily_builds_partial_window_delivery(
        self,
    ) -> None:
        controller = object.__new__(AppWindow)
        controller.master = Mock()
        controller.master.after.side_effect = RuntimeError("master unavailable")
        controller.__dict__["_is_closing"] = False
        controller.__dict__["_pending_after_ids"] = set()

        delivery = window_lifecycle.timer_delivery_for_window(controller)

        self.assertIs(controller.__dict__["_timer_delivery"], delivery)
        self.assertIsNone(delivery.schedule(1, Mock()))

    def test_app_window_lifecycle_wrapper_delegates_at_call_time(self) -> None:
        controller = object.__new__(AppWindow)

        with patch.object(window_lifecycle, "run") as run:
            controller.run()

        run.assert_called_once_with(controller)

    def test_component_card_policy_delegates_to_shared_helper(self) -> None:
        controller = object.__new__(AppWindow)
        controller.__dict__["_preferences"] = Mock()
        controller.__dict__["_capabilities"] = {}

        with patch.object(
            window_components.card_policy, "is_card_visible", return_value=False
        ) as policy:
            self.assertFalse(window_components.is_card_visible(controller, "gpu"))

        policy.assert_called_once_with(
            "gpu", preferences=controller._preferences, capabilities={}
        )

    def test_component_result_rejects_stale_node_before_apply(self) -> None:
        controller = object.__new__(AppWindow)
        controller.__dict__["_selected_node_id"] = NodeId("selected")
        scheduler = Mock()
        schedule_component_poll = Mock()
        apply_component = Mock()
        controller.__dict__["_schedule_component_poll"] = schedule_component_poll
        controller.__dict__["_apply_component"] = apply_component

        window_components.queue_component_result(
            controller,
            "cpu",
            1.0,
            Mock(),
            node_id=NodeId("other"),
            scheduler=scheduler,
        )

        scheduler.finish.assert_called_once_with("cpu")
        apply_component.assert_not_called()
        schedule_component_poll.assert_called_once_with(force=True)

    def test_component_snapshot_merge_uses_snapshot_state_helper(self) -> None:
        controller = object.__new__(AppWindow)
        controller.snapshot = None
        controller.FAILED_CARD_KEEP_LIMIT = 3

        with patch.object(
            window_components.snapshot_state, "merge_snapshot", return_value="merged"
        ) as merge:
            result = window_components.merge_snapshot(controller, Mock())

        self.assertEqual(result, "merged")
        merge.assert_called_once()

    def test_discovery_peer_connections_delegates_to_existing_manager(self) -> None:
        controller = object.__new__(AppWindow)
        manager = Mock()
        controller.__dict__["_peer_connection_manager"] = manager

        self.assertIs(window_discovery.peer_connections(controller), manager)

    def test_discovery_stop_handles_partial_controller(self) -> None:
        controller = object.__new__(AppWindow)
        cancel_timer = Mock()
        controller.__dict__["_cancel_timer"] = cancel_timer
        controller.__dict__["_discovery_tick_id"] = "discovery-timer"

        window_discovery.stop_discovery(controller)

        cancel_timer.assert_called_once_with("discovery-timer")
        self.assertIsNone(controller._discovery_tick_id)

    def test_node_runtime_switch_delegates_to_selection_component(self) -> None:
        controller = object.__new__(AppWindow)
        selection = Mock()
        controller.__dict__["_node_selection"] = Mock(return_value=selection)

        window_node_runtime.switch_selected_node(controller, NodeId("peer"))

        selection.switch.assert_called_once_with(NodeId("peer"))

    def test_app_window_switch_wrapper_delegates_to_adapter(self) -> None:
        controller = object.__new__(AppWindow)

        with patch.object(window_node_runtime, "switch_selected_node") as switch:
            controller._switch_selected_node(NodeId("peer"))

        switch.assert_called_once_with(controller, NodeId("peer"))

    def test_node_selection_callbacks_resolve_controller_methods_at_call_time(
        self,
    ) -> None:
        controller = object.__new__(AppWindow)
        controller._node_registry = Mock()
        selection = Mock()

        with patch.object(
            window_node_runtime, "NodeSelection", return_value=selection
        ) as node_selection_class:
            window_node_runtime.node_selection(controller)

        callbacks = node_selection_class.call_args.kwargs
        cancel = Mock()
        controller.__dict__["_cancel_active_scan"] = cancel
        callbacks["cancel_active_scan"]()

        cancel.assert_called_once_with()

    def test_app_window_scan_wrapper_delegates_at_call_time(self) -> None:
        controller = object.__new__(AppWindow)

        with patch.object(window_scan, "handle_analyze") as handle:
            controller.handle_analyze()

        handle.assert_called_once_with(controller)

    def test_scan_lifecycle_factory_restores_legacy_mirrors(self) -> None:
        controller = object.__new__(AppWindow)
        lifecycle = Mock(
            cancel_event="cancel",
            timeout_id="timeout",
            lease_grace_id="grace",
            timed_out_generation=7,
            resolved_generation=8,
        )
        controller.__dict__["_dashboard_scan_lifecycle_obj"] = lifecycle

        window_scan.sync_dashboard_scan_state(controller)

        self.assertEqual(controller.__dict__["_analysis_cancel_event"], "cancel")
        self.assertEqual(controller.__dict__["_scan_timeout_id"], "timeout")
        self.assertEqual(controller.__dict__["_lease_grace_id"], "grace")
        self.assertEqual(controller.__dict__["_timed_out_generation"], 7)
        self.assertEqual(controller.__dict__["_resolved_scan_generation"], 8)

    def test_snapshot_delivery_rejects_stale_generation_before_render(self) -> None:
        controller = object.__new__(AppWindow)
        coordinator = Mock(generation=3)
        scan_coordinator_state = Mock(return_value=coordinator)
        show_snapshot = Mock()
        controller.__dict__["_scan_coordinator_state"] = scan_coordinator_state
        controller.__dict__["_show_snapshot"] = show_snapshot

        window_scan.show_snapshot_if_current(controller, 2, Mock())

        show_snapshot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
