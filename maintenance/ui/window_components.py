"""Component polling and dashboard projection adapters for ``AppWindow``."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, cast

from maintenance.components.coordinator import ComponentRefreshScheduler
from maintenance.components.scan_support import call_legacy_compatible
from maintenance.components.temperature import (
    TemperatureRenderState,
    TemperatureTelemetryUpdate,
)
from maintenance.models import CapabilityState, ResourceSummary, unavailable_summary
from maintenance.nodes import NodeId
from maintenance.ui import render_coordinator as ui_render
from maintenance.ui import styles as ui_styles
from maintenance.ui.window_supports import card_policy, snapshot_state


def _window_symbols() -> Any:
    # Preserve window-module patch seams for constants and Tk widget classes.
    import window

    return window


def component_poll_delay(controller: Any) -> int | None:
    scheduler = controller.__dict__.get("_component_scheduler")
    if scheduler is None:
        return None
    now = time.monotonic()
    deadline = scheduler.next_deadline(now)
    if (
        getattr(controller, "snapshot", None) is None
        or controller.__dict__.get("_full_snapshot_applied_at") is None
    ):
        has_pending = scheduler.has_pending_work()
        if deadline is None:
            return None if has_pending else controller.COMPONENT_POLL_MILLISECONDS
        if deadline > now:
            return max(0, int((deadline - now) * 1000))
        return 0 if has_pending else controller.COMPONENT_POLL_MILLISECONDS
    if deadline is None:
        return None
    return max(0, int((deadline - now) * 1000))


def schedule_component_poll(
    controller: Any, *, force: bool = False, delay_override: int | None = None
) -> None:
    if controller._is_closing:
        return
    delay = (
        delay_override
        if delay_override is not None
        else controller._component_poll_delay()
    )
    if delay is None:
        if controller._component_poll_id is not None:
            controller._cancel_timer(controller._component_poll_id)
            controller._component_poll_id = None
        return
    if controller._component_poll_id is not None and not force:
        return
    if controller._component_poll_id is not None:
        controller._cancel_timer(controller._component_poll_id)
        controller._component_poll_id = None
    controller._component_poll_id = controller._schedule_timer(
        delay, controller._run_component_cycle
    )


def run_component_cycle(controller: Any) -> None:
    controller._component_poll_id = None
    if controller._is_closing:
        return
    router = controller.__dict__.get("_page_router")
    dashboard_visible = router is None or router.is_mapped(
        _window_symbols().DASHBOARD_PAGE
    )
    deferred_work = False
    for key in controller._component_scheduler.due_keys(time.monotonic()):
        operation_key = controller._operation_key(f"component:{key}")
        if dashboard_visible:
            controller._launch_component_scan(key)
        else:
            deferred_work = True

            def launch_deferred_component(component_key: str = key) -> None:
                controller._launch_component_scan(component_key)

            controller._coordinator.defer(operation_key, launch_deferred_component)
    controller._schedule_component_poll(
        force=True,
        delay_override=(
            controller.COMPONENT_POLL_MILLISECONDS if deferred_work else None
        ),
    )


def launch_component_scan(controller: Any, key: str) -> None:
    source_context = controller._selected_context()
    source_node_id = controller.__dict__.get("_selected_node_id")
    source_scheduler = controller._component_scheduler
    source_provider = controller.analyzer
    if source_context is not None:
        source_scheduler = source_context.scheduler
        source_provider = source_context.provider
    operation_key = controller._operation_key(f"component:{key}")
    coordinator_active = controller._coordinator.in_flight(operation_key)
    scheduler_active = source_scheduler.in_flight(key)
    if coordinator_active and scheduler_active:
        source_scheduler.request_refresh(key)
        return
    if not source_scheduler.begin(key, time.monotonic()):
        return
    started_at = time.monotonic()

    def task_factory(
        cancel_event: threading.Event, _progress: Callable[[str], None]
    ) -> ResourceSummary:
        return call_legacy_compatible(
            lambda: source_provider.component_summary(key, cancel_event=cancel_event),
            lambda: source_provider.component_summary(key),
        )

    def finish_component() -> None:
        source_scheduler.finish(key)
        controller._schedule_component_poll(force=True)

    def queue_result(value: ResourceSummary | Exception) -> None:
        generation = controller._coordinator.generation(operation_key)
        controller._request_render(
            ui_render.RenderIntent(
                target=f"component:{key}",
                generation=generation,
                node_id=source_node_id,
                components=frozenset({key}),
                payload=value,
                payload_set=True,
                priority=2,
            ),
            lambda intent: controller._queue_component_result(
                key,
                started_at,
                cast(ResourceSummary | Exception, intent.payload),
                node_id=source_node_id,
                scheduler_finished=True,
            ),
        )

    run_generation = controller._coordinator.run(
        operation_key,
        task_factory,
        on_result=lambda _operation, resource: queue_result(resource),
        on_error=lambda _operation, message: queue_result(RuntimeError(message)),
        on_finished=finish_component,
    )
    if run_generation is None:
        source_scheduler.finish(key)
        source_scheduler.request_refresh(key)
        controller._schedule_component_poll(force=True)


def queue_component_result(
    controller: Any,
    key: str,
    started_at: float,
    value: ResourceSummary | Exception,
    *,
    node_id: NodeId | None = None,
    scheduler: ComponentRefreshScheduler | None = None,
    scheduler_finished: bool = False,
) -> None:
    source_scheduler = scheduler or controller._component_scheduler
    if not scheduler_finished:
        source_scheduler.finish(key)
    try:
        if node_id is not None and node_id != controller.__dict__.get(
            "_selected_node_id"
        ):
            return
        applied_at = controller.__dict__.get("_full_snapshot_applied_at")
        if applied_at is not None and started_at < applied_at:
            return
        resource = (
            failed_component_summary(controller, key)
            if isinstance(value, Exception)
            else value
        )
        apply_component(controller, key, resource)
    finally:
        controller._schedule_component_poll(force=True)


def failed_component_summary(controller: Any, key: str) -> ResourceSummary:
    return unavailable_summary(key, fallback_component_title(controller, key))


def record_thermal_summary(
    controller: Any, key: str, resource: ResourceSummary
) -> TemperatureTelemetryUpdate | None:
    context = controller._selected_context()
    telemetry = getattr(context, "telemetry", None) if context is not None else None
    return telemetry.record_summary(key, resource) if telemetry is not None else None


def thermal_render_state(controller: Any, context: Any) -> TemperatureRenderState:
    return context.telemetry.render_state(("cpu", "gpu", "storage", "battery"))


def refresh_thermals_page(
    controller: Any, state: TemperatureRenderState | None = None
) -> None:
    page = getattr(controller, "thermals_page", None)
    context = controller._selected_context()
    if page is None or context is None:
        return
    state = state or thermal_render_state(controller, context)
    intent = ui_render.RenderIntent(
        target=_window_symbols().THERMALS_PAGE,
        node_id=context.node_id,
        components=frozenset({"temperature"}),
        payload=state,
        payload_set=True,
        priority=2,
    )
    controller._request_render(
        intent, lambda _intent: page.render(state, context.capabilities)
    )


def fallback_component_title(controller: Any, key: str) -> str:
    return controller._feature_catalog.title_for(key) or key


def apply_component(controller: Any, key: str, resource: ResourceSummary) -> None:
    if controller._is_closing:
        return
    observe_capability(controller, key, resource)
    record_thermal_summary(controller, key, resource)
    displayed = merge_resource(controller, key, resource)
    coordinator = controller.__dict__.get("_coordinator")
    if coordinator is not None:
        coordinator.store(controller._operation_key(f"component:{key}"), displayed)
    if key in controller.cards:
        controller.cards[key].update_summary(displayed)
    update_snapshot_resource(controller, key, displayed)
    context = controller._selected_context()
    refresh_thermals_page(
        controller,
        thermal_render_state(controller, context) if context is not None else None,
    )
    controller._refresh_health()


def observe_capability(controller: Any, key: str, resource: ResourceSummary) -> None:
    state = resource.capability
    if state == CapabilityState.UNKNOWN:
        return
    capabilities = controller.__dict__.setdefault("_capabilities", {})
    counts = controller.__dict__.setdefault("_capability_counts", {})
    if state == CapabilityState.SUPPORTED:
        counts[key] = 0
        if capabilities.get(key) != state:
            capabilities[key] = state
            reconcile_cards_and_polling(controller)
        return
    counts[key] = counts.get(key, 0) + 1
    if counts[key] < controller.UNSUPPORTED_CONFIRM_LIMIT:
        return
    if capabilities.get(key) != state:
        capabilities[key] = state
        reconcile_cards_and_polling(controller)


def is_card_visible(controller: Any, key: str) -> bool:
    return card_policy.is_card_visible(
        key,
        preferences=controller.__dict__.get("_preferences"),
        capabilities=controller.__dict__.get("_capabilities", {}),
    )


def polling_policy(controller: Any, key: str) -> bool:
    return card_policy.should_pause_polling(
        key,
        preferences=controller.__dict__.get("_preferences"),
        capabilities=controller.__dict__.get("_capabilities", {}),
    )


def grid_card(card: Any, index: int, columns: int) -> None:
    card.grid(
        row=index // columns,
        column=index % columns,
        sticky="nsew",
        padx=(
            0 if index % columns == 0 else ui_styles.LAYOUT["card_grid_gap"],
            0 if index % columns == columns - 1 else ui_styles.LAYOUT["card_grid_gap"],
        ),
        pady=(0, ui_styles.LAYOUT["card_row_gap"]),
    )


def layout_dashboard_cards(controller: Any) -> None:
    features = controller.__dict__.get("_feature_catalog")
    cards = controller.__dict__.get("cards")
    if features is None or cards is None:
        return
    visible = [
        feature
        for feature in features.all()
        if is_card_visible(controller, feature.key)
    ]
    for card in cards.values():
        card.grid_forget()
    empty_label = controller.__dict__.get("cards_empty_label")
    if not visible:
        if empty_label is None:
            ttk = _window_symbols().ttk
            empty_label = ttk.Label(
                controller.cards_frame,
                text="No cards are enabled. Open Settings to choose which cards to show.",
                style="Description.TLabel",
            )
            controller.__dict__["cards_empty_label"] = empty_label
        empty_label.grid(row=0, column=0, sticky="w", padx=2, pady=8)
        controller._refresh_cards_scrollbar()
        return
    if empty_label is not None:
        empty_label.grid_forget()
    columns = min(3, len(visible))
    for column in range(3):
        controller.cards_frame.grid_columnconfigure(
            column,
            weight=1 if column < columns else 0,
            uniform="cards" if column < columns else "",
        )
    for index, feature in enumerate(visible):
        grid_card(cards[feature.key], index, columns)
    controller._refresh_cards_scrollbar()


def reconcile_cards_and_polling(controller: Any) -> None:
    scheduler = controller.__dict__.get("_component_scheduler")
    if scheduler is None:
        return
    layout_dashboard_cards(controller)
    features = controller.__dict__.get("_feature_catalog")
    if features is None:
        return
    for feature in features.all():
        key = feature.key
        if polling_policy(controller, key):
            scheduler.pause(key)
            continue
        was_paused = scheduler.is_paused(key)
        scheduler.resume(key)
        if was_paused:
            request_component_refresh(controller, key)


def request_component_refresh(controller: Any, key: str) -> None:
    if controller._scan_coordinator_state().active or not controller.__dict__.get(
        "_full_snapshot_applied_at"
    ):
        return
    analyzer = getattr(controller, "analyzer", None)
    if analyzer is not None and hasattr(analyzer, "reset_component_sample"):
        analyzer.reset_component_sample(key)
    controller._component_scheduler.request_refresh(key)
    controller._schedule_component_poll(force=True)


def reconcile_intervals(controller: Any) -> None:
    now = time.monotonic()
    current = controller._component_scheduler.intervals
    for (
        key,
        milliseconds,
    ) in controller._preferences.refresh_intervals.as_dict().items():
        if current.get(key) != milliseconds:
            controller._component_scheduler.set_interval(key, milliseconds, now)
    controller._schedule_component_poll(force=True)


def update_snapshot_resource(
    controller: Any, key: str, resource: ResourceSummary
) -> None:
    updated = snapshot_state.replace_snapshot_resource(
        controller.snapshot, key, resource
    )
    if updated is None:
        return
    controller.snapshot = updated
    context = controller._selected_context()
    if context is not None:
        context.snapshot = controller.snapshot


def merge_snapshot(controller: Any, snapshot: Any) -> Any:
    return snapshot_state.merge_snapshot(
        previous_snapshot=controller.snapshot,
        failed_counts=controller.__dict__.setdefault("_failed_card_counts", {}),
        snapshot=snapshot,
        failed_card_keep_limit=controller.FAILED_CARD_KEEP_LIMIT,
    )


def merge_resource(
    controller: Any, key: str, resource: ResourceSummary
) -> ResourceSummary:
    return snapshot_state.merge_resource(
        previous_snapshot=controller.snapshot,
        failed_counts=controller.__dict__.setdefault("_failed_card_counts", {}),
        key=key,
        resource=resource,
        failed_card_keep_limit=controller.FAILED_CARD_KEEP_LIMIT,
    )
