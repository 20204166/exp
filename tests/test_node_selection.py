"""Focused tests for node selection transition ordering."""

import unittest
from unittest.mock import Mock

from maintenance.components.node_selection import NodeSelection
from maintenance.nodes import NodeId


class NodeSelectionTests(unittest.TestCase):
    def test_switch_preserves_transition_order(self) -> None:
        old_context = Mock()
        new_context = Mock()
        registry = Mock()
        registry.context.return_value = old_context
        registry.selected_context.return_value = new_context
        selected = NodeId("old")
        events: list[str] = []

        selection = NodeSelection(
            registry=registry,
            selected_id=lambda: selected,
            set_selected_id=lambda node_id: events.append(f"select-id:{node_id.value}"),
            cancel_active_scan=lambda: events.append("cancel-scan"),
            invalidate_render_targets=lambda node_id: events.append(
                f"invalidate:{node_id.value}"
            ),
            cancel_node_operations=lambda context: events.append(
                "cancel-old" if context is old_context else "cancel-wrong"
            ),
            sync_selected_context=lambda context: events.append("sync"),
            render_selected_node=lambda context: events.append("render"),
            refresh_thermals=lambda context: events.append("thermals"),
            schedule_scan=lambda: events.append("schedule"),
            logger=Mock(),
        )

        selection.switch(NodeId("new"))

        self.assertEqual(
            events,
            [
                "select-id:new",
                "cancel-scan",
                "invalidate:new",
                "cancel-old",
                "sync",
                "render",
                "thermals",
                "schedule",
            ],
        )
        registry.select.assert_called_once_with(NodeId("new"))

    def test_switch_rejects_unavailable_node_without_side_effects(self) -> None:
        registry = Mock()
        registry.select.side_effect = ValueError("not selectable")
        callback = Mock()
        selection = NodeSelection(
            registry=registry,
            selected_id=lambda: NodeId("old"),
            set_selected_id=callback,
            cancel_active_scan=callback,
            invalidate_render_targets=callback,
            cancel_node_operations=callback,
            sync_selected_context=callback,
            render_selected_node=callback,
            refresh_thermals=callback,
            schedule_scan=callback,
            logger=Mock(),
        )

        selection.switch(NodeId("new"))

        callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
