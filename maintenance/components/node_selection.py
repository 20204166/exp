"""Selection state and transition ordering for registered nodes."""

import logging
from collections.abc import Callable

from maintenance.nodes import NodeContext, NodeId, NodeRegistry, node_operation_key


class NodeSelection:
    """Coordinate a node selection change without owning presentation state."""

    def __init__(
        self,
        *,
        registry: NodeRegistry,
        selected_id: Callable[[], NodeId | None],
        set_selected_id: Callable[[NodeId], None],
        cancel_active_scan: Callable[[], None],
        invalidate_render_targets: Callable[[NodeId], None],
        cancel_node_operations: Callable[[NodeContext | None], None],
        sync_selected_context: Callable[[NodeContext], None],
        render_selected_node: Callable[[NodeContext], None],
        refresh_thermals: Callable[[NodeContext], None],
        schedule_scan: Callable[[], None],
        logger: logging.Logger,
        cancel_peer_connection: Callable[[NodeContext], None] | None = None,
    ) -> None:
        self._registry = registry
        self._selected_id = selected_id
        self._set_selected_id = set_selected_id
        self._cancel_active_scan = cancel_active_scan
        self._invalidate_render_targets = invalidate_render_targets
        self._cancel_node_operations = cancel_node_operations
        self._sync_selected_context = sync_selected_context
        self._render_selected_node = render_selected_node
        self._refresh_thermals = refresh_thermals
        self._schedule_scan = schedule_scan
        self._logger = logger
        self._cancel_peer_connection = cancel_peer_connection or (lambda _context: None)

    def selected_context(self) -> NodeContext | None:
        selected = self._selected_id()
        if selected is None:
            return None
        try:
            return self._registry.context(selected)
        except KeyError:
            return None

    def operation_key(self, operation: str) -> str:
        selected = self._selected_id()
        if selected is None:
            return operation
        return node_operation_key(selected, operation)

    def multi_node_selectable(self) -> bool:
        return len(self._registry.selectable_descriptors()) > 1

    def switch(self, node_id: NodeId) -> None:
        if node_id == self._selected_id():
            return
        old_context = self.selected_context()
        try:
            self._registry.select(node_id)
        except (KeyError, ValueError):
            self._logger.warning("Ignoring selection of unavailable node: %s", node_id)
            return

        self._set_selected_id(node_id)
        context = self._registry.selected_context()
        self._cancel_active_scan()
        self._invalidate_render_targets(node_id)
        self._cancel_node_operations(old_context)
        if old_context is not None:
            self._cancel_peer_connection(old_context)
        self._sync_selected_context(context)
        self._render_selected_node(context)
        self._refresh_thermals(context)
        self._schedule_scan()
