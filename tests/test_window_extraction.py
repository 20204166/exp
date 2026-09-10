import unittest
from unittest.mock import Mock, patch

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
