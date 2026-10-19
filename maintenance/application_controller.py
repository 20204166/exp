"""Toolkit-neutral application orchestration shared by desktop shells."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Iterable
from queue import Queue
from types import SimpleNamespace
from typing import Any

import algo
from maintenance.actions import FileManager, ProcessManager
from maintenance.application_state import initialize_application_state
from maintenance.cluster import ClusterStore, PeerGrantRecord, default_cluster_path
from maintenance.components import (
    CoordinatorTimeline,
    ResourceFeatureCatalog,
    ScanCoordinator,
    StandbyBuffer,
)
from maintenance.components.background_orchestration import BackgroundOrchestrator
from maintenance.components.coordinator import AppCoordinator, ComponentRefreshScheduler
from maintenance.diagnostics import developer_mode_enabled
from maintenance.health import health_warnings
from maintenance.nodes import NodeContext, NodeId, NodeRegistry
from maintenance.observability import ObservabilityWatcher
from maintenance.preferences import PreferencesStore, default_preferences_path
from maintenance.ui import (
    render_coordinator,
    window_components,
    window_discovery,
    window_node_runtime,
    window_page_data,
    window_preferences,
    window_scan,
)
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.window_context import (
    build_local_node_context,
    restore_trusted_nodes,
    save_cluster_state,
    sync_peer_listener_grants,
)
from maintenance.ui.window_supports.card_policy import is_card_visible

LOGGER = logging.getLogger(__name__)


def default_application_dependencies(
    *,
    preferences_store: PreferencesStore | None = None,
    cluster_store: ClusterStore | None = None,
    provision_target_grant: Callable[[PeerGrantRecord], bool] | None = None,
) -> SimpleNamespace:
    """Build service factories for a host that has no legacy patch seams."""
    return SimpleNamespace(
        analyzer_factory=algo.Analyzer,
        process_manager_factory=ProcessManager,
        file_manager_factory=FileManager,
        preferences_store_factory=lambda: (
            preferences_store or PreferencesStore(default_preferences_path())
        ),
        cluster_store_factory=lambda: (
            cluster_store or ClusterStore(default_cluster_path())
        ),
        timeline_factory=CoordinatorTimeline,
        standby_factory=StandbyBuffer,
        provision_target_grant=provision_target_grant,
        developer_mode=developer_mode_enabled(os.environ),
        observer_factory=ObservabilityWatcher,
        scan_coordinator_factory=ScanCoordinator,
        queue_factory=Queue,
        coordinator_factory=AppCoordinator,
        scheduler_factory=ComponentRefreshScheduler,
        button_factory=ButtonCoordinator,
        ui_coordinator_factory=render_coordinator.UICoordinator,
        catalog_factory=ResourceFeatureCatalog,
        registry_factory=NodeRegistry,
    )


class ApplicationController:
    """Own shared services and operations; concrete shells own presentation."""

    COMPONENT_POLL_MILLISECONDS = 1000
    COMPLETION_HOLD_MILLISECONDS = 500
    SCAN_TIMEOUT_MILLISECONDS = 30000
    SCAN_LEASE_GRACE_MILLISECONDS = 10000
    SCAN_TIMEOUT_MESSAGE = (
        "The system scan did not finish within 30 seconds and was stopped. "
        "A hardware query may be slow or unresponsive; try scanning again."
    )
    UNSUPPORTED_CONFIRM_LIMIT = 2
    FAILED_CARD_KEEP_LIMIT = 3
    BACKGROUND_POLL_MILLISECONDS = 10

    analyzer: Any
    process_manager: Any
    file_manager: Any
    snapshot: Any
    master: Any
    _preferences: Any
    _cluster_state: Any
    _developer_mode: bool
    _is_closing: bool
    _analysis_cancel_event: Any
    _background_queue: Any
    _background_tasks: int
    _background_poll_id: Any
    _coordinator: Any
    _ui_coordinator: Any
    _observer: Any
    _capabilities: dict[str, Any]
    _component_scheduler: Any
    _button_coordinator: ButtonCoordinator
    _feature_catalog: ResourceFeatureCatalog
    _node_registry: NodeRegistry
    _selected_node_id: Any
    _peer_server: Any
    _peer_connection_manager: Any
    _cluster_store: ClusterStore
    _cluster_timeline: Any
    _standby_buffer: Any
    preferences_page: Any
    nodes_page: Any
    cluster_page: Any
    cards: Any
    _health_state: dict[str, int]
    _health_warnings: tuple[str, ...]

    def __init__(self, *, master: Any, dependencies: Any) -> None:
        self.master = master
        initialize_application_state(self, dependencies=dependencies)

    @property
    def colors(self) -> dict[str, str]:
        from maintenance.ui import styles

        appearance = getattr(self._preferences, "appearance", styles.DEFAULT_APPEARANCE)
        return styles.accent_theme_colors(appearance)

    def _build_local_node_context(self) -> None:
        build_local_node_context(self)

    def _restore_trusted_nodes(self) -> None:
        restore_trusted_nodes(self)

    def _scan_coordinator_state(self) -> Any:
        return window_scan.scan_coordinator_state(self)

    def _dashboard_scan_lifecycle(self) -> Any:
        return window_scan.dashboard_scan_lifecycle(self)

    def _sync_dashboard_scan_state(self) -> None:
        window_scan.sync_dashboard_scan_state(self)

    def handle_analyze(self) -> None:
        window_scan.handle_analyze(self)

    def _cancel_active_scan(self) -> None:
        window_node_runtime.cancel_active_scan(self)

    def _cancel_analysis(self) -> None:
        window_scan.cancel_scan_timeout(self)
        self._cancel_active_scan()

    def _handle_scan_timeout(self, generation: int) -> None:
        window_scan.handle_scan_timeout(self, generation)

    def _release_lease_after_grace(self, generation: int) -> None:
        window_scan.release_lease_after_grace(self, generation)

    def _release_timed_out_lease(
        self, generation: int, *, cancel_grace_timer: bool
    ) -> None:
        window_scan.release_timed_out_lease(
            self, generation, cancel_grace_timer=cancel_grace_timer
        )

    def _resolution_for_generation(self, generation: int) -> bool | None:
        return window_scan.resolution_for_generation(self, generation)

    def _show_error_for_generation(
        self, generation: int, message: str, *, node_id: Any = None
    ) -> None:
        window_scan.show_error_for_generation(
            self, generation, message, node_id=node_id
        )

    def _show_node_snapshot_if_current(
        self, generation: int, node_snapshot: Any, *, node_id: Any = None
    ) -> None:
        window_scan.show_node_snapshot_if_current(
            self, generation, node_snapshot, node_id=node_id
        )

    def _resolve_completed_worker(self) -> None:
        window_scan.resolve_completed_worker(self)

    def _cancel_scan_timeout(self) -> None:
        window_scan.cancel_scan_timeout(self)

    def _claim_scan_resolution(self, generation: int) -> tuple[bool, bool]:
        return window_scan.claim_scan_resolution(self, generation)

    def _resolve_generation(self, generation: int) -> tuple[bool, bool]:
        return window_scan.resolve_generation(self, generation)

    def _schedule_rerun_if_requested(self, rerun_requested: bool) -> None:
        window_scan.schedule_rerun_if_requested(self, rerun_requested)

    def _progress_total(self) -> int:
        return len(self._feature_catalog.all())

    def _reconcile_cards_and_polling(self) -> None:
        window_components.reconcile_cards_and_polling(self)

    def _reconcile_intervals(self) -> None:
        window_components.reconcile_intervals(self)

    def _apply_appearance(self) -> None:
        # Appearance is a shell concern; implementations update their widgets.
        return None

    def _merge_snapshot(self, snapshot: Any) -> Any:
        return window_components.merge_snapshot(self, snapshot)

    def _merge_resource(self, key: str, resource: Any) -> Any:
        return window_components.merge_resource(self, key, resource)

    def _update_snapshot_resource(self, key: str, resource: Any) -> None:
        window_components.update_snapshot_resource(self, key, resource)

    def _failed_component_summary(self, key: str) -> Any:
        return window_components.failed_component_summary(self, key)

    def _queue_component_result(
        self,
        key: str,
        started_at: float,
        value: Any,
        *,
        node_id: Any = None,
        scheduler: Any = None,
        scheduler_finished: bool = False,
    ) -> None:
        window_components.queue_component_result(
            self,
            key,
            started_at,
            value,
            node_id=node_id,
            scheduler=scheduler,
            scheduler_finished=scheduler_finished,
        )

    def _request_render(self, intent: Any, apply: Callable[[Any], None]) -> bool:
        coordinator = self._render_coordinator()
        if coordinator is None:
            apply(intent)
            return True
        return coordinator.request(intent, apply)

    def _refresh_health(self) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            self.__dict__["_health_warnings"] = ()
            return
        state = self.__dict__.setdefault("_health_state", {})
        self.__dict__["_health_warnings"] = health_warnings(snapshot, state)

    def _observe_capability(self, key: str, resource: Any) -> None:
        window_components.observe_capability(self, key, resource)

    def _record_thermal_summary(self, key: str, resource: Any) -> Any:
        return window_components.record_thermal_summary(self, key, resource)

    def _thermal_render_state(self, context: Any) -> Any:
        return window_components.thermal_render_state(self, context)

    def _refresh_thermals_page(self, state: Any = None) -> None:
        window_components.refresh_thermals_page(self, state)

    def _component_poll_delay(self) -> int | None:
        return window_components.component_poll_delay(self)

    def _schedule_component_poll(
        self, *, force: bool = False, delay_override: int | None = None
    ) -> None:
        window_components.schedule_component_poll(
            self, force=force, delay_override=delay_override
        )

    def _run_component_cycle(self) -> None:
        window_components.run_component_cycle(self)

    def _launch_component_scan(self, key: str) -> None:
        window_components.launch_component_scan(self, key)

    def _request_component_refresh(self, key: str) -> None:
        window_components.request_component_refresh(self, key)

    def _rescan_node_after_change(self, node_id: Any) -> None:
        if node_id is None or node_id == self.__dict__.get("_selected_node_id"):
            self._schedule_timer(500, self.handle_analyze)

    def _nodes_peer_specs(self) -> Any:
        return window_page_data.nodes_peer_specs(self)

    def _nodes_trusted_specs(self) -> Any:
        return window_page_data.nodes_trusted_specs(self)

    def _nodes_manual_specs(self) -> Any:
        return window_page_data.nodes_manual_specs(self)

    def _nodes_cluster_spec(self) -> Any:
        return window_page_data.nodes_cluster_spec(self)

    def _cluster_specs(self) -> Any:
        return window_page_data.cluster_specs(self)

    def _settings_categories(self) -> Any:
        return window_page_data.settings_categories(self)

    def _interval_specs(self) -> Any:
        return window_page_data.interval_specs(self)

    def _card_specs(self) -> Any:
        return window_page_data.card_specs(self)

    def _on_select_settings_category(self, key: str) -> None:
        handler = {
            "preferences": self._show_preferences_page,
            "nodes": self._show_nodes_page,
            "cluster": self._show_cluster_page,
            "diagnostics": self._show_diagnostics_page,
            "help": self._show_help_page,
        }.get(key)
        if handler is not None:
            handler()

    def _show_preferences_page(self) -> None:
        raise NotImplementedError

    def _show_nodes_page(self) -> None:
        raise NotImplementedError

    def _show_cluster_page(self) -> None:
        raise NotImplementedError

    def _show_diagnostics_page(self) -> None:
        raise NotImplementedError

    def _show_help_page(self) -> None:
        raise NotImplementedError

    def _switch_selected_node(self, node_id: Any) -> None:
        window_node_runtime.switch_selected_node(self, node_id)

    def _open_cluster_node(self, node_id: str) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.open_cluster_node(self, node_id)

    def _test_connection(self, node_id: str) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.test_connection(self, node_id)

    def _rename_node(self, node_id: str) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.rename_node(self, node_id)

    def _set_node_permissions(self, node_id: str, raw_permissions: Any) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.set_node_permissions(self, node_id, raw_permissions)

    def _set_node_roles(self, node_id: str, roles: Any) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.set_node_roles(self, node_id, roles)

    def _pause_node(self, node_id: str) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.pause_node(self, node_id)

    def _resume_node(self, node_id: str) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.resume_node(self, node_id)

    def _revoke_node(self, node_id: str) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.revoke_node(self, node_id)

    def _remove_connection_node(self, node_id: str) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.remove_connection_node(self, node_id)

    def _remove_job_node(self, node_id: str) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.remove_job_node(self, node_id)

    def _apply_discovery_enabled(self, enabled: bool) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.apply_discovery_enabled(self, enabled)

    def _reject_discovered_node(self, node_id: str) -> None:
        from maintenance.ui import window_node_actions

        window_node_actions.reject_discovered_node(self, node_id)

    def _on_interval_commit(self, key: str, seconds: int) -> None:
        window_preferences.on_interval_commit(self, key, seconds)

    def _on_card_visibility_change(self, key: str, visible: bool) -> None:
        window_preferences.on_card_visibility_change(self, key, visible)

    def _on_auto_hide_change(self, enabled: bool) -> None:
        window_preferences.on_auto_hide_change(self, enabled)

    def _on_full_system_scan_change(self, enabled: bool) -> None:
        window_preferences.on_full_system_scan_change(self, enabled)

    def _on_appearance_change(self, theme: str) -> None:
        window_preferences.on_appearance_change(self, theme)

    def _apply_preferences(self, candidate: Any) -> None:
        window_preferences.apply_preferences(self, candidate)

    def _get_discovery_session(self) -> Any:
        """Return the shared discovery lifecycle without loading a UI shell."""
        return window_discovery.get_discovery_session(self)

    def _start_discovery(self) -> None:
        """Start the canonical discovery session; shells own its presentation."""
        session = self._get_discovery_session()
        session.start()
        self._discovery_tick_id = session.timer_id

    def _tick_discovery(self) -> None:
        session = self._get_discovery_session()
        session.tick()
        self._discovery_tick_id = session.timer_id

    def _stop_discovery(self) -> None:
        session = self.__dict__.get("_discovery_session")
        if session is not None:
            session.stop()
        self._discovery_tick_id = None

    def _save_cluster_state(self, state: Any) -> bool:
        return save_cluster_state(self, state)

    def _sync_peer_listener_grants(self) -> None:
        sync_peer_listener_grants(self)

    def _listener_endpoint(self) -> tuple[bool, int | None, str | None, bool | None]:
        return window_discovery.listener_endpoint(self)

    def _start_peer_listener(self) -> None:
        window_discovery.start_peer_listener(self)

    def _peer_connections(self) -> Any:
        return window_discovery.peer_connections(self)

    def _reconcile_peer_connections(self) -> None:
        window_discovery.reconcile_peer_connections(self)

    def _schedule_peer_reconciliation(self, deadline: float | None) -> None:
        window_discovery.schedule_peer_reconciliation(self, deadline)

    def _share_dashboard(self) -> None:
        """Toggle read-only dashboard sharing for the currently granted peers."""
        service = self.__dict__.get("_peer_service")
        shares = self.__dict__.get("_peer_dashboard_shares", {})
        if any(expiry > time.time() for expiry in shares.values()):
            if service is not None:
                service.stop_dashboard_shares()
            self.__dict__["_peer_dashboard_shares"] = {}
            self._cancel_timer(self.__dict__.get("_dashboard_share_timer_id"))
            self.__dict__["_dashboard_share_timer_id"] = None
            self._dashboard_share_status("Dashboard sharing stopped")
        else:
            if self._start_dashboard_shares(
                grant.caller_node_id for grant in self._cluster_state.peer_grants
            ):
                self._dashboard_share_status("Dashboard shared read-only for 5 minutes")
        self._refresh_dashboard_share_pages()
        self._dashboard_share_callback("_show_dashboard_page")

    def _share_dashboard_with(self, caller_node_id: str) -> None:
        if not self._start_dashboard_shares((caller_node_id,)):
            return
        self._dashboard_share_status("Dashboard shared read-only for 5 minutes")
        self._refresh_dashboard_share_pages()

    def _start_dashboard_shares(self, caller_node_ids: Iterable[str]) -> bool:
        caller_ids = tuple(caller_node_ids)
        if not caller_ids:
            return False
        service = self.__dict__.get("_peer_service")
        if service is None:
            self._start_peer_listener()
            service = self.__dict__.get("_peer_service")
        if service is None:
            return False
        expires_at = time.time() + 300.0
        shares = self.__dict__.get("_peer_dashboard_shares", {})
        previous_expiries = {
            caller_node_id: shares[caller_node_id]
            for caller_node_id in caller_ids
            if shares.get(caller_node_id, 0) > time.time()
        }
        attempted: list[str] = []
        try:
            for caller_node_id in caller_ids:
                attempted.append(caller_node_id)
                service.start_dashboard_share_for(
                    NodeId(caller_node_id), expires_at=expires_at
                )
        except Exception:
            # A batch must not leave peers enabled without controller expiry state.
            # Clear every attempted peer, including the one whose start failed in
            # case the service applied its change before reporting the failure.
            for caller_node_id in attempted:
                try:
                    service.clear_dashboard_share(NodeId(caller_node_id))
                except Exception:
                    LOGGER.exception("Could not roll back a dashboard share")
            failed_restorations: list[str] = []
            for caller_node_id, previous_expiry in previous_expiries.items():
                try:
                    service.start_dashboard_share_for(
                        NodeId(caller_node_id), expires_at=previous_expiry
                    )
                except Exception:
                    failed_restorations.append(caller_node_id)
                    LOGGER.exception("Could not restore a previous dashboard share")
            for caller_node_id in failed_restorations:
                shares.pop(caller_node_id, None)
            if failed_restorations:
                try:
                    self._reschedule_dashboard_share_timer()
                except Exception:
                    LOGGER.exception("Could not reschedule dashboard share expiry")
            raise
        shares = self.__dict__.setdefault("_peer_dashboard_shares", {})
        previous_shares = {
            caller_node_id: shares.get(caller_node_id) for caller_node_id in caller_ids
        }
        for caller_node_id in caller_ids:
            shares[caller_node_id] = expires_at
        try:
            self._reschedule_dashboard_share_timer()
        except Exception:
            # Do not leave service-side shares without an owned expiry timer.
            for caller_node_id in caller_ids:
                try:
                    service.clear_dashboard_share(NodeId(caller_node_id))
                except Exception:
                    LOGGER.exception("Could not roll back a dashboard share")
            for caller_node_id, previous_expiry in previous_shares.items():
                if previous_expiry is None:
                    shares.pop(caller_node_id, None)
                    continue
                try:
                    service.start_dashboard_share_for(
                        NodeId(caller_node_id), expires_at=previous_expiry
                    )
                except Exception:
                    shares.pop(caller_node_id, None)
                    LOGGER.exception("Could not restore a previous dashboard share")
            raise
        return True

    def _stop_sharing_with(self, caller_node_id: str) -> None:
        service = self.__dict__.get("_peer_service")
        if service is not None:
            service.clear_dashboard_share(NodeId(caller_node_id))
        self.__dict__.setdefault("_peer_dashboard_shares", {}).pop(caller_node_id, None)
        self._reschedule_dashboard_share_timer()
        self._dashboard_share_status("Dashboard sharing stopped")
        self._refresh_dashboard_share_pages()

    def _share_dashboard_with_coordinator(self) -> None:
        epoch = self._cluster_state.coordinator_epoch
        if epoch is None:
            return
        coordinator_id = epoch.coordinator_id.value
        shares = self.__dict__.get("_peer_dashboard_shares", {})
        if shares.get(coordinator_id, 0) > time.time():
            self._stop_sharing_with(coordinator_id)
        else:
            self._share_dashboard_with(coordinator_id)

    def _reschedule_dashboard_share_timer(self) -> None:
        old_timer_id = self.__dict__.get("_dashboard_share_timer_id")
        shares = self.__dict__.get("_peer_dashboard_shares", {})
        if not shares:
            self._cancel_timer(old_timer_id)
            self.__dict__["_dashboard_share_timer_id"] = None
            return
        nearest = min(shares.values())
        delay_ms = max(0, int((nearest - time.time()) * 1000))
        replacement_id = self._schedule_timer(delay_ms, self._expire_dashboard_shares)
        self._cancel_timer(old_timer_id)
        self.__dict__["_dashboard_share_timer_id"] = replacement_id

    def _expire_dashboard_shares(self) -> None:
        now = time.time()
        service = self.__dict__.get("_peer_service")
        shares = self.__dict__.get("_peer_dashboard_shares", {})
        for caller_id in [
            caller_id for caller_id, expiry in shares.items() if expiry <= now
        ]:
            shares.pop(caller_id, None)
            if service is not None:
                try:
                    service.clear_dashboard_share(NodeId(caller_id))
                except Exception:
                    LOGGER.exception("Could not clear an expired dashboard share")
        self.__dict__["_dashboard_share_timer_id"] = None
        try:
            self._reschedule_dashboard_share_timer()
        except Exception:
            LOGGER.exception("Could not reschedule dashboard share expiry")
            # No timer owns the remaining live shares. Fail closed rather than
            # leave them active indefinitely, even if service cleanup fails.
            for caller_id in list(shares):
                shares.pop(caller_id, None)
                if service is None:
                    continue
                try:
                    service.clear_dashboard_share(NodeId(caller_id))
                except Exception:
                    LOGGER.exception(
                        "Could not clear dashboard share after expiry scheduling failed"
                    )
            self._refresh_dashboard_share_pages()
            raise
        self._refresh_dashboard_share_pages()

    def _dashboard_share_status(self, message: str) -> None:
        callback = getattr(self, "_nodes_status", None)
        if callable(callback):
            callback(message)

    def _refresh_dashboard_share_pages(self) -> None:
        for name in ("_refresh_cluster_page", "_refresh_nodes_page"):
            self._dashboard_share_callback(name)

    def _dashboard_share_callback(self, name: str) -> None:
        callback = getattr(self, name, None)
        if callable(callback):
            callback()

    def _run_peer_reconciliation(self) -> None:
        window_discovery.run_peer_reconciliation(self)

    def _on_discovered_candidate(self, candidate: Any) -> None:
        window_discovery.on_discovered_candidate(self, candidate)

    def _on_discovered_lost(self, stable_id: str) -> None:
        window_discovery.on_discovered_lost(self, stable_id)

    def _queue_discovery_presentation(self, trusted_involved: bool) -> None:
        del trusted_involved

    def _close(self) -> None:
        """Close shared services; concrete shells own presentation teardown."""
        self._is_closing = True
        self._finalize_shutdown()
        if self._analysis_cancel_event is not None:
            self._analysis_cancel_event.set()
            self._analysis_cancel_event = None
        self._stop_all_node_workers()

    def _finalize_shutdown(self) -> None:
        """Stop domain/background activity before a shell releases its widgets."""
        peer_server = self.__dict__.get("_peer_server")
        self._peer_server = None
        self._peer_service = None
        if peer_server is not None:
            peer_server.stop()
        self._stop_discovery()
        peer_manager = self.__dict__.get("_peer_connection_manager")
        if peer_manager is not None:
            peer_manager.shutdown()
        self._cancel_timer(self.__dict__.get("_peer_reconcile_timer_id"))
        self._peer_reconcile_timer_id = None
        self._dashboard_scan_lifecycle().cancel()
        self._sync_dashboard_scan_state()
        coordinator = self.__dict__.get("_coordinator")
        if coordinator is not None:
            coordinator.cancel_all()
            coordinator.shutdown()
        self._cancel_all_node_operations()
        cluster_page = getattr(self, "cluster_page", None)
        dispose = getattr(cluster_page, "dispose", None)
        if callable(dispose):
            dispose()
        self._cancel_pending_timers()
        self._component_poll_id = None
        self._background_poll_id = None
        self._scan_timeout_id = None
        render = self._render_coordinator()
        if render is not None:
            render.shutdown()

    def _make_background_orchestrator(self) -> BackgroundOrchestrator:
        return BackgroundOrchestrator(
            queue=self._background_queue,
            is_closing=lambda: self._is_closing,
            schedule_timer=lambda delay, callback: self._schedule_timer(
                delay, callback
            ),
            get_poll_id=lambda: self._background_poll_id,
            set_poll_id=lambda identifier: setattr(
                self, "_background_poll_id", identifier
            ),
            get_task_count=lambda: self._background_tasks,
            set_task_count=lambda count: setattr(self, "_background_tasks", count),
            set_busy=self._set_busy,
            resolve_completed_worker=self._resolve_completed_worker,
            get_render_coordinator=self._render_coordinator,
            has_pending_coordinator_work=lambda: (
                self._coordinator is not None and self._coordinator.has_pending_work
            ),
            has_discovery_tick=lambda: self._discovery_tick_id is not None,
            invoke_delivered=self._invoke_delivered,
            poll_milliseconds=self.BACKGROUND_POLL_MILLISECONDS,
            logger=LOGGER,
        )

    def _background_service(self) -> BackgroundOrchestrator:
        service = self.__dict__.get("_background_orchestrator")
        if service is None:
            service = self._make_background_orchestrator()
            self._background_orchestrator = service
        return service

    def _render_coordinator(self) -> Any:
        return getattr(self, "_ui_coordinator", None)

    def _sync_render_visibility(self, active_page: str | None) -> None:
        """Update shared render gates without depending on a shell's page IDs."""
        discovery_visible = active_page in {"nodes", "cluster"}
        self.__dict__["_discovery_pages_visible"] = discovery_visible
        coordinator = self.__dict__.get("_coordinator")
        if discovery_visible and coordinator is not None:
            coordinator.flush_deferred("discovery-pages")
        render = self._render_coordinator()
        if render is None:
            return
        dashboard_visible = active_page == "dashboard"
        render.set_visible("selected-node", dashboard_visible)
        render.set_visible("dashboard-snapshot", dashboard_visible)
        render.set_visible("scan-status", active_page in {"dashboard", "preferences"})
        render.set_visible("dashboard-discovery", dashboard_visible)
        render.set_visible("thermals", active_page == "thermals")
        render.set_visible("discovery-pages", discovery_visible)
        render.set_visible("nodes-page", active_page == "nodes")
        render.set_visible("cluster-page", active_page == "cluster")
        render.set_visible("nodes-status", active_page == "nodes")
        for feature in self._feature_catalog.all():
            render.set_visible(f"component:{feature.key}", dashboard_visible)
            if dashboard_visible and coordinator is not None:
                coordinator.flush_deferred(
                    self._operation_key(f"component:{feature.key}")
                )

    def _is_card_visible(self, key: str) -> bool:
        return is_card_visible(
            key,
            preferences=self.__dict__.get("_preferences"),
            capabilities=self.__dict__.get("_capabilities", {}),
        )

    def _set_diagnostics_visibility(self, visible: bool) -> None:
        if not visible:
            refresh_id = self.__dict__.get("_diagnostics_refresh_id")
            if refresh_id is not None:
                self._cancel_timer(refresh_id)
                self._diagnostics_refresh_id = None
            return
        refresh = getattr(self, "_refresh_diagnostics_page", None)
        if refresh is not None:
            refresh()

    def _schedule_timer(
        self, delay: int, callback: Callable[..., None], *args: object
    ) -> str | None:
        return self._timer_delivery_for_window().schedule(delay, callback, *args)

    def _cancel_timer(self, identifier: str | None) -> bool:
        return self._timer_delivery_for_window().cancel(identifier)

    def _cancel_pending_timers(self) -> None:
        self._timer_delivery_for_window().cancel_all()

    def _submit_latest_progress(self, key: str, callback: Callable[[], None]) -> None:
        self._background_service().submit_progress(key, callback)

    def _start_background_poll(self) -> None:
        self._background_service().start_poll()

    def _run_daemon(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        self._background_service().run_daemon(task, on_success, on_error, on_finished)

    def _run_in_background(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> bool:
        return self._background_service().run_in_background(
            task,
            on_success or self._show_snapshot,
            on_error or self._show_error,
            daemon_runner=self._run_daemon,
        )

    @staticmethod
    def _invoke_delivered(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            LOGGER.exception("Dropped UI delivery callback")

    def _set_busy(self, is_busy: bool) -> None:
        raise NotImplementedError

    def _show_snapshot(self, snapshot: Any, *, node_snapshot: Any = None) -> None:
        raise NotImplementedError

    def _show_error(self, message: str) -> None:
        raise NotImplementedError

    def _timer_delivery_for_window(self) -> Any:
        raise NotImplementedError

    def _stop_all_node_workers(self) -> None:
        analyzer = getattr(self, "analyzer", None)
        stop_workers = getattr(analyzer, "stop_background_workers", None)
        if stop_workers is not None:
            stop_workers()
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        for context in registry.contexts():
            if context.provider is analyzer:
                continue
            stop = getattr(context.provider, "stop_background_workers", None)
            if stop is not None:
                stop()

    def _selected_context(self) -> NodeContext | None:
        return window_node_runtime.selected_context(self)

    def _operation_key(self, operation: str) -> str:
        return window_node_runtime.operation_key(self, operation)

    def _node_selection(self) -> Any:
        return window_node_runtime.node_selection(self)

    def _multi_node_selectable(self) -> bool:
        return window_node_runtime.multi_node_selectable(self)

    def _cancel_node_operations(self, context: NodeContext | None) -> None:
        window_node_runtime.cancel_node_operations(self, context)

    def _cancel_all_node_operations(self) -> None:
        window_node_runtime.cancel_all_node_operations(self)
