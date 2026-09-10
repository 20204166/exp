"""Dashboard scan orchestration adapters for :class:`window.AppWindow`."""

from __future__ import annotations

import threading
import time
from typing import Any, cast

from maintenance.models import DashboardSnapshot
from maintenance.nodes import (
    ConnectionState,
    NodeConnectionStatus,
    NodeId,
    NodeSnapshot,
)
from maintenance.ui import render_coordinator as ui_render


def _window_symbols() -> Any:
    # Keep historical window-module patch seams for provider compatibility.
    import window

    return window


def scan_coordinator_state(controller: Any) -> Any:
    coordinator = controller.__dict__.get("_scan_coordinator")
    if coordinator is None:
        window = _window_symbols()
        coordinator = window.ScanCoordinator()
        controller.__dict__["_scan_coordinator"] = coordinator
    return coordinator


def dashboard_scan_lifecycle(controller: Any) -> Any:
    lifecycle = controller.__dict__.get("_dashboard_scan_lifecycle_obj")
    if lifecycle is None:
        window = _window_symbols()
        lifecycle = window.DashboardScanLifecycle(
            coordinator=controller._scan_coordinator_state(),
            is_closing=lambda: controller._is_closing,
            schedule_timer=controller._schedule_timer,
            cancel_timer=controller._cancel_timer,
            show_timeout_error=controller._show_error,
            schedule_rerun=lambda: controller._schedule_rerun_if_requested(True),
            timeout_callback=controller._handle_scan_timeout,
            grace_callback=controller._release_lease_after_grace,
            timeout_milliseconds=controller.SCAN_TIMEOUT_MILLISECONDS,
            grace_milliseconds=controller.SCAN_LEASE_GRACE_MILLISECONDS,
            timeout_message=controller.SCAN_TIMEOUT_MESSAGE,
        )
        lifecycle.cancel_event = controller.__dict__.get("_analysis_cancel_event")
        lifecycle.timeout_id = controller.__dict__.get("_scan_timeout_id")
        lifecycle.lease_grace_id = controller.__dict__.get("_lease_grace_id")
        lifecycle.timed_out_generation = controller.__dict__.get(
            "_timed_out_generation"
        )
        lifecycle.resolved_generation = controller.__dict__.get(
            "_resolved_scan_generation", 0
        )
        controller.__dict__["_dashboard_scan_lifecycle_obj"] = lifecycle
    return lifecycle


def sync_dashboard_scan_state(controller: Any) -> None:
    lifecycle = controller._dashboard_scan_lifecycle()
    controller.__dict__.update(
        _analysis_cancel_event=lifecycle.cancel_event,
        _scan_timeout_id=lifecycle.timeout_id,
        _lease_grace_id=lifecycle.lease_grace_id,
        _timed_out_generation=lifecycle.timed_out_generation,
        _resolved_scan_generation=lifecycle.resolved_generation,
    )


def handle_analyze(controller: Any) -> None:
    if controller._is_closing:
        return
    source_node_id = controller.__dict__.get("_selected_node_id")
    source_context = controller._selected_context()
    source_provider = (
        source_context.provider if source_context is not None else controller.analyzer
    )

    def on_started(generation: int, _cancel_event: threading.Event) -> None:
        coordinator = controller._render_coordinator()
        if coordinator is not None:
            coordinator.invalidate("scan-status", generation, node_id=source_node_id)
            coordinator.invalidate(
                "dashboard-snapshot", generation, node_id=source_node_id
            )

    def start_worker(generation: int, cancel_event: threading.Event) -> None:
        resolved_node_snapshot: NodeSnapshot | None = None

        def report_progress(message: str) -> None:
            controller._submit_ui(lambda: apply_progress(message))

        def apply_progress(message: str) -> None:
            if generation <= controller._resolved_scan_generation:
                return
            controller._request_render(
                ui_render.RenderIntent(
                    target="scan-status",
                    generation=generation,
                    node_id=source_node_id,
                    components=frozenset({"progress"}),
                    payload=message,
                    payload_set=True,
                    priority=1,
                ),
                lambda intent: controller._show_progress(cast(str, intent.payload)),
            )

        def dashboard_task() -> DashboardSnapshot:
            window = _window_symbols()
            provider_snapshot = getattr(type(source_provider), "node_snapshot", None)
            if callable(provider_snapshot):
                provider_snapshot = cast(Any, source_provider).node_snapshot
                result = window.call_legacy_compatible(
                    lambda: provider_snapshot(
                        cancel_event=cancel_event,
                        progress_callback=report_progress,
                    ),
                    lambda: provider_snapshot(),
                )
            else:
                dashboard = window.call_legacy_compatible(
                    lambda: source_provider.dashboard_snapshot(
                        cancel_event=cancel_event,
                        progress_callback=report_progress,
                    ),
                    lambda: source_provider.dashboard_snapshot(),
                )
                descriptor = (
                    source_context.descriptor
                    if source_context is not None
                    else window.local_node_descriptor()
                )
                result = window.LocalNodeProvider(
                    source_provider, descriptor
                ).snapshot_from_dashboard(dashboard)
            if not isinstance(result, NodeSnapshot):
                raise TypeError("provider returned an invalid node snapshot")
            if source_node_id is not None and result.node_id != source_node_id:
                raise RuntimeError("provider returned the wrong node snapshot")
            if result.dashboard is None:
                raise RuntimeError("provider returned no dashboard data")
            nonlocal resolved_node_snapshot
            resolved_node_snapshot = result
            return result.dashboard

        def queue_snapshot(snapshot: DashboardSnapshot) -> None:
            # Lifecycle completion cannot wait for a hidden page to render.
            rerun_requested = controller._resolution_for_generation(generation)
            if rerun_requested is None:
                return
            controller._set_busy(False)
            controller._request_render(
                ui_render.RenderIntent(
                    target="dashboard-snapshot",
                    generation=generation,
                    node_id=source_node_id,
                    components=frozenset({"snapshot"}),
                    layout_changed=True,
                    payload=resolved_node_snapshot,
                    payload_set=True,
                    priority=3,
                ),
                lambda intent: controller._show_node_snapshot_if_current(
                    generation,
                    cast(NodeSnapshot, intent.payload),
                    node_id=source_node_id,
                ),
            )
            controller._schedule_rerun_if_requested(rerun_requested)

        controller._run_in_background(
            dashboard_task,
            on_success=queue_snapshot,
            on_error=lambda message: controller._show_error_for_generation(
                generation, message, node_id=source_node_id
            ),
        )

    controller._dashboard_scan_lifecycle().start(on_started, start_worker)
    controller._sync_dashboard_scan_state()


