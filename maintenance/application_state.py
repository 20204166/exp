"""Toolkit-neutral initialization of application services and state."""

from __future__ import annotations

from typing import Any


def initialize_application_state(owner: Any, *, dependencies: Any) -> None:
    """Initialize non-UI state using collaborators supplied by the host."""
    owner.analyzer = dependencies.analyzer_factory()
    owner.process_manager = dependencies.process_manager_factory()
    owner.file_manager = dependencies.file_manager_factory(
        owner.analyzer.scanner.downloads_path
    )
    owner._preferences_store = dependencies.preferences_store_factory()
    owner._preferences = owner._preferences_store.load()
    owner._cluster_store = dependencies.cluster_store_factory()
    owner._cluster_state = owner._cluster_store.load()
    local_roles = owner._cluster_state.local_assignment.roles
    owner._cluster_timeline = (
        dependencies.timeline_factory(
            owner._cluster_store.path.with_name("cluster-history.sqlite3")
        )
        if any(role.value == "coordinator" for role in local_roles)
        else None
    )
    owner._standby_buffer = (
        dependencies.standby_factory(
            owner._cluster_store.path.with_name("cluster-standby.sqlite3")
        )
        if any(role.value == "subcoordinator" for role in local_roles)
        else None
    )
    owner._provision_target_grant = dependencies.provision_target_grant
    owner._developer_mode = dependencies.developer_mode
    owner.snapshot = None
    owner._is_closing = False
    owner._pending_after_ids = set()
    owner._background_poll_id = None
    owner._background_tasks = 0
    owner._observer = dependencies.observer_factory()
    owner._scan_coordinator = dependencies.scan_coordinator_factory(
        observer=owner._observer
    )
    owner._analysis_cancel_event = None
    owner._scan_timeout_id = None
    owner._lease_grace_id = None
    owner._timed_out_generation = None
    owner._resolved_scan_generation = 0
    owner._background_queue = dependencies.queue_factory()
    owner._coordinator = dependencies.coordinator_factory(
        deliver=owner._submit_ui,
        deliver_progress=owner._submit_latest_progress,
        on_activity=owner._start_background_poll,
        observer=owner._observer,
    )
    owner._component_scheduler = dependencies.scheduler_factory(
        owner._preferences.refresh_intervals.as_dict(), observer=owner._observer
    )
    owner._button_coordinator = dependencies.button_factory(observer=owner._observer)
    owner._ui_coordinator = dependencies.ui_coordinator_factory(
        schedule=lambda delay, callback: owner._schedule_timer(delay, callback),
        cancel=lambda identifier: owner._cancel_timer(identifier),
        observer=owner._observer,
    )
    owner._background_orchestrator = owner._make_background_orchestrator()
    owner._feature_catalog = dependencies.catalog_factory()
    owner._component_poll_id = None
    owner._diagnostics_refresh_id = None
    owner._capabilities = {}
    owner._node_registry = dependencies.registry_factory()
    owner._selected_node_id = None
    owner._discovery_tick_id = None
    owner._peer_reconcile_timer_id = None
    owner._build_local_node_context()
    owner._restore_trusted_nodes()
    owner._peer_server = None
    owner._connection_dialog = None
    owner._pairing_dialog = None
    owner._node_details_dialog = None
    owner._sharing_dialog = None
