"""Node selection and runtime adapters for :class:`window.AppWindow`."""

from __future__ import annotations

import logging
from typing import Any, cast

from maintenance.components import NodeSelection
from maintenance.nodes import NodeContext, NodeId, node_operation_key
from maintenance.ui.target_state import render_target_state

DASHBOARD_PAGE = "dashboard"
THERMALS_PAGE = "thermals"
LOGGER = logging.getLogger(__name__)


def selected_context(controller: Any) -> NodeContext | None:
    selection = controller._node_selection()
    if selection is None:
        return None
    return selection.selected_context()


def operation_key(controller: Any, operation: str) -> str:
    selection = controller._node_selection()
    if selection is None:
        return operation
    return selection.operation_key(operation)


def multi_node_selectable(controller: Any) -> bool:
    selection = controller._node_selection()
    return selection is not None and selection.multi_node_selectable()


def node_selection(controller: Any) -> NodeSelection | None:
    selection = controller.__dict__.get("_node_selection_component")
    if selection is not None:
        return cast(NodeSelection, selection)
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return None
    selection = NodeSelection(
        registry=registry,
        selected_id=lambda: controller.__dict__.get("_selected_node_id"),
        set_selected_id=lambda node_id: controller.__dict__.__setitem__(
            "_selected_node_id", node_id
        ),
        cancel_active_scan=lambda: controller._cancel_active_scan(),
        invalidate_render_targets=lambda node_id: (
            controller._invalidate_node_render_targets(node_id)
        ),
        cancel_node_operations=lambda context: controller._cancel_node_operations(
            context
        ),
        sync_selected_context=lambda context: controller._sync_selected_context_mirrors(
            context
        ),
        render_selected_node=lambda context: controller._render_selected_node(context),
        refresh_thermals=lambda context: controller._refresh_selected_node_thermals(
            context
        ),
        schedule_scan=lambda: controller._schedule_selected_node_scan(),
        logger=LOGGER,
        cancel_peer_connection=lambda context: controller._cancel_peer_connection(
            context
        ),
    )
    controller.__dict__["_node_selection_component"] = selection
    return selection


def schedule_selected_node_scan(controller: Any) -> None:
    controller._schedule_timer(0, controller.handle_analyze)


def rebuild_node_selector(controller: Any) -> None:
    frame = getattr(controller, "_node_selector_frame", None)
    if frame is not None:
        try:
            frame.destroy()
        except Exception:  # noqa: BLE001 - a dead widget must not fail the page.
            return
    actions = getattr(controller, "header_actions", None)
    if actions is not None:
        controller._build_node_selector(actions)


def build_node_selector(controller: Any, actions: Any) -> None:
    controller._node_selector = None
    controller._node_selector_var = None
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    selectable = registry.selectable_descriptors()
    if len(selectable) <= 1:
        return

    name_counts: dict[str, int] = {}
    for descriptor in selectable:
        name_counts[descriptor.display_name] = (
            name_counts.get(descriptor.display_name, 0) + 1
        )
    labels = {
        descriptor.id: (
            descriptor.display_name
            if name_counts[descriptor.display_name] == 1
            else f"{descriptor.display_name} ({descriptor.hostname} · {descriptor.id.value})"
        )
        for descriptor in selectable
    }
    controller._node_selector_values = {
        label: node_id for node_id, label in labels.items()
    }
    selected_id = controller.__dict__.get("_selected_node_id")
    selected_value = labels.get(selected_id, labels[selectable[0].id])

    toolkit_ttk = getattr(controller, "ttk", None)
    toolkit_tk = getattr(controller, "tk", None)
    if toolkit_ttk is None or toolkit_tk is None:
        # Keep the historical window-module patch seam for partial test windows.
        import window

        toolkit_ttk = window.ttk
        toolkit_tk = window.tk
    frame = toolkit_ttk.Frame(actions, style="App.TFrame")
    toolkit_ttk.Label(frame, text="Node", style="Description.TLabel").pack(anchor="w")
    controller._node_selector_var = toolkit_tk.StringVar(value=selected_value)
    controller._node_selector = toolkit_ttk.Combobox(
        frame,
        textvariable=controller._node_selector_var,
        state="readonly",
        values=list(controller._node_selector_values),
        width=18,
    )
    controller._node_selector.pack(anchor="w")
    controller._node_selector.bind(
        "<<ComboboxSelected>>", controller._on_node_selector_change
    )
    frame.pack(anchor="e", pady=(0, 9))
    controller._node_selector_frame = frame


def on_node_selector_change(controller: Any, _event: object) -> None:
    registry = controller.__dict__.get("_node_registry")
    selector = controller.__dict__.get("_node_selector")
    selector_var = controller.__dict__.get("_node_selector_var")
    if registry is None or selector is None or selector_var is None:
        return
    label = selector_var.get()
    node_id = controller.__dict__.get("_node_selector_values", {}).get(label)
    if node_id is not None:
        controller._switch_selected_node(node_id)