def claim_scan_resolution(controller: Any, generation: int) -> tuple[bool, bool]:
    result = controller._dashboard_scan_lifecycle().claim_resolution(generation)
    controller._sync_dashboard_scan_state()
    return result


def handle_scan_timeout(controller: Any, generation: int) -> None:
    controller._dashboard_scan_lifecycle().handle_timeout(generation)
    controller._sync_dashboard_scan_state()


def release_timed_out_lease(
    controller: Any, generation: int, *, cancel_grace_timer: bool
) -> None:
    controller._dashboard_scan_lifecycle().release_timed_out_lease(
        generation, cancel_grace_timer=cancel_grace_timer
    )
    controller._sync_dashboard_scan_state()


def release_lease_after_grace(controller: Any, generation: int) -> None:
    controller._dashboard_scan_lifecycle().release_lease_after_grace(generation)
    controller._sync_dashboard_scan_state()


def resolve_completed_worker(controller: Any) -> None:
    controller._dashboard_scan_lifecycle().resolve_completed_worker()
    controller._sync_dashboard_scan_state()


def cancel_scan_timeout(controller: Any) -> None:
    controller._dashboard_scan_lifecycle().cancel_timeout()
    controller._sync_dashboard_scan_state()


def resolve_generation(controller: Any, generation: int) -> tuple[bool, bool]:
    result = controller._dashboard_scan_lifecycle().resolve_generation(generation)
    controller._sync_dashboard_scan_state()
    return result


def schedule_rerun_if_requested(controller: Any, rerun_requested: bool) -> None:
    if rerun_requested and not controller._is_closing:
        controller._schedule_timer(0, controller.handle_analyze)


def resolution_for_generation(controller: Any, generation: int) -> bool | None:
    result = controller._dashboard_scan_lifecycle().resolution_for_generation(
        generation
    )
    controller._sync_dashboard_scan_state()
    return result


def show_snapshot_for_generation(
    controller: Any,
    generation: int,
    snapshot: DashboardSnapshot,
    *,
    node_snapshot: NodeSnapshot | None = None,
    node_id: NodeId | None = None,
) -> None:
    rerun_requested = controller._resolution_for_generation(generation)
    if rerun_requested is None:
        return
    if node_id is None or node_id == controller.__dict__.get("_selected_node_id"):
        controller._show_snapshot(snapshot, node_snapshot=node_snapshot)
    controller._schedule_rerun_if_requested(rerun_requested)


def show_node_snapshot_if_current(
    controller: Any,
    generation: int,
    node_snapshot: NodeSnapshot,
    *,
    node_id: NodeId | None = None,
) -> None:
    if node_snapshot.dashboard is None:
        return
    controller._show_snapshot_if_current(
        generation,
        node_snapshot.dashboard,
        node_snapshot=node_snapshot,
        node_id=node_id,
    )


def show_snapshot_if_current(
    controller: Any,
    generation: int,
    snapshot: DashboardSnapshot,
    *,
    node_snapshot: NodeSnapshot | None = None,
    node_id: NodeId | None = None,
) -> None:
    if generation != controller._scan_coordinator_state().generation:
        return
    if node_id is not None and node_id != controller.__dict__.get("_selected_node_id"):
        return
    controller._show_snapshot(snapshot, node_snapshot=node_snapshot)


def show_error_for_generation(
    controller: Any,
    generation: int,
    message: str,
    *,
    node_id: NodeId | None = None,
) -> None:
    window = _window_symbols()
    rerun_requested = controller._resolution_for_generation(generation)
    if rerun_requested is None:
        return
    if node_id is not None:
        try:
            context = controller._node_registry.context(node_id)
        except (AttributeError, KeyError):
            context = None
        if context is not None and not context.descriptor.is_local:
            status = (
                NodeConnectionStatus.AUTHENTICATION_FAILED
                if "author" in message.lower()
                else NodeConnectionStatus.OFFLINE
            )
            context.connection = ConnectionState(
                status,
                reason=message,
                changed_at=time.monotonic(),
            )
    if node_id is not None and node_id != controller.__dict__.get("_selected_node_id"):
        controller._schedule_rerun_if_requested(rerun_requested)
        return
    if message == window.DOWNLOADS_SCAN_CANCELLED:
        controller._set_busy(False)
        controller._reset_progress_bar()
        controller.refreshed_label.config(text=window.SCAN_CANCELLED_NOTICE)
        controller._schedule_rerun_if_requested(rerun_requested)
        return
    controller._show_error(message)
    controller._schedule_rerun_if_requested(rerun_requested)
