"""Background, presentation, timer, and shutdown adapters for ``AppWindow``."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from typing import Any

from maintenance.components.background_orchestration import BackgroundOrchestrator
from maintenance.components.background_orchestration import (
    run_daemon as run_daemon_impl,
)
from maintenance.ui import render_coordinator as ui_render
from maintenance.ui import scan_status
from maintenance.ui import styles as ui_styles
from maintenance.ui import transition as ui_transition
from maintenance.ui.window_supports.timer_delivery import TimerDelivery

LOGGER = logging.getLogger(__name__)


def make_background_orchestrator(controller: Any) -> BackgroundOrchestrator:
    return BackgroundOrchestrator(
        queue=controller._background_queue,
        is_closing=lambda: controller._is_closing,
        schedule_timer=lambda delay, callback: controller._schedule_timer(
            delay, callback
        ),
        get_poll_id=lambda: controller._background_poll_id,
        set_poll_id=lambda identifier: setattr(
            controller, "_background_poll_id", identifier
        ),
        get_task_count=lambda: controller._background_tasks,
        set_task_count=lambda count: setattr(controller, "_background_tasks", count),
        set_busy=lambda busy: controller._set_busy(busy),
        resolve_completed_worker=lambda: controller._resolve_completed_worker(),
        get_render_coordinator=controller._render_coordinator,
        has_pending_coordinator_work=lambda: (
            (coordinator := controller.__dict__.get("_coordinator")) is not None
            and coordinator.has_pending_work
        ),
        has_discovery_tick=lambda: (
            controller.__dict__.get("_discovery_tick_id") is not None
        ),
        invoke_delivered=lambda callback: controller._invoke_delivered(callback),
        poll_milliseconds=controller.BACKGROUND_POLL_MILLISECONDS,
        logger=_window_symbols().LOGGER,
    )


def background_service(controller: Any) -> BackgroundOrchestrator:
    service = controller.__dict__.get("_background_orchestrator")
    if service is None:
        service = controller._make_background_orchestrator()
        controller.__dict__["_background_orchestrator"] = service
    return service


def render_coordinator(controller: Any) -> ui_render.UICoordinator | None:
    return getattr(controller, "_ui_coordinator", None)


def request_render(
    controller: Any,
    intent: ui_render.RenderIntent,
    apply: Callable[[ui_render.RenderIntent], None],
) -> bool:
    coordinator = controller._render_coordinator()
    if coordinator is None:
        apply(intent)
        return True
    return coordinator.request(intent, apply)


def sync_render_visibility(controller: Any, active_page: str | None) -> None:
    window = _window_symbols()
    discovery_pages_visible = active_page in {window.NODES_PAGE, window.CLUSTER_PAGE}
    controller.__dict__["_discovery_pages_visible"] = discovery_pages_visible
    app_coordinator = controller.__dict__.get("_coordinator")
    if discovery_pages_visible and app_coordinator is not None:
        app_coordinator.flush_deferred("discovery-pages")
    render = controller._render_coordinator()
    if render is None:
        return
    dashboard_visible = active_page == window.DASHBOARD_PAGE
    render.set_visible("dashboard-snapshot", dashboard_visible)
    render.set_visible(
        "scan-status", active_page in {window.DASHBOARD_PAGE, window.PREFERENCES_PAGE}
    )
    render.set_visible("dashboard-discovery", dashboard_visible)
    render.set_visible(window.THERMALS_PAGE, active_page == window.THERMALS_PAGE)
    render.set_visible("discovery-pages", discovery_pages_visible)
    render.set_visible("nodes-status", active_page == window.NODES_PAGE)
    for feature in controller._feature_catalog.all():
        render.set_visible(f"component:{feature.key}", dashboard_visible)
        if dashboard_visible and app_coordinator is not None:
            app_coordinator.flush_deferred(
                controller._operation_key(f"component:{feature.key}")
            )


def configure_styles(controller: Any) -> None:
    style = _window_symbols().ttk.Style(controller.master)
    style.theme_use("clam")
    ui_styles.configure_app_styles(style, colors=controller.colors)
    controller._style_obj = style


def apply_appearance(controller: Any) -> None:
    style = getattr(controller, "_style_obj", None)
    if style is None:
        return
    colors = ui_styles.accent_theme_colors(controller._preferences.appearance)
    ui_styles.configure_app_styles(style, colors=colors)
    cards = getattr(controller, "cards", None)
    if cards:
        for card in cards.values():
            apply = getattr(card, "apply_colors", None)
            if apply is not None:
                apply(colors)


def presentation_targets(controller: Any) -> list[tuple[Any, Any]]:
    targets: list[tuple[Any, Any | None]] = [(controller.status_label, None)]
    label = getattr(controller, "preferences_status_label", None)
    bar = getattr(controller, "preferences_progress_bar", None)
    if label is not None and bar is not None:
        targets.append((label, bar))
    return targets


def for_each_presentation_target(
    controller: Any, action: Callable[[Any, Any], Any]
) -> None:
    for label, bar in controller._presentation_targets():
        action(label, bar)


def set_busy(controller: Any, is_busy: bool) -> None:
    controller.analyze_button.config(state=tk.DISABLED if is_busy else tk.NORMAL)
    controller.cancel_button.config(state=tk.NORMAL if is_busy else tk.DISABLED)
    coordinator = getattr(controller, "_button_coordinator", None)
    if coordinator is not None:
        if "preferences:scan" in coordinator.registered_ids():
            coordinator.set_enabled("preferences:scan", not is_busy)
        if "preferences:cancel-scan" in coordinator.registered_ids():
            coordinator.set_enabled("preferences:cancel-scan", is_busy)
    if is_busy:
        controller.__dict__["_scan_progress_count"] = 0
        controller._completion_transition().cancel()

        def apply_scanning_state(label: Any, bar: Any) -> None:
            if bar is not None:
                scan_status.apply_reset(bar)
            scan_status.apply_scanning(label)

        controller._for_each_presentation_target(apply_scanning_state)
    else:

        def apply_ready_state(label: Any, bar: Any) -> None:
            scan_status.apply_ready(label)
            if bar is not None:
                bar.stop()

        controller._for_each_presentation_target(apply_ready_state)


def completion_transition(controller: Any) -> ui_transition.PendingTransition:
    return controller.__dict__.setdefault(
        "_completion_transition_obj",
        ui_transition.PendingTransition(
            controller._schedule_timer, controller._cancel_timer
        ),
    )


def cancel_analysis(controller: Any) -> None:
    if controller._analysis_cancel_event is None:
        return
    controller._analysis_cancel_event.set()
    controller.cancel_button.config(state=tk.DISABLED)
    coordinator = getattr(controller, "_button_coordinator", None)
    if (
        coordinator is not None
        and "preferences:cancel-scan" in coordinator.registered_ids()
    ):
        coordinator.set_enabled("preferences:cancel-scan", False)
    controller._for_each_presentation_target(
        lambda label, _bar: scan_status.apply_cancelling(label)
    )


def progress_total(controller: Any) -> int:
    return len(controller._feature_catalog.all())


def show_progress(controller: Any, message: str) -> None:
    if controller._is_closing:
        return
    count = controller.__dict__.get("_scan_progress_count", 0) + 1
    controller.__dict__["_scan_progress_count"] = count
    total = controller._progress_total()
    for label, bar in controller._presentation_targets():
        if bar is not None:
            scan_status.apply_step(label, bar, message, count, total)
        else:
            label.config(text=scan_status.progress_text(message, count, total))


def run_daemon(
    controller: Any,
    task: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[Exception], None],
    on_finished: Callable[[], None] | None = None,
) -> None:
    if "_background_queue" not in controller.__dict__:
        run_daemon_impl(
            task, on_success, on_error, on_finished, logger=_window_symbols().LOGGER
        )
        return
    controller._background_service().run_daemon(task, on_success, on_error, on_finished)


def run_in_background(
    controller: Any,
    task: Callable[[], Any],
    on_success: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> bool:
    return controller._background_service().run_in_background(
        task,
        on_success or controller._show_snapshot,
        on_error or controller._show_error,
        daemon_runner=controller._run_daemon,
    )


def submit_ui(controller: Any, callback: Callable[[], None]) -> None:
    controller._background_service().submit_ui(callback)


def start_background_poll(controller: Any) -> None:
    controller._background_service().start_poll()


def drain_background_queue(controller: Any) -> None:
    controller._background_service().drain_queue()


def invoke_delivered(callback: Callable[[], None]) -> None:
    TimerDelivery.invoke(callback, _window_symbols().LOGGER)


def schedule_timer(
    controller: Any, delay: int, callback: Callable[..., None], *args: object
) -> str | None:
    return controller._timer_delivery_for_window().schedule(delay, callback, *args)


def cancel_timer(controller: Any, identifier: str | None) -> bool:
    return controller._timer_delivery_for_window().cancel(identifier)


def cancel_pending_timers(controller: Any) -> None:
    controller._timer_delivery_for_window().cancel_all()


def timer_delivery_for_window(controller: Any) -> TimerDelivery:
    timer_delivery = controller.__dict__.get("_timer_delivery")
    if timer_delivery is None:
        timer_delivery = TimerDelivery(
            master=controller.master,
            is_closing=lambda: controller._is_closing,
            pending_ids=controller._pending_after_ids,
            logger=_window_symbols().LOGGER,
        )
        controller.__dict__["_timer_delivery"] = timer_delivery
    return timer_delivery


def finalize_shutdown(controller: Any) -> None:
    peer_server = controller.__dict__.get("_peer_server")
    controller.__dict__["_peer_server"] = None
    if peer_server is not None:
        peer_server.stop()
    controller._stop_discovery()
    peer_manager = controller.__dict__.get("_peer_connection_manager")
    if peer_manager is not None:
        peer_manager.shutdown()
    controller._cancel_timer(controller.__dict__.get("_peer_reconcile_timer_id"))
    controller.__dict__["_peer_reconcile_timer_id"] = None
    controller._dashboard_scan_lifecycle().cancel()
    controller._sync_dashboard_scan_state()
    coordinator = controller.__dict__.get("_coordinator")
    if coordinator is not None:
        coordinator.cancel_all()
        coordinator.shutdown()
    controller._cancel_all_node_operations()
    cluster_page = getattr(controller, "cluster_page", None)
    if cluster_page is not None:
        cluster_page.dispose()
    controller._cancel_pending_timers()
    controller._component_poll_id = None
    controller._background_poll_id = None
    controller._scan_timeout_id = None
    render = controller._render_coordinator()
    if render is not None:
        render.shutdown()


def stop_all_node_workers(controller: Any) -> None:
    analyzer = getattr(controller, "analyzer", None)
    stop_workers = getattr(analyzer, "stop_background_workers", None)
    if stop_workers is not None:
        stop_workers()
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    for context in registry.contexts():
        if context.provider is analyzer:
            continue
        stop = getattr(context.provider, "stop_background_workers", None)
        if stop is not None:
            stop()


def close(controller: Any) -> None:
    controller._is_closing = True
    controller._finalize_shutdown()
    if controller._analysis_cancel_event is not None:
        controller._analysis_cancel_event.set()
    controller._analysis_cancel_event = None
    controller._stop_all_node_workers()
    controller.master.destroy()


def reset_progress_bar(controller: Any) -> None:
    controller._completion_transition().cancel()
    controller._for_each_presentation_target(
        lambda _label, bar: scan_status.apply_reset(bar) if bar is not None else None
    )


def show_error(controller: Any, message: str) -> None:
    if controller._is_closing:
        return
    controller._set_busy(False)
    controller._reset_progress_bar()
    _window_symbols().messagebox.showerror(
        "Analysis Error", message, parent=controller.master
    )


def run(controller: Any) -> None:
    try:
        controller.master.mainloop()
    except KeyboardInterrupt:
        controller._close()
    finally:
        if not controller._is_closing:
            controller._is_closing = True
            controller._finalize_shutdown()


def _window_symbols() -> Any:
    import window

    return window