def switch_selected_node(controller: Any, node_id: NodeId) -> None:
    selection = controller._node_selection()
    if selection is None:
        return
    selection.switch(node_id)


def invalidate_node_render_targets(controller: Any, node_id: NodeId) -> None:
    coordinator = controller._render_coordinator()
    if coordinator is None:
        return
    generation = controller._scan_coordinator_state().generation
    coordinator.invalidate(DASHBOARD_PAGE, generation, node_id=node_id)
    coordinator.invalidate("scan-status", generation, node_id=node_id)
    coordinator.invalidate("discovery-pages", 0, node_id=node_id)
    coordinator.invalidate(THERMALS_PAGE, 0, node_id=node_id)
    for feature in controller._feature_catalog.all():
        coordinator.invalidate(f"component:{feature.key}", 0, node_id=node_id)


def refresh_selected_node_thermals(controller: Any, context: NodeContext) -> None:
    thermals_page = getattr(controller, "thermals_page", None)
    router = getattr(controller, "_page_router", None)
    if (
        thermals_page is not None
        and router is not None
        and router.is_mapped(THERMALS_PAGE)
    ):
        thermals_page.render(
            controller._thermal_render_state(context),
            context.capabilities,
        )


def cancel_active_scan(controller: Any) -> None:
    controller._dashboard_scan_lifecycle().cancel()
    controller._sync_dashboard_scan_state()


def cancel_node_operations(controller: Any, context: NodeContext | None) -> None:
    if context is None:
        return
    coordinator = controller.__dict__.get("_coordinator")
    scheduler = getattr(context, "scheduler", None)
    node_id = getattr(context.descriptor, "id", None)
    for feature in controller._feature_catalog.all():
        if coordinator is not None and node_id is not None:
            coordinator.cancel(node_operation_key(node_id, f"component:{feature.key}"))
            if coordinator.in_flight(
                node_operation_key(node_id, f"component:{feature.key}")
            ):
                continue
        cancel = getattr(scheduler, "cancel", None)
        if cancel is not None:
            try:
                cancel(feature.key)
            except Exception as error:  # noqa: BLE001 - cancellation is best-effort.
                LOGGER.debug(
                    "Ignoring cancellation failure for %s: %s", feature.key, error
                )


def cancel_all_node_operations(controller: Any) -> None:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    for context in registry.contexts():
        controller._cancel_node_operations(context)


def sync_selected_context_mirrors(controller: Any, context: NodeContext) -> None:
    controller.analyzer = context.provider
    controller.process_manager = context.process_manager
    controller.file_manager = context.file_manager
    controller.snapshot = context.snapshot
    controller.__dict__["_node_snapshot"] = context.node_snapshot
    controller._capabilities = context.capabilities
    controller.__dict__["_capability_counts"] = context.capability_counts
    controller.__dict__["_failed_card_counts"] = context.failed_card_counts
    controller.__dict__["_full_snapshot_applied_at"] = context.full_snapshot_applied_at
    controller._component_scheduler = context.scheduler
    controller._reconcile_intervals()
    controller._reconcile_cards_and_polling()


def render_selected_node(controller: Any, context: NodeContext) -> None:
    snapshot = context.snapshot
    node_title_label = getattr(controller, "node_title_label", None)
    if node_title_label is not None:
        presentation = render_target_state(context.descriptor, snapshot)
        node_title_label.config(text=context.descriptor.display_name.upper())
    target_status_label = getattr(controller, "target_status_label", None)
    if target_status_label is not None:
        presentation = render_target_state(context.descriptor, snapshot)
        target_status_label.config(
            text=(
                f"{presentation.label} · {presentation.identity} · "
                f"capabilities: {', '.join(presentation.capabilities) or 'none'}"
            )
        )
    if snapshot is None:
        controller.refreshed_label.config(text="Not refreshed yet")
        controller.scan_time_label.config(text="Not scanned yet")
        controller.health_label.config(
            text="Health: No issues detected", style="Healthy.TLabel"
        )
        for card in controller.cards.values():
            card.reset_summary()
        return
    for key, card in controller.cards.items():
        card.set_action_enabled(
            render_target_state(context.descriptor, snapshot, key).can_review
        )
    for resource in snapshot.resources:
        if resource.key in controller.cards:
            controller.cards[resource.key].update_summary(resource)
    scanned_time = snapshot.scanned_at.strftime("%H:%M:%S")
    controller.scan_time_label.config(
        text=f"{snapshot.system_label} • scanned {scanned_time}"
    )
    controller.refreshed_label.config(text=f"Last refreshed: {scanned_time}")
    controller._refresh_health()
