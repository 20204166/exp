"""Snapshot, health, and resource-dialog adapters for ``AppWindow``."""

from __future__ import annotations

import time
from typing import Any

from maintenance.health import health_warnings
from maintenance.nodes import NodeCapability, NodePermission, node_operation_key
from maintenance.ui import scan_status
from maintenance.ui.target_state import render_target_state


def show_snapshot(controller: Any, snapshot: Any, *, node_snapshot: Any = None) -> None:
    if controller._is_closing:
        return
    merged = controller._merge_snapshot(snapshot)
    controller.snapshot = merged
    context = controller._selected_context()
    if context is not None:
        context.snapshot = merged
        if node_snapshot is not None:
            context.node_snapshot = node_snapshot
        context.full_snapshot_applied_at = time.monotonic()
    coordinator = controller.__dict__.get("_coordinator")
    if coordinator is not None:
        coordinator.store(controller._operation_key("snapshot:dashboard"), merged)
        if node_snapshot is not None:
            coordinator.store(
                node_operation_key(node_snapshot.node_id, "node_snapshot"),
                node_snapshot,
            )
    for resource in snapshot.resources:
        controller._observe_capability(resource.key, resource)
        controller._record_thermal_summary(resource.key, resource)
    for resource in merged.resources:
        controller.cards[resource.key].update_summary(resource)
    controller._full_snapshot_applied_at = time.monotonic()
    router = controller.__dict__.get("_page_router")
    if router is None or router.is_mapped(_window_symbols().CLUSTER_PAGE):
        controller._refresh_cluster_page()
    scanned_time = snapshot.scanned_at.strftime("%H:%M:%S")
    controller.scan_time_label.config(
        text=f"{snapshot.system_label} • scanned {scanned_time}"
    )
    controller.refreshed_label.config(text=f"Last refreshed: {scanned_time}")
    controller._set_busy(False)
    controller._for_each_presentation_target(
        lambda label, bar: (
            scan_status.apply_complete(label, bar, controller._progress_total())
            if bar is not None
            else label.config(
                text=scan_status.COMPLETE_TEXT, style=scan_status.READY_STYLE
            )
        )
    )
    controller._completion_transition().start(
        controller.COMPLETION_HOLD_MILLISECONDS,
        controller._show_ready_after_completion_hold,
    )
    controller._refresh_health()
    controller._refresh_thermals_page(
        controller._thermal_render_state(context) if context is not None else None
    )
    controller._component_scheduler.mark_all_refreshed(time.monotonic())
    controller._schedule_component_poll(force=True)


def show_ready_after_completion_hold(controller: Any) -> None:
    if controller._is_closing or controller._scan_coordinator_state().active:
        return
    controller._for_each_presentation_target(
        lambda label, _bar: scan_status.apply_ready(label)
    )


def refresh_health(controller: Any) -> None:
    if not isinstance(controller.snapshot, _window_symbols().DashboardSnapshot):
        return
    warnings = health_warnings(
        controller.snapshot, controller.__dict__.setdefault("_health_state", {})
    )
    if warnings:
        controller.health_label.config(
            text="Health: " + " · ".join(warnings), style="HealthWarning.TLabel"
        )
    else:
        controller.health_label.config(
            text="Health: No issues detected", style="Healthy.TLabel"
        )


def open_resource(controller: Any, resource_key: str) -> None:
    window = _window_symbols()
    if controller.snapshot is None:
        window.messagebox.showinfo(
            "Scan Required",
            "Run the system scan before opening resource details.",
            parent=controller.master,
        )
        return
    summary = controller.snapshot.get(resource_key)
    feature = controller._feature_catalog.get(resource_key)
    context = controller._selected_context()
    if (
        context is not None
        and not render_target_state(
            context.descriptor, context.snapshot, resource_key
        ).can_review
    ):
        controller._nodes_error(
            f"{context.descriptor.display_name} is not available for {resource_key} review"
        )
        return
    node_id = context.node_id if context is not None else None
    node_title = (
        context.descriptor.display_name
        if context is not None and controller._multi_node_selectable()
        else None
    )
    if feature.action_kind == "process":
        if context is not None and not (
            context.descriptor.has(NodeCapability.PROCESS_REVIEW)
            and NodePermission.PROCESS_REVIEW in context.descriptor.permissions
        ):
            controller._nodes_error("This node is not authorised for process review")
            return
        read_only = context is not None and not (
            context.descriptor.has(NodeCapability.PROCESS_TERMINATION)
            and NodePermission.PROCESS_TERMINATION in context.descriptor.permissions
        )
        window.ProcessDialog(
            controller.master,
            analyzer=context.provider if context is not None else controller.analyzer,
            provider=context.provider if context is not None else controller.analyzer,
            manager=context.process_manager
            if context is not None
            else controller.process_manager,
            resource_key=resource_key,
            colors=controller.colors,
            on_changed=lambda: controller._rescan_node_after_change(node_id),
            coordinator=controller._coordinator,
            node_id=node_id,
            node_title=node_title,
            read_only=read_only,
        )
    elif feature.action_kind == "storage":
        if context is not None and not (
            context.descriptor.has(NodeCapability.STORAGE_REVIEW)
            and NodePermission.STORAGE_REVIEW in context.descriptor.permissions
        ):
            controller._nodes_error("This node is not authorised for storage review")
            return
        window.StorageDialog(
            controller.master,
            analyzer=context.provider if context is not None else controller.analyzer,
            provider=context.provider if context is not None else controller.analyzer,
            manager=context.file_manager
            if context is not None
            else controller.file_manager,
            colors=controller.colors,
            on_changed=lambda: controller._rescan_node_after_change(node_id),
            coordinator=controller._coordinator,
            node_id=node_id,
            node_title=node_title,
            read_only=context is not None,
        )
    else:
        window.InfoDialog(controller.master, summary=summary, colors=controller.colors)


def _window_symbols() -> Any:
    import window

    return window
