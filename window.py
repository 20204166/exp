import logging
import threading
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from queue import Queue
from tkinter import messagebox, simpledialog, ttk
from typing import Any, cast

import algo
from maintenance import __version__
from maintenance.actions import FileManager, ProcessManager
from maintenance.cluster import (
    ClusterSaveError,
    ClusterState,
    ClusterStore,
    PeerGrantRecord,
    default_cluster_path,
)
from maintenance.components import (
    DOWNLOADS_SCAN_CANCELLED,
    DashboardScanLifecycle,
    NodeSelection,
    PeerConnectionManager,
    ResourceFeatureCatalog,
    ScanCoordinator,
    node_context,
)
from maintenance.components.background_orchestration import (
    BackgroundItem,
    BackgroundOrchestrator,
    run_daemon,
)
from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
)
from maintenance.components.discovery_session import DiscoverySession
from maintenance.components.network_discovery import (
    NetworkDiscovery,
)
from maintenance.components.scan_support import (
    SCAN_CANCELLED_NOTICE,
    call_legacy_compatible,
)
from maintenance.components.temperature import (
    TemperatureRenderState,
    TemperatureTelemetryUpdate,
)
from maintenance.dialogs import (
    InfoDialog,
    ProcessDialog,
    ResourceCard,
    StorageDialog,
    run_in_thread,
)
from maintenance.health import health_warnings
from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    ResourceSummary,
    unavailable_summary,
)
from maintenance.nodes import (
    ConnectionState,
    LocalNodeProvider,
    NodeCapability,
    NodeConnectionStatus,
    NodeContext,
    NodeId,
    NodeIdentityStatus,
    NodePermission,
    NodeRegistry,
    NodeSnapshot,
    generate_node_secret,
    is_trusted_descriptor,
    local_node_descriptor,
    node_identity_fingerprint,
    node_operation_key,
)
from maintenance.preferences import (
    INTERVAL_POLICIES,
    AppPreferences,
    PreferencesSaveError,
    PreferencesStore,
    default_preferences_path,
)
from maintenance.remote import (
    AuthenticatedNodeProvider,
    PeerGrant,
    RemoteProcessActionBackend,
    RemoteService,
    RemoteSocketServer,
    SocketRemoteTransport,
)
from maintenance.ui import cluster_page as ui_cluster
from maintenance.ui import dashboard_page as ui_dashboard
from maintenance.ui import discovery_refresh as ui_discovery_refresh
from maintenance.ui import nodes_connections as ui_nodes
from maintenance.ui import preferences_page as ui_preferences
from maintenance.ui import render_coordinator as ui_render
from maintenance.ui import scan_status
from maintenance.ui import settings_home as ui_settings_home
from maintenance.ui import styles as ui_styles
from maintenance.ui import transition as ui_transition
from maintenance.ui import window_node_actions as ui_node_actions
from maintenance.ui import window_pages as ui_window_pages
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.navigation import PageRouter, PageSpec
from maintenance.ui.target_state import render_target_state
from maintenance.ui.window_supports import card_policy, node_specs, snapshot_state
from maintenance.ui.window_supports.timer_delivery import TimerDelivery

LOGGER = logging.getLogger(__name__)

DASHBOARD_PAGE = "dashboard"
SETTINGS_PAGE = "settings"
PREFERENCES_PAGE = "preferences"
NODES_PAGE = "nodes"
CLUSTER_PAGE = "cluster"
THERMALS_PAGE = "thermals"


class AppWindow:
    # Dashboard widgets are built by the dashboard adapter after construction.
    tk: Any
    cards: dict[str, ResourceCard]
    cards_frame: Any
    _refresh_cards_scrollbar: Callable[..., None]
    refreshed_label: Any
    scan_time_label: Any
    health_label: Any
    status_label: Any
    analyze_button: Any
    cancel_button: Any
    preferences_page: Any
    settings_home: Any
    thermals_page: Any
    BACKGROUND = ui_styles.COLORS["background"]
    CARD_BACKGROUND = ui_styles.COLORS["card"]
    TEXT_PRIMARY = ui_styles.COLORS["text"]
    TEXT_SECONDARY = ui_styles.COLORS["secondary"]
    ACCENT = ui_styles.COLORS["accent"]
    ACCENT_ACTIVE = ui_styles.COLORS["accent_active"]
    BORDER = ui_styles.COLORS["border"]
    COMPONENT_POLL_MILLISECONDS = 1000
    COMPLETION_HOLD_MILLISECONDS = 500
    SCAN_TIMEOUT_MILLISECONDS = 30000
    SCAN_LEASE_GRACE_MILLISECONDS = 10000
    UNSUPPORTED_CONFIRM_LIMIT = 2
    SCAN_TIMEOUT_MESSAGE = (
        "The system scan did not finish within 30 seconds and was stopped. "
        "A hardware query may be slow or unresponsive; try scanning again."
    )
    FAILED_CARD_KEEP_LIMIT = 3
    UI_FONT = ui_styles.FONTS["ui"][0]
    TITLE_FONT = ui_styles.FONTS["title"]
    SECTION_FONT = ui_styles.FONTS["section"]
    BODY_FONT = ui_styles.FONTS["body"]
    BUTTON_FONT = ui_styles.FONTS["button"]
    DANGER_BUTTON_FONT = ui_styles.FONTS["danger_button"]
    STATUS_FONT = ui_styles.FONTS["status"]
    BACKGROUND_POLL_MILLISECONDS = 10

    def __init__(
        self,
        master: Any = None,
        *,
        preferences_store: PreferencesStore | None = None,
        cluster_store: ClusterStore | None = None,
        provision_target_grant: Callable[[PeerGrantRecord], bool] | None = None,
    ) -> None:
        self.analyzer = algo.Analyzer()
        self.process_manager = ProcessManager()
        self.file_manager = FileManager(self.analyzer.scanner.downloads_path)
        self._preferences_store = preferences_store or PreferencesStore(
            default_preferences_path()
        )
        self._preferences = self._preferences_store.load()
        self._cluster_store = cluster_store or ClusterStore(default_cluster_path())
        self._cluster_state = self._cluster_store.load()
        self._provision_target_grant = provision_target_grant
        self.snapshot: DashboardSnapshot | None = None
        self._is_closing = False
        self._pending_after_ids: set[str] = set()
        self._background_poll_id: str | None = None
        self._background_tasks = 0
        self._scan_coordinator = ScanCoordinator()
        self._analysis_cancel_event: threading.Event | None = None
        self._scan_timeout_id: str | None = None
        self._lease_grace_id: str | None = None
        self._timed_out_generation: int | None = None
        self._resolved_scan_generation = 0
        self._background_queue: Queue[BackgroundItem] = Queue()
        self._coordinator = AppCoordinator(
            deliver=self._submit_ui,
            on_activity=self._start_background_poll,
        )
        self._component_scheduler = ComponentRefreshScheduler(
            self._preferences.refresh_intervals.as_dict()
        )
        self._button_coordinator = ButtonCoordinator()
        self._ui_coordinator = ui_render.UICoordinator()
        self._background_orchestrator = self._make_background_orchestrator()
        self._feature_catalog = ResourceFeatureCatalog()
        self._component_poll_id: str | None = None
        self._capabilities: dict[str, CapabilityState] = {}
        self._node_registry = NodeRegistry()
        self._selected_node_id: NodeId | None = None
        self._discovery_tick_id: str | None = None
        self._peer_reconcile_timer_id: str | None = None
        self._build_local_node_context()
        self._restore_trusted_nodes()
        self._peer_server: RemoteSocketServer | None = None

        self.master = master or tk.Tk()
        self._timer_delivery = TimerDelivery(
            master=self.master,
            is_closing=lambda: self._is_closing,
            pending_ids=self._pending_after_ids,
            logger=LOGGER,
        )
        self.master.title("System Analyzer")
        self.master.geometry("1040x760")
        self.master.minsize(900, 680)
        self.master.configure(bg=self.BACKGROUND)
        self.master.protocol("WM_DELETE_WINDOW", self._close)

        self._configure_styles()
        self._build_window()
        self._start_peer_listener()
        self._start_discovery()
        self._schedule_timer(350, self.handle_analyze)

    def _build_local_node_context(self) -> None:
        """Register the local machine as the first node and select it.

        The local node is the one real target today. The window's historical
        attributes (``analyzer``, ``snapshot``, ``_capabilities``,
        ``_component_scheduler``) are kept as mirrors of the selected context
        so existing callers and test seams keep working; switching nodes
        re-syncs the mirrors from the newly selected context.
        """

        context = node_context.build_local_node_context(
            cluster_state=self._cluster_state,
            analyzer=self.analyzer,
            process_manager=self.process_manager,
            file_manager=self.file_manager,
            scheduler=self._component_scheduler,
            coordinator=self._coordinator,
            snapshot=self.snapshot,
            capabilities=self._capabilities,
        )
        self.__dict__["_capability_counts"] = context.capability_counts
        self.__dict__["_failed_card_counts"] = context.failed_card_counts
        self._node_registry.register_context(context)
        self._selected_node_id = self._node_registry.select(context.node_id)

    def _restore_trusted_nodes(self) -> None:
        """Restore persisted trusted nodes into the registry at startup.

        Each record becomes a trusted placeholder (no provider/scheduler), so
        it is never selectable until pairing attaches an operational read
        provider. Display overrides and colours from the store are applied.
        """

        registry = self.__dict__.get("_node_registry")
        state = self.__dict__.get("_cluster_state")
        if registry is None or state is None:
            return
        node_context.restore_trusted_nodes(
            registry=registry,
            cluster_state=state,
            logger=LOGGER,
        )

    @property
    def colors(self) -> dict[str, str]:
        preferences = self.__dict__.get("_preferences")
        appearance = (
            preferences.appearance
            if preferences is not None
            and isinstance(getattr(preferences, "appearance", None), str)
            else ui_styles.DEFAULT_APPEARANCE
        )
        return ui_styles.accent_theme_colors(appearance)

    def _scan_coordinator_state(self) -> ScanCoordinator:
        coordinator = self.__dict__.get("_scan_coordinator")
        if coordinator is None:
            coordinator = ScanCoordinator()
            self.__dict__["_scan_coordinator"] = coordinator
        return coordinator

    def _dashboard_scan_lifecycle(self) -> DashboardScanLifecycle:
        lifecycle = self.__dict__.get("_dashboard_scan_lifecycle_obj")
        if lifecycle is None:
            lifecycle = DashboardScanLifecycle(
                coordinator=self._scan_coordinator_state(),
                is_closing=lambda: self._is_closing,
                schedule_timer=self._schedule_timer,
                cancel_timer=self._cancel_timer,
                show_timeout_error=self._show_error,
                schedule_rerun=lambda: self._schedule_rerun_if_requested(True),
                timeout_callback=self._handle_scan_timeout,
                grace_callback=self._release_lease_after_grace,
                timeout_milliseconds=self.SCAN_TIMEOUT_MILLISECONDS,
                grace_milliseconds=self.SCAN_LEASE_GRACE_MILLISECONDS,
                timeout_message=self.SCAN_TIMEOUT_MESSAGE,
            )
            lifecycle.cancel_event = self.__dict__.get("_analysis_cancel_event")
            lifecycle.timeout_id = self.__dict__.get("_scan_timeout_id")
            lifecycle.lease_grace_id = self.__dict__.get("_lease_grace_id")
            lifecycle.timed_out_generation = self.__dict__.get("_timed_out_generation")
            lifecycle.resolved_generation = self.__dict__.get(
                "_resolved_scan_generation", 0
            )
            self.__dict__["_dashboard_scan_lifecycle_obj"] = lifecycle
        return lifecycle

    def _sync_dashboard_scan_state(self) -> None:
        lifecycle = self._dashboard_scan_lifecycle()
        self.__dict__.update(
            _analysis_cancel_event=lifecycle.cancel_event,
            _scan_timeout_id=lifecycle.timeout_id,
            _lease_grace_id=lifecycle.lease_grace_id,
            _timed_out_generation=lifecycle.timed_out_generation,
            _resolved_scan_generation=lifecycle.resolved_generation,
        )

    def _selected_context(self) -> NodeContext | None:
        """Return the selected node's runtime context, or None outside the app.

        Tests construct ``AppWindow`` with ``object.__new__`` and no registry,
        so callers must treat ``None`` as the legacy single-node behaviour.
        """

        selection = self._node_selection()
        if selection is None:
            return None
        return selection.selected_context()

    def _operation_key(self, operation: str) -> str:
        """Return a node-qualified coordinator key for the selected node.

        Outside the registry (tests) the legacy unqualified key is returned so
        existing coordinator-key assertions keep passing; inside the app every
        shared operation key is namespaced so two nodes can never coalesce or
        overwrite each other's work.
        """

        selection = self._node_selection()
        if selection is None:
            return operation
        return selection.operation_key(operation)

    def _multi_node_selectable(self) -> bool:
        selection = self._node_selection()
        return selection is not None and selection.multi_node_selectable()

    def _node_selection(self) -> NodeSelection | None:
        selection = self.__dict__.get("_node_selection_component")
        if selection is not None:
            return cast(NodeSelection, selection)
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return None
        selection = NodeSelection(
            registry=registry,
            selected_id=lambda: self.__dict__.get("_selected_node_id"),
            set_selected_id=lambda node_id: self.__dict__.__setitem__(
                "_selected_node_id", node_id
            ),
            cancel_active_scan=lambda: self._cancel_active_scan(),
            invalidate_render_targets=lambda node_id: (
                self._invalidate_node_render_targets(node_id)
            ),
            cancel_node_operations=lambda context: self._cancel_node_operations(
                context
            ),
            sync_selected_context=lambda context: self._sync_selected_context_mirrors(
                context
            ),
            render_selected_node=lambda context: self._render_selected_node(context),
            refresh_thermals=lambda context: self._refresh_selected_node_thermals(
                context
            ),
            schedule_scan=self._schedule_selected_node_scan,
            logger=LOGGER,
            cancel_peer_connection=self._cancel_peer_connection,
        )
        self.__dict__["_node_selection_component"] = selection
        return selection

    def _schedule_selected_node_scan(self) -> None:
        self._schedule_timer(0, self.handle_analyze)

    def _build_window(self) -> None:
        self._page_router = PageRouter(self.master)
        self._page_router.register(PageSpec(DASHBOARD_PAGE, self._build_dashboard_page))
        self._page_router.register(
            PageSpec(SETTINGS_PAGE, self._build_settings_home_page)
        )
        self._page_router.register(
            PageSpec(PREFERENCES_PAGE, self._build_preferences_page)
        )
        self._page_router.register(PageSpec(NODES_PAGE, self._build_nodes_page))
        self._page_router.register(PageSpec(CLUSTER_PAGE, self._build_cluster_page))
        self._page_router.register(PageSpec(THERMALS_PAGE, self._build_thermals_page))
        self._page_router.show(DASHBOARD_PAGE)
        self._sync_render_visibility(DASHBOARD_PAGE)
        self._reconcile_cards_and_polling()

    def _render_coordinator(self) -> ui_render.UICoordinator | None:
        return getattr(self, "_ui_coordinator", None)

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
            set_busy=lambda busy: self._set_busy(busy),
            resolve_completed_worker=lambda: self._resolve_completed_worker(),
            get_render_coordinator=self._render_coordinator,
            has_pending_coordinator_work=lambda: (
                (coordinator := self.__dict__.get("_coordinator")) is not None
                and coordinator.has_pending_work
            ),
            has_discovery_tick=lambda: (
                self.__dict__.get("_discovery_tick_id") is not None
            ),
            invoke_delivered=lambda callback: self._invoke_delivered(callback),
            poll_milliseconds=self.BACKGROUND_POLL_MILLISECONDS,
            logger=LOGGER,
        )

    def _background_service(self) -> BackgroundOrchestrator:
        service = self.__dict__.get("_background_orchestrator")
        if service is None:
            service = self._make_background_orchestrator()
            self.__dict__["_background_orchestrator"] = service
        return service

    def _request_render(
        self,
        intent: ui_render.RenderIntent,
        apply: Callable[[ui_render.RenderIntent], None],
    ) -> bool:
        coordinator = self._render_coordinator()
        if coordinator is None:
            apply(intent)
            return True
        return coordinator.request(intent, apply)

    def _sync_render_visibility(self, active_page: str | None) -> None:
        discovery_pages_visible = active_page in {NODES_PAGE, CLUSTER_PAGE}
        self.__dict__["_discovery_pages_visible"] = discovery_pages_visible
        app_coordinator = self.__dict__.get("_coordinator")
        if discovery_pages_visible and app_coordinator is not None:
            app_coordinator.flush_deferred("discovery-pages")
        render_coordinator = self._render_coordinator()
        if render_coordinator is None:
            return
        dashboard_visible = active_page == DASHBOARD_PAGE
        render_coordinator.set_visible("dashboard-snapshot", dashboard_visible)
        render_coordinator.set_visible(
            "scan-status",
            active_page in {DASHBOARD_PAGE, PREFERENCES_PAGE},
        )
        render_coordinator.set_visible(
            "dashboard-discovery", active_page == DASHBOARD_PAGE
        )
        render_coordinator.set_visible(THERMALS_PAGE, active_page == THERMALS_PAGE)
        render_coordinator.set_visible(
            "discovery-pages",
            discovery_pages_visible,
        )
        render_coordinator.set_visible("nodes-status", active_page == NODES_PAGE)
        for feature in self._feature_catalog.all():
            render_coordinator.set_visible(
                f"component:{feature.key}", dashboard_visible
            )
            if dashboard_visible and app_coordinator is not None:
                app_coordinator.flush_deferred(
                    self._operation_key(f"component:{feature.key}")
                )

    def _build_dashboard_page(self, parent: Any) -> Any:
        self.ttk = ttk
        self.tk = tk
        return ui_dashboard.build(self, parent)

    def _build_settings_home_page(self, parent: Any) -> Any:
        self.ttk = ttk
        return ui_window_pages.build_settings_home(self, parent)

    def _settings_categories(self) -> list[ui_settings_home.SettingsCategorySpec]:
        return [
            ui_settings_home.SettingsCategorySpec(
                key="preferences",
                title="Preferences",
                description=(
                    "Refresh intervals, visible dashboard cards, scan "
                    "behaviour, and interface options."
                ),
            ),
            ui_settings_home.SettingsCategorySpec(
                key="nodes",
                title="Nodes & Connections",
                description=(
                    "Discover peers, pair trusted nodes, manage manual hosts, "
                    "and control local-network discovery."
                ),
            ),
            ui_settings_home.SettingsCategorySpec(
                key="cluster",
                title="All Systems",
                description=(
                    "Overview of every known machine and its connection, "
                    "trust, and capability state."
                ),
            ),
        ]

    def _build_preferences_page(self, parent: Any) -> Any:
        self.ttk = ttk
        return ui_window_pages.build_preferences(self, parent)

    def _interval_specs(self) -> list[ui_preferences.IntervalControlSpec]:
        intervals = self._preferences.refresh_intervals.as_dict()
        specs: list[ui_preferences.IntervalControlSpec] = []
        for feature in self._feature_catalog.all():
            policy = INTERVAL_POLICIES[feature.key]
            specs.append(
                ui_preferences.IntervalControlSpec(
                    key=feature.key,
                    title=feature.title,
                    seconds=intervals[feature.key] // 1000,
                    minimum_seconds=policy.minimum_ms // 1000,
                    maximum_seconds=policy.maximum_ms // 1000,
                    step_seconds=policy.step_ms // 1000,
                )
            )
        return specs

    def _card_specs(self) -> list[ui_preferences.CardControlSpec]:
        return [
            ui_preferences.CardControlSpec(
                key=feature.key,
                title=feature.title,
                enabled=feature.key in self._preferences.visible_cards,
            )
            for feature in self._feature_catalog.all()
        ]

    def _show_settings_page(self) -> None:
        ui_window_pages.show_page(self, SETTINGS_PAGE, "settings_home")

    def _show_preferences_page(self) -> None:
        ui_window_pages.show_page(self, PREFERENCES_PAGE, "preferences_page")

    def _show_dashboard_page(self) -> None:
        ui_window_pages.show_dashboard(self)

    def _show_thermals_page(self) -> None:
        ui_window_pages.show_thermals(self)

    def _build_thermals_page(self, parent: Any) -> Any:
        self.ttk = ttk
        return ui_window_pages.build_thermals(self, parent)

    def _on_select_settings_category(self, key: str) -> None:
        """Route one Settings category card to its dedicated page.

        Unknown keys are ignored defensively so adding a category later is a
        matter of registering its page and a handler here.
        """

        ui_window_pages.select_settings_category(self, key)

    def _show_nodes_page(self) -> None:
        self._refresh_nodes_page()
        ui_window_pages.show_page(self, NODES_PAGE, "nodes_page")

    def _build_nodes_page(self, parent: Any) -> Any:
        self.ttk = ttk
        return ui_window_pages.build_nodes(self, parent)

    def _start_discovery_from_nodes(self) -> None:
        """Enable and start local discovery from Nodes & Connections."""

        if not self._cluster_state.discovery_enabled:
            self._apply_discovery_enabled(True)
            return
        self._start_discovery()

    def _nodes_peer_specs(self) -> list[ui_nodes.DiscoveredPeerSpec]:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return []
        return node_specs.discovered_peer_specs(registry)

    def _nodes_trusted_specs(self) -> list[ui_nodes.TrustedNodeSpec]:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return []
        return node_specs.trusted_node_specs(
            registry, self._cluster_state, getattr(self, "_manual_host_ids", set())
        )

    def _nodes_manual_specs(self) -> list[ui_nodes.TrustedNodeSpec]:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return []
        return node_specs.manual_node_specs(
            registry, self._cluster_state, getattr(self, "_manual_host_ids", set())
        )

    def _refresh_nodes_page(self) -> None:
        ui_window_pages.refresh_nodes(self)

    def _nodes_status(self, message: str) -> None:
        ui_window_pages.set_nodes_status(self, message, error=False)

    def _nodes_error(self, message: str) -> None:
        ui_window_pages.set_nodes_status(self, message, error=True)

    def _show_cluster_page(self) -> None:
        self._refresh_cluster_page()
        ui_window_pages.show_page(self, CLUSTER_PAGE, "cluster_page")

    def _build_cluster_page(self, parent: Any) -> Any:
        self.ttk = ttk
        return ui_window_pages.build_cluster(self, parent)

    def _cluster_specs(self) -> list[ui_cluster.ClusterNodeSpec]:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return []
        return node_specs.cluster_node_specs(registry)

    def _refresh_cluster_page(self) -> None:
        ui_window_pages.refresh_cluster(self)

    def _save_cluster_state(self, state: ClusterState) -> bool:
        try:
            self._cluster_store.save(state)
        except ClusterSaveError as error:
            LOGGER.warning("Failed to save cluster settings: %s", error)
            return False
        self._cluster_state = state
        self._sync_peer_listener_grants()
        return True

    def _sync_peer_listener_grants(self) -> None:
        server = self.__dict__.get("_peer_server")
        if server is None:
            if self._cluster_state.peer_grants:
                self._start_peer_listener()
            return
        grants = {
            NodeId(grant.caller_node_id): PeerGrant(
                caller_node_id=NodeId(grant.caller_node_id),
                secret=grant.secret,
                permissions=grant.permissions,
            )
            for grant in self._cluster_state.peer_grants
        }
        if not grants:
            server.stop()
            self._peer_server = None
            return
        server.update_grants(grants)

    def _apply_discovery_enabled(self, enabled: bool) -> None:
        ui_node_actions.apply_discovery_enabled(self, enabled)

    def _pair_discovered_node(self, node_id: str) -> None:
        self.__dict__.setdefault("_activation_generations", {})[NodeId(node_id)] = (
            self.__dict__.setdefault("_activation_generations", {}).get(
                NodeId(node_id), 0
            )
            + 1
        )
        ui_node_actions.pair_discovered_node(
            self,
            node_id,
            messagebox_module=messagebox,
            provision_target_grant=getattr(self, "_provision_target_grant", None),
        )

    def _reject_discovered_node(self, node_id: str) -> None:
        ui_node_actions.reject_discovered_node(self, node_id)

    def _rename_node(self, node_id: str) -> None:
        ui_node_actions.rename_node(self, node_id, simpledialog_module=simpledialog)

    def _set_node_permissions(
        self, node_id: str, raw_permissions: frozenset[str]
    ) -> None:
        ui_node_actions.set_node_permissions(self, node_id, raw_permissions)

    def _set_node_color(self, node_id: str, color: str) -> None:
        ui_node_actions.set_node_color(self, node_id, color)

    def _revoke_trusted_node(self, node_id: str) -> None:
        self.__dict__.setdefault("_activation_generations", {})[NodeId(node_id)] = (
            self.__dict__.setdefault("_activation_generations", {}).get(
                NodeId(node_id), 0
            )
            + 1
        )
        ui_node_actions.revoke_trusted_node(self, node_id)

    def _add_manual_host(
        self,
        display_name: str,
        host: str,
        port: int | None,
    ) -> None:
        ui_node_actions.add_manual_host(self, display_name, host, port)

    def _remove_manual_host(self, node_id: str) -> None:
        ui_node_actions.remove_manual_host(self, node_id)

    def _test_connection(self, node_id: str) -> None:
        ui_node_actions.test_connection(
            self,
            node_id,
            messagebox_module=messagebox,
            provider_cls=AuthenticatedNodeProvider,
            transport_cls=SocketRemoteTransport,
            run_in_thread_fn=run_in_thread,
        )

    def _open_cluster_node(self, node_id: str) -> None:
        ui_node_actions.open_cluster_node(self, node_id)

    def _activate_remote_node(self, node_id: NodeId) -> None:
        ui_node_actions.activate_remote_node(
            self,
            node_id,
            provider_cls=AuthenticatedNodeProvider,
            transport_cls=SocketRemoteTransport,
            backend_cls=RemoteProcessActionBackend,
            scheduler_cls=ComponentRefreshScheduler,
        )

    def _rebuild_node_selector(self) -> None:
        frame = getattr(self, "_node_selector_frame", None)
        if frame is not None:
            try:
                frame.destroy()
            except Exception:  # noqa: BLE001 - a dead widget must not fail the page.
                return
        actions = getattr(self, "header_actions", None)
        if actions is not None:
            self._build_node_selector(actions)

    def _build_node_selector(self, actions: Any) -> None:
        """Add a compact readonly node selector to the header, when needed.

        With only the local node (or none registered) no selector is built, so
        the one-node experience stays exactly as it is today. With multiple
        selectable (local/trusted) nodes a labelled combobox appears above the
        Settings button; discovered/untrusted candidates are never offered.
        """

        self._node_selector = None
        self._node_selector_var: tk.StringVar | None = None
        registry = self.__dict__.get("_node_registry")
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
                else (
                    f"{descriptor.display_name} "
                    f"({descriptor.hostname} · {descriptor.id.value})"
                )
            )
            for descriptor in selectable
        }
        self._node_selector_values = {
            label: node_id for node_id, label in labels.items()
        }
        selected_id = self.__dict__.get("_selected_node_id")
        selected_value = labels.get(selected_id, labels[selectable[0].id])

        frame = ttk.Frame(actions, style="App.TFrame")
        ttk.Label(frame, text="Node", style="Description.TLabel").pack(anchor="w")
        self._node_selector_var = tk.StringVar(value=selected_value)
        self._node_selector = ttk.Combobox(
            frame,
            textvariable=self._node_selector_var,
            state="readonly",
            values=list(self._node_selector_values),
            width=18,
        )
        self._node_selector.pack(anchor="w")
        self._node_selector.bind("<<ComboboxSelected>>", self._on_node_selector_change)
        frame.pack(anchor="e", pady=(0, 9))
        self._node_selector_frame = frame

    def _on_node_selector_change(self, _event: object) -> None:
        registry = self.__dict__.get("_node_registry")
        selector = self.__dict__.get("_node_selector")
        selector_var = self.__dict__.get("_node_selector_var")
        if registry is None or selector is None or selector_var is None:
            return
        label = selector_var.get()
        node_id = self.__dict__.get("_node_selector_values", {}).get(label)
        if node_id is not None:
            self._switch_selected_node(node_id)

    def _switch_selected_node(self, node_id: NodeId) -> None:
        """Switch the dashboard to another selectable node.

        Cancels the current node's active scan first, then re-syncs the
        window's state mirrors from the new context, renders the new node's
        last-known-good snapshot, and starts a fresh scan for it. Node contexts
        keep their own snapshots, caches, capabilities, and scheduler so no
        value leaks across nodes. Unknown/non-selectable IDs are ignored
        defensively.
        """

        selection = self._node_selection()
        if selection is None:
            return
        selection.switch(node_id)

    def _invalidate_node_render_targets(self, node_id: NodeId) -> None:
        coordinator = self._render_coordinator()
        if coordinator is None:
            return
        generation = self._scan_coordinator_state().generation
        coordinator.invalidate(DASHBOARD_PAGE, generation, node_id=node_id)
        coordinator.invalidate("scan-status", generation, node_id=node_id)
        coordinator.invalidate("discovery-pages", 0, node_id=node_id)
        coordinator.invalidate(THERMALS_PAGE, 0, node_id=node_id)
        for feature in self._feature_catalog.all():
            coordinator.invalidate(f"component:{feature.key}", 0, node_id=node_id)

    def _refresh_selected_node_thermals(self, context: NodeContext) -> None:
        thermals_page = getattr(self, "thermals_page", None)
        router = getattr(self, "_page_router", None)
        if (
            thermals_page is not None
            and router is not None
            and router.is_mapped(THERMALS_PAGE)
        ):
            thermals_page.render(
                self._thermal_render_state(context),
                context.capabilities,
            )

    def _cancel_active_scan(self) -> None:
        """Cancel the in-flight full scan so its result cannot land on another node."""

        self._dashboard_scan_lifecycle().cancel()
        self._sync_dashboard_scan_state()

    def _cancel_node_operations(self, context: NodeContext | None) -> None:
        """Cancel every known component operation owned by one node context."""

        if context is None:
            return
        coordinator = self.__dict__.get("_coordinator")
        scheduler = getattr(context, "scheduler", None)
        node_id = getattr(context.descriptor, "id", None)
        for feature in self._feature_catalog.all():
            if coordinator is not None and node_id is not None:
                coordinator.cancel(
                    node_operation_key(node_id, f"component:{feature.key}")
                )
                if coordinator.in_flight(
                    node_operation_key(node_id, f"component:{feature.key}")
                ):
                    # Retain physical capacity until the worker acknowledges cancel.
                    continue
            cancel = getattr(scheduler, "cancel", None)
            if cancel is not None:
                try:
                    cancel(feature.key)
                except Exception as error:  # noqa: BLE001 - cancellation is best-effort.
                    LOGGER.debug(
                        "Ignoring cancellation failure for %s: %s", feature.key, error
                    )

    def _cancel_all_node_operations(self) -> None:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        for context in registry.contexts():
            self._cancel_node_operations(context)

    def _sync_selected_context_mirrors(self, context: NodeContext) -> None:
        """Point the window's historical attributes at the selected context's state."""

        self.analyzer = context.provider
        self.process_manager = context.process_manager
        self.file_manager = context.file_manager
        self.snapshot = context.snapshot
        self.__dict__["_node_snapshot"] = context.node_snapshot
        self._capabilities = context.capabilities
        self.__dict__["_capability_counts"] = context.capability_counts
        self.__dict__["_failed_card_counts"] = context.failed_card_counts
        self.__dict__["_full_snapshot_applied_at"] = context.full_snapshot_applied_at
        self._component_scheduler = context.scheduler
        self._reconcile_intervals()
        self._reconcile_cards_and_polling()

    def _render_selected_node(self, context: NodeContext) -> None:
        """Render one node's cached snapshot without starting a new scan."""

        snapshot = context.snapshot
        node_title_label = getattr(self, "node_title_label", None)
        if node_title_label is not None:
            presentation = render_target_state(context.descriptor, snapshot)
            node_title_label.config(text=context.descriptor.display_name.upper())
            target_status_label = getattr(self, "target_status_label", None)
            if target_status_label is not None:
                target_status_label.config(
                    text=(
                        f"{presentation.label} · {presentation.identity} · "
                        f"capabilities: {', '.join(presentation.capabilities) or 'none'}"
                    )
                )
        if snapshot is None:
            self.refreshed_label.config(text="Not refreshed yet")
            self.scan_time_label.config(text="Not scanned yet")
            self.health_label.config(
                text="Health: No issues detected", style="Healthy.TLabel"
            )
            for card in self.cards.values():
                card.reset_summary()
            return
        for key, card in self.cards.items():
            card.set_action_enabled(
                render_target_state(context.descriptor, snapshot, key).can_review
            )
        for resource in snapshot.resources:
            if resource.key in self.cards:
                self.cards[resource.key].update_summary(resource)
        scanned_time = snapshot.scanned_at.strftime("%H:%M:%S")
        self.scan_time_label.config(
            text=f"{snapshot.system_label} • scanned {scanned_time}"
        )
        self.refreshed_label.config(text=f"Last refreshed: {scanned_time}")
        self._refresh_health()

    def _get_discovery_session(self) -> DiscoverySession:
        session = self.__dict__.get("_discovery_session")
        if session is None:
            session = DiscoverySession(
                coordinator=self._coordinator,
                registry=self._node_registry,
                get_cluster_state=lambda: self.__dict__.get("_cluster_state"),
                set_cluster_state=lambda state: setattr(self, "_cluster_state", state),
                save_cluster_state=self._save_cluster_state,
                schedule_timer=self._schedule_timer,
                cancel_timer=self._cancel_timer,
                start_background_poll=self._start_background_poll,
                on_candidate=self._on_discovered_candidate,
                on_lost=self._on_discovered_lost,
                on_stabilized=lambda: self._queue_discovery_presentation(False),
                discovery_factory=NetworkDiscovery,
                app_version=__version__,
                is_closing=lambda: self._is_closing,
                get_listener_endpoint=self._listener_endpoint,
                on_presence_changed=self._reconcile_peer_connections,
            )
            session.timer_id = self.__dict__.get("_discovery_tick_id")
            self._discovery_session = session
        return session

    def _listener_endpoint(self) -> tuple[bool, int | None]:
        # The current listener is deliberately loopback-only. Do not advertise
        # a port that another machine cannot reach.
        return False, None

    def _start_peer_listener(self) -> None:
        """Start the target listener only when target-owned grants exist."""

        if self.__dict__.get("_peer_server") is not None:
            return
        grants = {
            NodeId(grant.caller_node_id): PeerGrant(
                caller_node_id=NodeId(grant.caller_node_id),
                secret=grant.secret,
                permissions=grant.permissions,
            )
            for grant in self._cluster_state.peer_grants
        }
        if not grants:
            return
        local_context = self._node_registry.context(NodeId("local"))
        descriptor = local_context.descriptor
        service = RemoteService(
            node_id=descriptor.id,
            display_name=descriptor.display_name,
            hostname=descriptor.hostname,
            platform=descriptor.platform,
            status=descriptor.status,
            capabilities=descriptor.capabilities,
            provider=local_context.provider,
            process_manager=local_context.process_manager,
            secret=generate_node_secret(),
            app_version=__version__,
            grants=grants,
            identity_fingerprint=descriptor.identity_fingerprint,
        )
        server = RemoteSocketServer(service, host="127.0.0.1")
        try:
            server.start()
        except OSError as error:
            LOGGER.warning("Remote peer listener unavailable: %s", error)
            return
        self._peer_server = server

    def _start_discovery(self) -> None:
        """Advertise this node and browse for peers via the shared coordinator.

        Discovery is optional infrastructure: when it is disabled in the
        cluster settings, or the transport is unavailable, or startup fails,
        the app continues as a normal single-node application and the registry
        simply has no discovered candidates.
        """

        if self.__dict__.get("_node_registry") is None:
            return
        if self.__dict__.get("_coordinator") is None:
            return
        session = self._get_discovery_session()
        result = session.start()
        self._discovery_tick_id = session.timer_id
        if result.reason == "disabled":
            self._nodes_status("Discovery disabled")
            return
        if result.started:
            self._nodes_status("Discovery running - no peers found")
        else:
            if result.reason in {"identity persistence", "local node unavailable"}:
                return
            if result.available:
                self._nodes_error(f"Discovery error: {result.reason}")
            else:
                self._nodes_error(f"Discovery backend unavailable: {result.reason}")

    def _tick_discovery(self) -> None:
        session = self._get_discovery_session()
        session.tick()
        self._discovery_tick_id = session.timer_id

    def _peer_connections(self) -> PeerConnectionManager | None:
        manager = self.__dict__.get("_peer_connection_manager")
        if manager is not None:
            return cast(PeerConnectionManager, manager)
        registry = self.__dict__.get("_node_registry")
        coordinator = self.__dict__.get("_coordinator")
        if registry is None or coordinator is None:
            return None
        # No unauthenticated connection operation is installed. A later
        # authenticated provider can replace this composition seam explicitly.
        manager = PeerConnectionManager(
            registry=registry,
            coordinator=coordinator,
            connect=lambda _context, _cancel_event, _progress: None,
            is_closing=lambda: self._is_closing,
            can_connect=lambda _context: False,
        )
        self.__dict__["_peer_connection_manager"] = manager
        return manager

    def _cancel_peer_connection(self, context: NodeContext) -> None:
        manager = self._peer_connections()
        if manager is not None:
            manager.cancel(context.node_id)

    def _reconcile_peer_connections(self) -> None:
        manager = self._peer_connections()
        if manager is None or self._is_closing:
            return
        deadline = manager.reconcile()
        self._schedule_peer_reconciliation(deadline)

    def _schedule_peer_reconciliation(self, deadline: float | None) -> None:
        self._cancel_timer(self.__dict__.get("_peer_reconcile_timer_id"))
        self.__dict__["_peer_reconcile_timer_id"] = None
        if deadline is None or self._is_closing:
            return
        delay = max(0, int((deadline - time.monotonic()) * 1000))
        self.__dict__["_peer_reconcile_timer_id"] = self._schedule_timer(
            delay, self._run_peer_reconciliation
        )

    def _run_peer_reconciliation(self) -> None:
        self.__dict__["_peer_reconcile_timer_id"] = None
        self._reconcile_peer_connections()

    def _on_discovered_candidate(self, candidate: Any) -> None:
        if self._is_closing:
            return
        registry = self.__dict__.get("_node_registry")
        trusted_descriptor = None
        trusted_updated = False
        if registry is not None:
            registry.update_discovered(candidate)
            if self._selected_node_id != registry.selected_id():
                self._switch_selected_node(registry.selected_id())
            try:
                context = registry.context(NodeId(candidate.stable_id))
            except KeyError:
                context = None
            if context is not None and is_trusted_descriptor(context.descriptor):
                trusted_descriptor = context.descriptor
            trusted_updated = self._sync_trusted_node_endpoint(candidate)
            if trusted_descriptor is not None:
                self.__dict__["_discovery_trusted_refresh_pending"] = True
            count = len(registry.discovered_candidates())
            self._nodes_status(
                f"Discovery running - {count} peer{'s' if count != 1 else ''} found"
            )
            if trusted_updated:
                try:
                    descriptor = registry.context(
                        NodeId(candidate.stable_id)
                    ).descriptor
                except KeyError:
                    descriptor = None
                if descriptor is not None:
                    self._nodes_status(
                        f"Verified {descriptor.display_name} at a new address"
                    )

    def _on_discovered_lost(self, stable_id: str) -> None:
        if self._is_closing:
            return
        registry = self.__dict__.get("_node_registry")
        trusted_descriptor = None
        if registry is not None:
            registry.remove_discovered(NodeId(stable_id))
            try:
                context = registry.context(NodeId(stable_id))
            except KeyError:
                context = None
            if context is not None and is_trusted_descriptor(context.descriptor):
                trusted_descriptor = context.descriptor
        if trusted_descriptor is not None:
            self.__dict__["_discovery_trusted_refresh_pending"] = True
        count = len(registry.discovered_candidates()) if registry is not None else 0
        self._nodes_status(
            f"Discovery running - {count} peers found"
            if count != 1
            else "Discovery running - 1 peer found"
        )

    def _queue_discovery_presentation(self, trusted_involved: bool) -> None:
        """Keep discovery mutations immediate while batching their rendering."""

        if trusted_involved:
            self.__dict__["_discovery_trusted_refresh_pending"] = True
        coordinator = self.__dict__.get("_coordinator")
        registry = self.__dict__.get("_node_registry")
        if coordinator is None or registry is None:
            return

        ui_discovery_refresh.post_discovery_refresh(
            coordinator=coordinator,
            key="discovery-pages",
            page=getattr(self, "nodes_page", None),
            get_peer_specs=self._nodes_peer_specs,
            get_trusted_specs=self._nodes_trusted_specs,
            should_refresh_trusted=lambda: bool(
                self.__dict__.pop("_discovery_trusted_refresh_pending", False)
            ),
            refresh_cluster_page=self._refresh_cluster_page,
            status_label=getattr(self, "discovery_status_label", None),
            get_discovered_candidates=registry.discovered_candidates,
            visible=bool(self.__dict__.get("_discovery_pages_visible", False)),
            is_active=lambda: not self._is_closing,
        )

    def _sync_trusted_node_endpoint(self, candidate: Any) -> bool:
        registry = self.__dict__.get("_node_registry")
        state = self.__dict__.get("_cluster_state")
        if registry is None or state is None:
            return False
        try:
            context = registry.context(NodeId(candidate.stable_id))
        except (AttributeError, KeyError):
            return False
        descriptor = context.descriptor
        if descriptor.is_local or not is_trusted_descriptor(descriptor):
            return False
        record = state.record(descriptor.id.value)
        if record is None:
            return False
        if (
            record.identity_fingerprint is not None
            and candidate.identity_fingerprint != record.identity_fingerprint
        ):
            context.descriptor = replace(
                descriptor,
                identity_fingerprint=record.identity_fingerprint,
                identity_status=NodeIdentityStatus.MISMATCH,
            )
            self._nodes_error(
                f"Identity mismatch for {descriptor.display_name}; re-pair required"
            )
            return False
        needs_identity_hydration = (
            record.identity_fingerprint is None
            and candidate.identity_fingerprint is not None
            and candidate.identity_fingerprint
            == node_identity_fingerprint(descriptor.id)
        )
        needs_identity_recovery = (
            descriptor.identity_status is NodeIdentityStatus.MISMATCH
            and record.identity_fingerprint is not None
            and candidate.identity_fingerprint == record.identity_fingerprint
        )
        address = candidate.addresses[0] if candidate.addresses else record.host
        port = candidate.port if candidate.port is not None else record.port
        endpoint_changed = address != record.host or port != record.port
        if not endpoint_changed and not (
            needs_identity_hydration or needs_identity_recovery
        ):
            return False
        if port is None:
            return False
        try:
            provider = AuthenticatedNodeProvider(
                node_id=descriptor.id,
                secret=record.secret,
                caller_node_id=NodeId(self._cluster_state.local_node_id),
                transport=SocketRemoteTransport(address, port),
            )
            hello = provider.hello()
            if not isinstance(hello, dict):
                raise TypeError("authenticated peer returned invalid hello metadata")
            if hello.get("node_id") != descriptor.id.value:
                raise RuntimeError("authenticated peer returned the wrong node ID")
            actual_fingerprint = hello.get("identity_fingerprint")
            if not isinstance(actual_fingerprint, str) or not actual_fingerprint:
                raise RuntimeError(
                    "authenticated peer returned no identity fingerprint"
                )
            if record.identity_fingerprint is not None and actual_fingerprint != (
                record.identity_fingerprint
            ):
                raise RuntimeError("authenticated peer identity fingerprint changed")
        except Exception as error:  # noqa: BLE001 - failed verification means no update.
            LOGGER.info(
                "Trusted node %s could not be verified at %s:%s: %s",
                descriptor.id,
                address,
                port,
                error,
            )
            return False
        display_name = record.display_name
        if display_name == record.hostname:
            display_name = descriptor.display_name
        updated_record = replace(
            record,
            display_name=display_name,
            hostname=descriptor.hostname,
            host=address,
            port=port,
            platform=descriptor.platform,
            identity_fingerprint=(
                candidate.identity_fingerprint
                if needs_identity_hydration
                else record.identity_fingerprint
            ),
        )
        if updated_record == record:
            if needs_identity_recovery:
                registry.confirm_identity(descriptor.id, candidate.identity_fingerprint)
                return True
            return False
        updated_records = tuple(
            updated_record if item.node_id == record.node_id else item
            for item in state.trusted_nodes
        )
        updated_state = ClusterState(
            discovery_enabled=state.discovery_enabled,
            trusted_nodes=updated_records,
            local_node_id=state.local_node_id,
            local_identity_persisted=state.local_identity_persisted,
            peer_grants=state.peer_grants,
        )
        if not self._save_cluster_state(updated_state):
            self._nodes_error("Cluster settings could not be saved")
            return False
        if needs_identity_hydration or needs_identity_recovery:
            registry.confirm_identity(descriptor.id, candidate.identity_fingerprint)
        return True

    def _refresh_discovery_status(self) -> None:
        """Render untrusted peer presence without offering any interaction."""

        label = getattr(self, "discovery_status_label", None)
        if label is None:
            return
        self._request_render(
            ui_render.RenderIntent(
                target="dashboard-discovery",
                components=frozenset({"discovery"}),
                layout_changed=True,
                payload=self._node_registry.discovered_candidates(),
                payload_set=True,
                priority=1,
            ),
            lambda _intent: ui_discovery_refresh.render_discovery_status(
                label,
                self._node_registry.discovered_candidates(),
            ),
        )

    def _stop_discovery(self) -> None:
        if "_node_registry" not in self.__dict__:
            self._cancel_timer(self.__dict__.get("_discovery_tick_id"))
            self._discovery_tick_id = None
            return
        if self.__dict__.get("_coordinator") is None:
            self._cancel_timer(self.__dict__.get("_discovery_tick_id"))
            self._discovery_tick_id = None
            return
        session = self._get_discovery_session()
        session.stop()
        self._discovery_tick_id = session.timer_id

    def _configure_styles(self) -> None:
        style = ttk.Style(self.master)
        style.theme_use("clam")
        ui_styles.configure_app_styles(style, colors=self.colors)
        self._style_obj = style

    def _apply_appearance(self) -> None:
        """Re-register styles and re-colour cards after an appearance change."""

        style = getattr(self, "_style_obj", None)
        if style is None:
            return
        colors = ui_styles.accent_theme_colors(self._preferences.appearance)
        ui_styles.configure_app_styles(style, colors=colors)
        cards = getattr(self, "cards", None)
        if cards:
            for card in cards.values():
                apply = getattr(card, "apply_colors", None)
                if apply is not None:
                    apply(colors)

    def _presentation_targets(self) -> list[tuple[Any, Any]]:
        """Return the ``(status_label, progress_bar)`` pairs to render into.

        The dashboard pair is always present; the Preferences Manual Scan pair
        is added when the Preferences page has been built. Both render the one
        shared scan state so they can never drift apart.
        """

        targets: list[tuple[Any, Any | None]] = [(self.status_label, None)]
        settings_label = getattr(self, "preferences_status_label", None)
        settings_bar = getattr(self, "preferences_progress_bar", None)
        if settings_label is not None and settings_bar is not None:
            targets.append((settings_label, settings_bar))
        return targets

    def _for_each_presentation_target(
        self,
        action: Callable[[Any, Any], Any],
    ) -> None:
        """Apply ``action`` to every ``(status_label, progress_bar)`` target.

        All callers render the same shared scan state into both the dashboard
        pair and the optional Preferences pair so the two can never drift.
        """

        for label, bar in self._presentation_targets():
            action(label, bar)

    def _set_busy(self, is_busy: bool) -> None:
        self.analyze_button.config(state=tk.DISABLED if is_busy else tk.NORMAL)
        self.cancel_button.config(state=tk.NORMAL if is_busy else tk.DISABLED)
        coordinator = getattr(self, "_button_coordinator", None)
        if coordinator is not None:
            if "preferences:scan" in coordinator.registered_ids():
                coordinator.set_enabled("preferences:scan", not is_busy)
            if "preferences:cancel-scan" in coordinator.registered_ids():
                coordinator.set_enabled("preferences:cancel-scan", is_busy)

        if is_busy:
            self.__dict__["_scan_progress_count"] = 0
            self._completion_transition().cancel()

            def apply_scanning_state(label: Any, bar: Any) -> None:
                if bar is not None:
                    scan_status.apply_reset(bar)
                scan_status.apply_scanning(label)

            self._for_each_presentation_target(apply_scanning_state)
        else:

            def apply_ready_state(label: Any, bar: Any) -> None:
                scan_status.apply_ready(label)
                if bar is not None:
                    bar.stop()

            self._for_each_presentation_target(apply_ready_state)

    def _completion_transition(self) -> ui_transition.PendingTransition:
        """The latest-wins timer behind the completion-hold status transition."""

        return self.__dict__.setdefault(
            "_completion_transition_obj",
            ui_transition.PendingTransition(self._schedule_timer, self._cancel_timer),
        )

    def _cancel_analysis(self) -> None:
        if self._analysis_cancel_event is None:
            return
        self._analysis_cancel_event.set()
        self.cancel_button.config(state=tk.DISABLED)
        coordinator = getattr(self, "_button_coordinator", None)
        if (
            coordinator is not None
            and "preferences:cancel-scan" in coordinator.registered_ids()
        ):
            coordinator.set_enabled("preferences:cancel-scan", False)
        self._for_each_presentation_target(
            lambda label, _bar: scan_status.apply_cancelling(label)
        )

    def _show_progress(self, message: str) -> None:
        if self._is_closing:
            return
        count = self.__dict__.get("_scan_progress_count", 0) + 1
        self.__dict__["_scan_progress_count"] = count
        self._for_each_presentation_target(
            lambda label, bar: (
                scan_status.apply_step(
                    label,
                    bar,
                    message,
                    count,
                    self._progress_total(),
                )
                if bar is not None
                else label.config(
                    text=scan_status.progress_text(
                        message, count, self._progress_total()
                    )
                )
            )
        )

    def _progress_total(self) -> int:
        return len(self._feature_catalog.all())

    def _run_daemon(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        if "_background_queue" not in self.__dict__:
            run_daemon(task, on_success, on_error, on_finished, logger=LOGGER)
            return
        self._background_service().run_daemon(task, on_success, on_error, on_finished)

    def _run_in_background(
        self,
        task: Callable[[], DashboardSnapshot],
        on_success: Callable[[DashboardSnapshot], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> bool:
        return self._background_service().run_in_background(
            task,
            on_success or self._show_snapshot,
            on_error or self._show_error,
            daemon_runner=self._run_daemon,
        )

    def _submit_ui(self, callback: Callable[[], None]) -> None:
        """Deliver one UI callback through the shared background queue.

        Thread-safe (a plain queue put) and drained on the Tkinter thread by
        ``_drain_background_queue``; worker threads never touch widgets.
        """

        self._background_service().submit_ui(callback)

    def _start_background_poll(self) -> None:
        self._background_service().start_poll()

    def _drain_background_queue(self) -> None:
        self._background_service().drain_queue()

    @staticmethod
    def _invoke_delivered(callback: Callable[[], None]) -> None:
        TimerDelivery.invoke(callback, LOGGER)

    def handle_analyze(self) -> None:
        if self._is_closing:
            return
        source_node_id = self.__dict__.get("_selected_node_id")
        source_context = self._selected_context()
        source_provider = (
            source_context.provider if source_context is not None else self.analyzer
        )

        def on_started(generation: int, _cancel_event: threading.Event) -> None:
            coordinator = self._render_coordinator()
            if coordinator is not None:
                coordinator.invalidate(
                    "scan-status", generation, node_id=source_node_id
                )
                coordinator.invalidate(
                    "dashboard-snapshot", generation, node_id=source_node_id
                )

        def start_worker(generation: int, cancel_event: threading.Event) -> None:
            resolved_node_snapshot: NodeSnapshot | None = None

            def report_progress(message: str) -> None:
                self._submit_ui(lambda: apply_progress(message))

            def apply_progress(message: str) -> None:
                if generation <= self._resolved_scan_generation:
                    return
                self._request_render(
                    ui_render.RenderIntent(
                        target="scan-status",
                        generation=generation,
                        node_id=source_node_id,
                        components=frozenset({"progress"}),
                        payload=message,
                        payload_set=True,
                        priority=1,
                    ),
                    lambda intent: self._show_progress(cast(str, intent.payload)),
                )

            def dashboard_task() -> DashboardSnapshot:
                provider_snapshot = getattr(
                    type(source_provider), "node_snapshot", None
                )
                if callable(provider_snapshot):
                    provider_snapshot = cast(Any, source_provider).node_snapshot
                    result = call_legacy_compatible(
                        lambda: provider_snapshot(
                            cancel_event=cancel_event,
                            progress_callback=report_progress,
                        ),
                        lambda: provider_snapshot(),
                    )
                else:
                    dashboard = call_legacy_compatible(
                        lambda: source_provider.dashboard_snapshot(
                            cancel_event=cancel_event,
                            progress_callback=report_progress,
                        ),
                        lambda: source_provider.dashboard_snapshot(),
                    )
                    descriptor = (
                        source_context.descriptor
                        if source_context is not None
                        else local_node_descriptor()
                    )
                    result = LocalNodeProvider(
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
                rerun_requested = self._resolution_for_generation(generation)
                if rerun_requested is None:
                    return
                self._set_busy(False)
                self._request_render(
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
                    lambda intent: self._show_node_snapshot_if_current(
                        generation,
                        cast(NodeSnapshot, intent.payload),
                        node_id=source_node_id,
                    ),
                )
                self._schedule_rerun_if_requested(rerun_requested)

            self._run_in_background(
                dashboard_task,
                on_success=queue_snapshot,
                on_error=lambda message: self._show_error_for_generation(
                    generation, message, node_id=source_node_id
                ),
            )

        self._dashboard_scan_lifecycle().start(
            on_started,
            start_worker,
        )
        self._sync_dashboard_scan_state()

    def _claim_scan_resolution(self, generation: int) -> tuple[bool, bool]:
        """Resolve a scan generation once and report its finish state.

        Returns ``(finished, rerun_requested)``; the first resolution of a
        generation wins, so late completions, timeouts, and errors cannot
        double-report the same scan.
        """

        result = self._dashboard_scan_lifecycle().claim_resolution(generation)
        self._sync_dashboard_scan_state()
        return result

    def _handle_scan_timeout(self, generation: int) -> None:
        self._dashboard_scan_lifecycle().handle_timeout(generation)
        self._sync_dashboard_scan_state()

    def _release_timed_out_lease(
        self,
        generation: int,
        *,
        cancel_grace_timer: bool,
    ) -> None:
        """Release a timed-out scan lease and honour any queued rerun.

        Shared by the grace timeout and the worker-completion paths so the
        resolution statement sequence exists once; the caller decides whether
        the pending grace timer must also be cancelled (the grace callback
        itself is that timer, so it must not cancel it).
        """

        self._dashboard_scan_lifecycle().release_timed_out_lease(
            generation, cancel_grace_timer=cancel_grace_timer
        )
        self._sync_dashboard_scan_state()

    def _release_lease_after_grace(self, generation: int) -> None:
        """Force-release a timed-out scan lease after a bounded grace window.

        A genuinely hung worker must not lock the dashboard out of scanning
        forever: after the grace period the lease is released anyway, so the
        rare physical overlap this bounded hold exists to prevent is accepted
        over a permanent lockout.
        """

        self._dashboard_scan_lifecycle().release_lease_after_grace(generation)
        self._sync_dashboard_scan_state()

    def _resolve_completed_worker(self) -> None:
        """Release the timed-out scan lease once its worker actually finishes.

        The timeout only presents the failure; the coordinator lease stays
        held so a new scan cannot physically overlap the old worker. When the
        worker's finish marker arrives the lease is released and any queued
        rerun is honoured.
        """

        self._dashboard_scan_lifecycle().resolve_completed_worker()
        self._sync_dashboard_scan_state()

    def _cancel_scan_timeout(self) -> None:
        self._dashboard_scan_lifecycle().cancel_timeout()
        self._sync_dashboard_scan_state()

    def _resolve_generation(self, generation: int) -> tuple[bool, bool]:
        """Resolve one scan generation, clearing its timeout and cancel event.

        Returns ``(resolved, rerun_requested)``; when the generation was
        already resolved, nothing is cleared.
        """

        result = self._dashboard_scan_lifecycle().resolve_generation(generation)
        self._sync_dashboard_scan_state()
        return result

    def _schedule_rerun_if_requested(self, rerun_requested: bool) -> None:
        """Re-run one coalesced scan when the finished generation requested it.

        Shared by every scan-completion path so the guard plus the deferred
        trigger stay in one place and can never drift apart.
        """

        if rerun_requested and not self._is_closing:
            self._schedule_timer(0, self.handle_analyze)

    def _resolution_for_generation(self, generation: int) -> bool | None:
        """Resolve one scan generation unless it was already timed out.

        Returns ``rerun_requested`` when the generation resolves, or ``None``
        when it was already timed out or already resolved. Shared by the
        snapshot and error completion handlers so the guard plus the
        resolution preamble exist in one place.
        """

        result = self._dashboard_scan_lifecycle().resolution_for_generation(generation)
        self._sync_dashboard_scan_state()
        return result

    def _show_snapshot_for_generation(
        self,
        generation: int,
        snapshot: DashboardSnapshot,
        *,
        node_snapshot: NodeSnapshot | None = None,
        node_id: NodeId | None = None,
    ) -> None:
        rerun_requested = self._resolution_for_generation(generation)
        if rerun_requested is None:
            return
        if node_id is None or node_id == self.__dict__.get("_selected_node_id"):
            self._show_snapshot(snapshot, node_snapshot=node_snapshot)
        self._schedule_rerun_if_requested(rerun_requested)

    def _show_node_snapshot_if_current(
        self,
        generation: int,
        node_snapshot: NodeSnapshot,
        *,
        node_id: NodeId | None = None,
    ) -> None:
        if node_snapshot.dashboard is None:
            return
        self._show_snapshot_if_current(
            generation,
            node_snapshot.dashboard,
            node_snapshot=node_snapshot,
            node_id=node_id,
        )

    def _show_snapshot_if_current(
        self,
        generation: int,
        snapshot: DashboardSnapshot,
        *,
        node_snapshot: NodeSnapshot | None = None,
        node_id: NodeId | None = None,
    ) -> None:
        """Commit a resolved snapshot only if its scan and node remain current."""

        if generation != self._scan_coordinator_state().generation:
            return
        if node_id is not None and node_id != self.__dict__.get("_selected_node_id"):
            return
        self._show_snapshot(snapshot, node_snapshot=node_snapshot)

    def _show_error_for_generation(
        self,
        generation: int,
        message: str,
        *,
        node_id: NodeId | None = None,
    ) -> None:
        rerun_requested = self._resolution_for_generation(generation)
        if rerun_requested is None:
            return
        if node_id is not None:
            try:
                context = self._node_registry.context(node_id)
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
        if node_id is not None and node_id != self.__dict__.get("_selected_node_id"):
            self._schedule_rerun_if_requested(rerun_requested)
            return
        if message == DOWNLOADS_SCAN_CANCELLED:
            self._set_busy(False)
            self._reset_progress_bar()
            self.refreshed_label.config(text=SCAN_CANCELLED_NOTICE)
            self._schedule_rerun_if_requested(rerun_requested)
            return
        self._show_error(message)
        self._schedule_rerun_if_requested(rerun_requested)

    def _show_snapshot(
        self,
        snapshot: DashboardSnapshot,
        *,
        node_snapshot: NodeSnapshot | None = None,
    ) -> None:
        if self._is_closing:
            return

        merged = self._merge_snapshot(snapshot)
        self.snapshot = merged
        context = self._selected_context()
        if context is not None:
            context.snapshot = merged
            if node_snapshot is not None:
                context.node_snapshot = node_snapshot
            context.full_snapshot_applied_at = time.monotonic()
        coordinator = self.__dict__.get("_coordinator")
        if coordinator is not None:
            coordinator.store(self._operation_key("snapshot:dashboard"), merged)
            if node_snapshot is not None:
                coordinator.store(
                    node_operation_key(node_snapshot.node_id, "node_snapshot"),
                    node_snapshot,
                )
        for resource in snapshot.resources:
            self._observe_capability(resource.key, resource)
            self._record_thermal_summary(resource.key, resource)
        for resource in merged.resources:
            self.cards[resource.key].update_summary(resource)
        self._full_snapshot_applied_at = time.monotonic()
        router = self.__dict__.get("_page_router")
        if router is None or router.is_mapped(CLUSTER_PAGE):
            self._refresh_cluster_page()

        scanned_time = snapshot.scanned_at.strftime("%H:%M:%S")
        self.scan_time_label.config(
            text=f"{snapshot.system_label} • scanned {scanned_time}"
        )
        self.refreshed_label.config(text=f"Last refreshed: {scanned_time}")
        self._set_busy(False)
        self._for_each_presentation_target(
            lambda label, bar: (
                scan_status.apply_complete(label, bar, self._progress_total())
                if bar is not None
                else label.config(
                    text=scan_status.COMPLETE_TEXT,
                    style=scan_status.READY_STYLE,
                )
            )
        )
        self._completion_transition().start(
            self.COMPLETION_HOLD_MILLISECONDS,
            self._show_ready_after_completion_hold,
        )
        self._refresh_health()
        self._refresh_thermals_page(
            self._thermal_render_state(context) if context is not None else None
        )
        self._component_scheduler.mark_all_refreshed(time.monotonic())
        self._schedule_component_poll(force=True)

    def _show_ready_after_completion_hold(self) -> None:
        """Return the status to Ready after the completion hold expires.

        The progress bar itself stays full until the next scan starts, so a
        finished scan remains visibly distinct from a frozen partial bar.
        """

        if self._is_closing:
            return
        if self._scan_coordinator_state().active:
            return
        self._for_each_presentation_target(
            lambda label, _bar: scan_status.apply_ready(label)
        )

    def _refresh_health(self) -> None:
        if not isinstance(self.snapshot, DashboardSnapshot):
            return
        warnings = health_warnings(
            self.snapshot,
            self.__dict__.setdefault("_health_state", {}),
        )
        if warnings:
            self.health_label.config(
                text="Health: " + " · ".join(warnings),
                style="HealthWarning.TLabel",
            )
        else:
            self.health_label.config(
                text="Health: No issues detected",
                style="Healthy.TLabel",
            )

    def _merge_snapshot(
        self,
        snapshot: DashboardSnapshot,
    ) -> DashboardSnapshot:
        """Keep last-valid card values while a refresh fails transiently.

        A card whose builder raised (``failed=True``) keeps its previous
        summary so valid information is never flashed away; after
        `FAILED_CARD_KEEP_LIMIT` consecutive failures the unavailable summary
        is shown deliberately. Cards with valid data always update, so one
        failing metric never erases unrelated information.
        """

        return snapshot_state.merge_snapshot(
            previous_snapshot=self.snapshot,
            failed_counts=self.__dict__.setdefault("_failed_card_counts", {}),
            snapshot=snapshot,
            failed_card_keep_limit=self.FAILED_CARD_KEEP_LIMIT,
        )

    def _merge_resource(
        self,
        key: str,
        resource: ResourceSummary,
    ) -> ResourceSummary:
        """Merge one incoming card against its last valid value."""

        return snapshot_state.merge_resource(
            previous_snapshot=self.snapshot,
            failed_counts=self.__dict__.setdefault("_failed_card_counts", {}),
            key=key,
            resource=resource,
            failed_card_keep_limit=self.FAILED_CARD_KEEP_LIMIT,
        )

    def open_resource(self, resource_key: str) -> None:
        if self.snapshot is None:
            messagebox.showinfo(
                "Scan Required",
                "Run the system scan before opening resource details.",
                parent=self.master,
            )
            return

        summary = self.snapshot.get(resource_key)
        feature = self._feature_catalog.get(resource_key)
        context = self._selected_context()
        if (
            context is not None
            and not render_target_state(
                context.descriptor, context.snapshot, resource_key
            ).can_review
        ):
            self._nodes_error(
                f"{context.descriptor.display_name} is not available for {resource_key} review"
            )
            return
        node_id = context.node_id if context is not None else None
        node_title = (
            context.descriptor.display_name
            if context is not None and self._multi_node_selectable()
            else None
        )
        if feature.action_kind == "process":
            if context is not None and not (
                context.descriptor.has(NodeCapability.PROCESS_REVIEW)
                and NodePermission.PROCESS_REVIEW in context.descriptor.permissions
            ):
                self._nodes_error("This node is not authorised for process review")
                return
            read_only = context is not None and not (
                context.descriptor.has(NodeCapability.PROCESS_TERMINATION)
                and NodePermission.PROCESS_TERMINATION in context.descriptor.permissions
            )
            ProcessDialog(
                self.master,
                analyzer=context.provider if context is not None else self.analyzer,
                provider=context.provider if context is not None else self.analyzer,
                manager=(
                    context.process_manager
                    if context is not None
                    else self.process_manager
                ),
                resource_key=resource_key,
                colors=self.colors,
                on_changed=lambda: self._rescan_node_after_change(node_id),
                coordinator=self._coordinator,
                node_id=node_id,
                node_title=node_title,
                read_only=read_only,
            )
        elif feature.action_kind == "storage":
            if context is not None and not (
                context.descriptor.has(NodeCapability.STORAGE_REVIEW)
                and NodePermission.STORAGE_REVIEW in context.descriptor.permissions
            ):
                self._nodes_error("This node is not authorised for storage review")
                return
            # Remote cleanup remains disabled until an opaque target-owned
            # candidate contract and target-side revalidation exist.
            read_only = context is not None
            StorageDialog(
                self.master,
                analyzer=context.provider if context is not None else self.analyzer,
                provider=context.provider if context is not None else self.analyzer,
                manager=(
                    context.file_manager if context is not None else self.file_manager
                ),
                colors=self.colors,
                on_changed=lambda: self._rescan_node_after_change(node_id),
                coordinator=self._coordinator,
                node_id=node_id,
                node_title=node_title,
                read_only=read_only,
            )
        else:
            InfoDialog(
                self.master,
                summary=summary,
                colors=self.colors,
            )

    def _rescan_after_change(self) -> None:
        self._schedule_timer(500, self.handle_analyze)

    def _rescan_node_after_change(self, node_id: NodeId | None) -> None:
        """Rescan only when an action's original target remains selected."""

        if node_id is None or node_id == self.__dict__.get("_selected_node_id"):
            self._rescan_after_change()

    def _component_poll_delay(self) -> int | None:
        scheduler = self.__dict__.get("_component_scheduler")
        if scheduler is None:
            return None
        now = time.monotonic()
        deadline = scheduler.next_deadline(now)
        if (
            getattr(self, "snapshot", None) is None
            or self.__dict__.get("_full_snapshot_applied_at") is None
        ):
            has_pending = scheduler.has_pending_work()
            if deadline is None:
                return None if has_pending else self.COMPONENT_POLL_MILLISECONDS
            if deadline > now:
                return max(0, int((deadline - now) * 1000))
            return 0 if has_pending else self.COMPONENT_POLL_MILLISECONDS
        if deadline is None:
            return None
        return max(0, int((deadline - now) * 1000))

    def _schedule_component_poll(
        self, *, force: bool = False, delay_override: int | None = None
    ) -> None:
        if self._is_closing:
            return
        delay = (
            delay_override
            if delay_override is not None
            else self._component_poll_delay()
        )
        if delay is None:
            if self._component_poll_id is not None:
                self._cancel_timer(self._component_poll_id)
                self._component_poll_id = None
            return
        if self._component_poll_id is not None and not force:
            return
        if self._component_poll_id is not None:
            self._cancel_timer(self._component_poll_id)
            self._component_poll_id = None
        self._component_poll_id = self._schedule_timer(delay, self._run_component_cycle)

    def _run_component_cycle(self) -> None:
        self._component_poll_id = None
        if self._is_closing:
            return
        router = self.__dict__.get("_page_router")
        dashboard_visible = router is None or router.is_mapped(DASHBOARD_PAGE)
        deferred_work = False
        for key in self._component_scheduler.due_keys(time.monotonic()):
            operation_key = self._operation_key(f"component:{key}")
            if dashboard_visible:
                self._launch_component_scan(key)
            else:
                deferred_work = True

                def launch_deferred_component(component_key: str = key) -> None:
                    self._launch_component_scan(component_key)

                self._coordinator.defer(
                    operation_key,
                    launch_deferred_component,
                )
        self._schedule_component_poll(
            force=True,
            delay_override=(
                self.COMPONENT_POLL_MILLISECONDS if deferred_work else None
            ),
        )

    def _launch_component_scan(self, key: str) -> None:
        source_context = self._selected_context()
        source_node_id = self.__dict__.get("_selected_node_id")
        source_scheduler = self._component_scheduler
        source_provider = self.analyzer
        if source_context is not None:
            source_scheduler = source_context.scheduler
            source_provider = source_context.provider
        operation_key = self._operation_key(f"component:{key}")
        coordinator_active = self._coordinator.in_flight(operation_key)
        scheduler_active = source_scheduler.in_flight(key)
        if coordinator_active and scheduler_active:
            source_scheduler.request_refresh(key)
            return
        if not source_scheduler.begin(key, time.monotonic()):
            return

        started_at = time.monotonic()

        def task_factory(
            _cancel_event: threading.Event,
            _progress: Callable[[str], None],
        ) -> ResourceSummary:
            return call_legacy_compatible(
                lambda: source_provider.component_summary(
                    key,
                    cancel_event=_cancel_event,
                ),
                lambda: source_provider.component_summary(key),
            )

        def finish_component() -> None:
            source_scheduler.finish(key)
            self._schedule_component_poll(force=True)

        def queue_component_snapshot(resource: ResourceSummary) -> None:
            render_generation = self._coordinator.generation(operation_key)
            self._request_render(
                ui_render.RenderIntent(
                    target=f"component:{key}",
                    generation=render_generation,
                    node_id=source_node_id,
                    components=frozenset({key}),
                    payload=resource,
                    payload_set=True,
                    priority=2,
                ),
                lambda intent: self._queue_component_result(
                    key,
                    started_at,
                    cast(ResourceSummary, intent.payload),
                    node_id=source_node_id,
                    scheduler_finished=True,
                ),
            )

        def queue_component_error(message: str) -> None:
            render_generation = self._coordinator.generation(operation_key)
            self._request_render(
                ui_render.RenderIntent(
                    target=f"component:{key}",
                    generation=render_generation,
                    node_id=source_node_id,
                    components=frozenset({key}),
                    payload=RuntimeError(message),
                    payload_set=True,
                    priority=2,
                ),
                lambda intent: self._queue_component_result(
                    key,
                    started_at,
                    cast(Exception, intent.payload),
                    node_id=source_node_id,
                    scheduler_finished=True,
                ),
            )

        run_generation = self._coordinator.run(
            operation_key,
            task_factory,
            on_result=lambda _operation, resource: queue_component_snapshot(resource),
            on_error=lambda _operation, message: queue_component_error(message),
            on_finished=finish_component,
        )
        if run_generation is None:
            # A stale coordinator state coalesced this trigger. Restore the
            # scheduler lease and retry after the existing worker settles.
            source_scheduler.finish(key)
            source_scheduler.request_refresh(key)
            self._schedule_component_poll(force=True)

    def _queue_component_result(
        self,
        key: str,
        started_at: float,
        value: ResourceSummary | Exception,
        *,
        node_id: NodeId | None = None,
        scheduler: ComponentRefreshScheduler | None = None,
        scheduler_finished: bool = False,
    ) -> None:
        """Apply one component scan result delivered on the Tkinter thread."""

        source_scheduler = scheduler or self._component_scheduler
        if not scheduler_finished:
            source_scheduler.finish(key)
        try:
            if node_id is not None and node_id != self.__dict__.get(
                "_selected_node_id"
            ):
                return
            applied_at = self.__dict__.get("_full_snapshot_applied_at")
            if applied_at is not None and started_at < applied_at:
                return
            if isinstance(value, Exception):
                resource = self._failed_component_summary(key)
            else:
                resource = value
            self._apply_component(key, resource)
        finally:
            self._schedule_component_poll(force=True)

    def _failed_component_summary(self, key: str) -> ResourceSummary:
        title = self._fallback_component_title(key)
        return unavailable_summary(key, title)

    def _record_thermal_summary(
        self,
        key: str,
        resource: ResourceSummary,
    ) -> TemperatureTelemetryUpdate | None:
        context = self._selected_context()
        telemetry = getattr(context, "telemetry", None) if context is not None else None
        if telemetry is not None:
            return telemetry.record_summary(key, resource)
        return None

    def _thermal_render_state(self, context: Any) -> TemperatureRenderState:
        return context.telemetry.render_state(("cpu", "gpu", "storage", "battery"))

    def _refresh_thermals_page(
        self,
        state: TemperatureRenderState | None = None,
    ) -> None:
        page = getattr(self, "thermals_page", None)
        context = self._selected_context()
        if page is None or context is None:
            return
        state = state or self._thermal_render_state(context)
        node_id = context.node_id
        intent = ui_render.RenderIntent(
            target=THERMALS_PAGE,
            node_id=node_id,
            components=frozenset({"temperature"}),
            payload=state,
            payload_set=True,
            priority=2,
        )

        def apply_thermals(_intent: ui_render.RenderIntent) -> None:
            page.render(
                state,
                context.capabilities,
            )

        self._request_render(intent, apply_thermals)

    def _fallback_component_title(self, key: str) -> str:
        """Return one card title from the feature catalog, falling back to key."""

        return self._feature_catalog.title_for(key) or key

    def _apply_component(self, key: str, resource: ResourceSummary) -> None:
        if self._is_closing:
            return
        self._observe_capability(key, resource)
        self._record_thermal_summary(key, resource)
        displayed = self._merge_resource(key, resource)
        coordinator = self.__dict__.get("_coordinator")
        if coordinator is not None:
            coordinator.store(self._operation_key(f"component:{key}"), displayed)
        if key in self.cards:
            self.cards[key].update_summary(displayed)
        self._update_snapshot_resource(key, displayed)
        self._refresh_thermals_page(
            self._thermal_render_state(self._selected_context())
            if self._selected_context() is not None
            else None
        )
        self._refresh_health()

    def _observe_capability(
        self,
        key: str,
        resource: ResourceSummary,
    ) -> None:
        """Track one component's definitive hardware capability.

        Only ``SUPPORTED``/``UNSUPPORTED`` observations change the tracked
        state; ``UNKNOWN`` (a transient failure) is ignored so it can never
        hide a card. ``UNSUPPORTED`` must be corroborated across consecutive
        observations before it is treated as definitive, so a single ambiguous
        or momentarily-undeterminable reading (e.g. a battery that reports
        ``None`` once) is never enough to hide the card. Capability is
        processed from the raw result before the last-valid display merge.
        """

        state = resource.capability
        if state == CapabilityState.UNKNOWN:
            return
        capabilities = self.__dict__.setdefault("_capabilities", {})
        counts = self.__dict__.setdefault("_capability_counts", {})

        if state == CapabilityState.SUPPORTED:
            counts[key] = 0
            if capabilities.get(key) != state:
                capabilities[key] = state
                self._reconcile_cards_and_polling()
            return

        counts[key] = counts.get(key, 0) + 1
        if counts[key] < self.UNSUPPORTED_CONFIRM_LIMIT:
            return
        if capabilities.get(key) != state:
            capabilities[key] = state
            self._reconcile_cards_and_polling()

    def _is_card_visible(self, key: str) -> bool:
        return card_policy.is_card_visible(
            key,
            preferences=self.__dict__.get("_preferences"),
            capabilities=self.__dict__.get("_capabilities", {}),
        )

    def _polling_policy(self, key: str) -> bool:
        """Return whether periodic polling for one component should pause.

        CPU, Memory and Storage always keep polling because their readings
        feed health warnings. GPU pauses only when automatically hidden by a
        proven-absent capability. Network and Battery pause when manually
        hidden or when proven absent and auto-hiding is enabled.
        """

        return card_policy.should_pause_polling(
            key,
            preferences=self.__dict__.get("_preferences"),
            capabilities=self.__dict__.get("_capabilities", {}),
        )

    def _grid_card(self, card: Any, index: int, columns: int) -> None:
        """Place one dashboard card in the responsive grid.

        Shared by the initial build (fixed three columns) and the visibility
        reflow (dynamic column count) so the placement rule exists once.
        """

        card.grid(
            row=index // columns,
            column=index % columns,
            sticky="nsew",
            padx=(
                0 if index % columns == 0 else 7,
                0 if index % columns == columns - 1 else 7,
            ),
            pady=(0, 14),
        )

    def _layout_dashboard_cards(self) -> None:
        """Reflow the visible cards and render an empty state when none remain.

        All six ``ResourceCard`` objects are retained and only re-gridded, so
        snapshots and component updates keep working for hidden cards and no
        fixed holes are left where a hidden card used to sit.
        """

        features = self.__dict__.get("_feature_catalog")
        cards = self.__dict__.get("cards")
        if features is None or cards is None:
            return
        visible = [
            feature for feature in features.all() if self._is_card_visible(feature.key)
        ]
        for card in cards.values():
            card.grid_forget()

        empty_label = self.__dict__.get("cards_empty_label")
        if not visible:
            if empty_label is None:
                empty_label = ttk.Label(
                    self.cards_frame,
                    text=(
                        "No cards are enabled. Open Settings to choose which "
                        "cards to show."
                    ),
                    style="Description.TLabel",
                )
                self.__dict__["cards_empty_label"] = empty_label
            empty_label.grid(row=0, column=0, sticky="w", padx=2, pady=8)
            self._refresh_cards_scrollbar()
            return
        if empty_label is not None:
            empty_label.grid_forget()

        columns = min(3, len(visible))
        for column in range(3):
            if column < columns:
                self.cards_frame.grid_columnconfigure(column, weight=1, uniform="cards")
            else:
                self.cards_frame.grid_columnconfigure(column, weight=0, uniform="")
        for index, feature in enumerate(visible):
            self._grid_card(cards[feature.key], index, columns)
        self._refresh_cards_scrollbar()

    def _reconcile_cards_and_polling(self) -> None:
        """Apply the current preferences to card layout and periodic polling.

        Components that transition out of pause are given one safe coalesced
        refresh request; full scans and the current scheduler in-flight guard
        prevent any duplicate or overlapping scans.
        """

        scheduler = self.__dict__.get("_component_scheduler")
        if scheduler is None:
            return
        self._layout_dashboard_cards()
        features = self.__dict__.get("_feature_catalog")
        if features is None:
            return
        for feature in features.all():
            key = feature.key
            if self._polling_policy(key):
                scheduler.pause(key)
                continue
            was_paused = scheduler.is_paused(key)
            scheduler.resume(key)
            if was_paused:
                self._request_component_refresh(key)

    def _request_component_refresh(self, key: str) -> None:
        """Queue one safe immediate refresh for a re-enabled component.

        Skipped while a full scan is active (its result satisfies the refresh)
        and before the first snapshot has been applied.
        """

        if self._scan_coordinator_state().active:
            return
        if not self.__dict__.get("_full_snapshot_applied_at"):
            return
        analyzer = getattr(self, "analyzer", None)
        if analyzer is not None and hasattr(analyzer, "reset_component_sample"):
            analyzer.reset_component_sample(key)
        self._component_scheduler.request_refresh(key)
        self._schedule_component_poll(force=True)

    def _reconcile_intervals(self) -> None:
        now = time.monotonic()
        current = self._component_scheduler.intervals
        for key, milliseconds in self._preferences.refresh_intervals.as_dict().items():
            if current.get(key) != milliseconds:
                self._component_scheduler.set_interval(key, milliseconds, now)
        self._schedule_component_poll(force=True)

    def _apply_preferences(self, candidate: AppPreferences) -> None:
        """Persist, then publish, one preferences candidate.

        The candidate is committed to disk before any runtime state changes;
        if persistence fails the runtime keeps the previous preferences and
        the Settings controls are restored.
        """

        try:
            self._preferences_store.save(candidate)
        except PreferencesSaveError as error:
            LOGGER.warning("Failed to save preferences: %s", error)
            self.preferences_page.refresh_from(self._preferences)
            self.preferences_page.show_error("Preferences could not be saved")
            return
        self._preferences = candidate
        self._reconcile_intervals()
        self._reconcile_cards_and_polling()
        self._apply_appearance()
        self.preferences_page.refresh_from(self._preferences)
        self.preferences_page.show_status("Preferences saved")

    def _try_apply_preference(
        self,
        builder: Callable[[], AppPreferences],
    ) -> bool:
        """Build and apply one validated preferences candidate.

        A ``ValueError`` from the candidate builder (an invalid interval or
        card key) restores the controls and shows the error without persisting.
        Persistence failures are not absorbed here; they are handled by
        ``_apply_preferences``. Returns whether the candidate was applied.
        """

        try:
            candidate = builder()
        except ValueError as error:
            self.preferences_page.refresh_from(self._preferences)
            self.preferences_page.show_error(str(error))
            return False
        self._apply_preferences(candidate)
        return True

    def _on_interval_commit(self, key: str, seconds: int) -> None:
        self._try_apply_preference(
            lambda: self._preferences.with_interval(key, seconds * 1000)
        )

    def _on_card_visibility_change(self, key: str, visible: bool) -> None:
        applied = self._try_apply_preference(
            lambda: self._preferences.with_card_visibility(key, visible)
        )
        if applied and visible:
            self._request_component_refresh(key)

    def _on_auto_hide_change(self, enabled: bool) -> None:
        self._apply_preferences(self._preferences.with_hide_unavailable_cards(enabled))

    def _on_appearance_change(self, theme: str) -> None:
        try:
            candidate = self._preferences.with_appearance(theme)
        except ValueError as error:
            self.preferences_page.refresh_from(self._preferences)
            self.preferences_page.show_error(str(error))
            return
        self._apply_preferences(candidate)

    def _on_reset(self) -> None:
        confirmed = messagebox.askyesno(
            "Reset Preferences?",
            "Reset all preferences to their defaults?",
            parent=self.master,
        )
        if not confirmed:
            return
        self._apply_preferences(AppPreferences.defaults())

    def _update_snapshot_resource(
        self,
        key: str,
        resource: ResourceSummary,
    ) -> None:
        updated = snapshot_state.replace_snapshot_resource(self.snapshot, key, resource)
        if updated is None:
            return
        self.snapshot = updated
        context = self._selected_context()
        if context is not None:
            context.snapshot = self.snapshot

    def _schedule_timer(
        self,
        delay: int,
        callback: Callable[..., None],
        *args: object,
    ) -> str | None:
        return self._timer_delivery_for_window().schedule(delay, callback, *args)

    def _cancel_timer(self, identifier: str | None) -> bool:
        return self._timer_delivery_for_window().cancel(identifier)

    def _cancel_pending_timers(self) -> None:
        self._timer_delivery_for_window().cancel_all()

    def _timer_delivery_for_window(self) -> TimerDelivery:
        timer_delivery = self.__dict__.get("_timer_delivery")
        if timer_delivery is None:
            timer_delivery = TimerDelivery(
                master=self.master,
                is_closing=lambda: self._is_closing,
                pending_ids=self._pending_after_ids,
                logger=LOGGER,
            )
            self.__dict__["_timer_delivery"] = timer_delivery
        return timer_delivery

    def _finalize_shutdown(self) -> None:
        """Release the scan lease and cancel every pending timer.

        Shared by the window's Close path and ``run()``'s ``finally`` so the
        two termination paths can never drift apart. Statement order is
        deliberate and preserved: the coordinator lease and per-path state are
        cleared, then all pending Tk timers are cancelled before the master is
        torn down. Discovery is stopped first so no late network event can
        reach a dying UI.
        """

        peer_server = self.__dict__.get("_peer_server")
        self.__dict__["_peer_server"] = None
        if peer_server is not None:
            peer_server.stop()
        self._stop_discovery()
        peer_manager = self.__dict__.get("_peer_connection_manager")
        if peer_manager is not None:
            peer_manager.shutdown()
        self._cancel_timer(self.__dict__.get("_peer_reconcile_timer_id"))
        self.__dict__["_peer_reconcile_timer_id"] = None
        self._dashboard_scan_lifecycle().cancel()
        self._sync_dashboard_scan_state()
        coordinator = self.__dict__.get("_coordinator")
        if coordinator is not None:
            coordinator.cancel_all()
            coordinator.shutdown()
        self._cancel_all_node_operations()
        cluster_page = getattr(self, "cluster_page", None)
        if cluster_page is not None:
            cluster_page.dispose()
        self._cancel_pending_timers()
        self._component_poll_id = None
        self._background_poll_id = None
        self._scan_timeout_id = None
        render_coordinator = self._render_coordinator()
        if render_coordinator is not None:
            render_coordinator.shutdown()

    def _stop_all_node_workers(self) -> None:
        """Stop every registered node's persistent scanner workers.

        The selected provider is stopped for backward compatibility with tests
        that only ever build the local analyzer; any other registered context
        providers are stopped too so no scanner thread survives the window.
        """

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

    def _close(self) -> None:
        self._is_closing = True
        self._finalize_shutdown()
        if self._analysis_cancel_event is not None:
            self._analysis_cancel_event.set()
        self._analysis_cancel_event = None
        self._stop_all_node_workers()
        self.master.destroy()

    def _show_error(self, message: str) -> None:
        if self._is_closing:
            return

        self._set_busy(False)
        self._reset_progress_bar()
        messagebox.showerror("Analysis Error", message, parent=self.master)

    def _reset_progress_bar(self) -> None:
        """Return the progress bars to their empty idle state (no false completion).

        Used by failure, timeout, and cancellation paths so an unfinished
        scan never leaves a full or frozen partial bar behind.
        """

        self._completion_transition().cancel()
        self._for_each_presentation_target(
            lambda _label, bar: (
                scan_status.apply_reset(bar) if bar is not None else None
            )
        )

    def run(self) -> None:
        try:
            self.master.mainloop()
        except KeyboardInterrupt:
            self._close()
        finally:
            if not self._is_closing:
                self._is_closing = True
                self._finalize_shutdown()
