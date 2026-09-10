import logging
import threading
import tkinter as tk
from collections.abc import Callable
from queue import Queue
from tkinter import messagebox, simpledialog, ttk
from typing import Any

import algo
from maintenance import __version__  # noqa: F401 - retained patch/import seam
from maintenance.actions import FileManager, ProcessManager
from maintenance.cluster import (
    ClusterSaveError,  # noqa: F401 - retained cluster patch seam
    ClusterState,
    ClusterStore,
    PeerGrantRecord,
    default_cluster_path,
)
from maintenance.components import (
    DOWNLOADS_SCAN_CANCELLED,  # noqa: F401 - retained scan patch seam
    DashboardScanLifecycle,
    NodeSelection,
    PeerConnectionManager,
    ResourceFeatureCatalog,
    ScanCoordinator,
    node_context,  # noqa: F401 - retained context patch seam
)
from maintenance.components.background_orchestration import (
    BackgroundItem,
    BackgroundOrchestrator,
)
from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
)
from maintenance.components.discovery_session import DiscoverySession
from maintenance.components.network_discovery import (  # noqa: F401 - patch seam
    NetworkDiscovery,
)
from maintenance.components.scan_support import (
    SCAN_CANCELLED_NOTICE,  # noqa: F401 - retained scan patch seam
    call_legacy_compatible,  # noqa: F401 - retained scan patch seam
)
from maintenance.components.temperature import (
    TemperatureRenderState,
    TemperatureTelemetryUpdate,
)
from maintenance.dialogs import (
    InfoDialog,  # noqa: F401 - retained dialog patch seam
    ProcessDialog,  # noqa: F401 - retained dialog patch seam
    ResourceCard,
    StorageDialog,  # noqa: F401 - retained dialog patch seam
)
from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    ResourceSummary,
)
from maintenance.nodes import (
    ConnectionState,  # noqa: F401 - retained scan patch seam
    LocalNodeProvider,  # noqa: F401 - retained scan patch seam
    NodeCapability,  # noqa: F401 - retained dialog patch seam
    NodeConnectionStatus,  # noqa: F401 - retained scan patch seam
    NodeContext,
    NodeId,
    NodePermission,  # noqa: F401 - retained dialog patch seam
    NodeRegistry,
    NodeSnapshot,
    generate_node_secret,  # noqa: F401 - retained listener patch seam
    is_trusted_descriptor,  # noqa: F401 - retained discovery patch seam
    local_node_descriptor,  # noqa: F401 - retained scan patch seam
    node_identity_fingerprint,  # noqa: F401 - retained discovery patch seam
    node_operation_key,  # noqa: F401 - retained dialog patch seam
)
from maintenance.preferences import (
    AppPreferences,
    PreferencesSaveError,  # noqa: F401 - retained preference patch seam
    PreferencesStore,
    default_preferences_path,
)
from maintenance.remote import (
    AuthenticatedNodeProvider,
    PeerGrant,  # noqa: F401 - retained dialog patch seam
    RemoteProcessActionBackend,
    RemoteService,  # noqa: F401 - retained listener patch seam
    RemoteSocketServer,
    SocketRemoteTransport,
)
from maintenance.ui import cluster_page as ui_cluster
from maintenance.ui import dashboard_page as ui_dashboard
from maintenance.ui import nodes_connections as ui_nodes
from maintenance.ui import preferences_page as ui_preferences
from maintenance.ui import render_coordinator as ui_render
from maintenance.ui import settings_home as ui_settings_home
from maintenance.ui import styles as ui_styles
from maintenance.ui import transition as ui_transition
from maintenance.ui import window_components as ui_window_components
from maintenance.ui import window_context as ui_window_context
from maintenance.ui import window_discovery as ui_window_discovery
from maintenance.ui import window_lifecycle as ui_window_lifecycle
from maintenance.ui import window_node_actions as ui_node_actions
from maintenance.ui import window_node_runtime as ui_node_runtime
from maintenance.ui import window_page_data as ui_window_page_data
from maintenance.ui import window_pages as ui_window_pages
from maintenance.ui import window_preferences as ui_window_preferences
from maintenance.ui import window_presentation as ui_window_presentation
from maintenance.ui import window_scan as ui_window_scan
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.navigation import PageRouter, PageSpec
from maintenance.ui.window_supports.timer_delivery import TimerDelivery

LOGGER = logging.getLogger(__name__)

DASHBOARD_PAGE = "dashboard"
SETTINGS_PAGE = "settings"
PREFERENCES_PAGE = "preferences"
NODES_PAGE = "nodes"
CLUSTER_PAGE = "cluster"
THERMALS_PAGE = "thermals"


class AppWindow:
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
            on_interrupt=self._close,
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
        ui_window_context.build_local_node_context(self)

    def _restore_trusted_nodes(self) -> None:
        ui_window_context.restore_trusted_nodes(self)

    @property
    def colors(self) -> dict[str, str]:
        return ui_window_page_data.colors(self)

    def _scan_coordinator_state(self) -> ScanCoordinator:
        return ui_window_scan.scan_coordinator_state(self)

    def _dashboard_scan_lifecycle(self) -> DashboardScanLifecycle:
        return ui_window_scan.dashboard_scan_lifecycle(self)

    def _sync_dashboard_scan_state(self) -> None:
        ui_window_scan.sync_dashboard_scan_state(self)

    def _selected_context(self) -> NodeContext | None:
        return ui_node_runtime.selected_context(self)

    def _operation_key(self, operation: str) -> str:
        return ui_node_runtime.operation_key(self, operation)

    def _multi_node_selectable(self) -> bool:
        return ui_node_runtime.multi_node_selectable(self)

    def _node_selection(self) -> NodeSelection | None:
        return ui_node_runtime.node_selection(self)

    def _schedule_selected_node_scan(self) -> None:
        ui_node_runtime.schedule_selected_node_scan(self)

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
        return ui_window_lifecycle.render_coordinator(self)

    def _make_background_orchestrator(self) -> BackgroundOrchestrator:
        return ui_window_lifecycle.make_background_orchestrator(self)

    def _background_service(self) -> BackgroundOrchestrator:
        return ui_window_lifecycle.background_service(self)

    def _request_render(
        self,
        intent: ui_render.RenderIntent,
        apply: Callable[[ui_render.RenderIntent], None],
    ) -> bool:
        return ui_window_lifecycle.request_render(self, intent, apply)

    def _sync_render_visibility(self, active_page: str | None) -> None:
        ui_window_lifecycle.sync_render_visibility(self, active_page)

    def _build_dashboard_page(self, parent: Any) -> Any:
        self.ttk = ttk
        self.tk = tk
        return ui_dashboard.build(self, parent)

    def _build_settings_home_page(self, parent: Any) -> Any:
        self.ttk = ttk
        return ui_window_pages.build_settings_home(self, parent)

    def _settings_categories(self) -> list[ui_settings_home.SettingsCategorySpec]:
        return ui_window_page_data.settings_categories(self)

    def _build_preferences_page(self, parent: Any) -> Any:
        self.ttk = ttk
        return ui_window_pages.build_preferences(self, parent)

    def _interval_specs(self) -> list[ui_preferences.IntervalControlSpec]:
        return ui_window_page_data.interval_specs(self)

    def _card_specs(self) -> list[ui_preferences.CardControlSpec]:
        return ui_window_page_data.card_specs(self)

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
        ui_window_pages.select_settings_category(self, key)

    def _show_nodes_page(self) -> None:
        self._refresh_nodes_page()
        ui_window_pages.show_page(self, NODES_PAGE, "nodes_page")

    def _build_nodes_page(self, parent: Any) -> Any:
        self.ttk = ttk
        return ui_window_pages.build_nodes(self, parent)

    def _start_discovery_from_nodes(self) -> None:
        if not self._cluster_state.discovery_enabled:
            self._apply_discovery_enabled(True)
            return
        self._start_discovery()

    def _nodes_peer_specs(self) -> list[ui_nodes.DiscoveredPeerSpec]:
        return ui_window_page_data.nodes_peer_specs(self)

    def _nodes_trusted_specs(self) -> list[ui_nodes.TrustedNodeSpec]:
        return ui_window_page_data.nodes_trusted_specs(self)

    def _nodes_manual_specs(self) -> list[ui_nodes.TrustedNodeSpec]:
        return ui_window_page_data.nodes_manual_specs(self)

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
        return ui_window_page_data.cluster_specs(self)

    def _refresh_cluster_page(self) -> None:
        ui_window_pages.refresh_cluster(self)

    def _save_cluster_state(self, state: ClusterState) -> bool:
        return ui_window_context.save_cluster_state(self, state)

    def _sync_peer_listener_grants(self) -> None:
        ui_window_context.sync_peer_listener_grants(self)

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
        ui_node_runtime.rebuild_node_selector(self)

    def _build_node_selector(self, actions: Any) -> None:
        ui_node_runtime.build_node_selector(self, actions)

    def _on_node_selector_change(self, _event: object) -> None:
        ui_node_runtime.on_node_selector_change(self, _event)

    def _switch_selected_node(self, node_id: NodeId) -> None:
        ui_node_runtime.switch_selected_node(self, node_id)

    def _invalidate_node_render_targets(self, node_id: NodeId) -> None:
        ui_node_runtime.invalidate_node_render_targets(self, node_id)

    def _refresh_selected_node_thermals(self, context: NodeContext) -> None:
        ui_node_runtime.refresh_selected_node_thermals(self, context)

    def _cancel_active_scan(self) -> None:
        ui_node_runtime.cancel_active_scan(self)

    def _cancel_node_operations(self, context: NodeContext | None) -> None:
        ui_node_runtime.cancel_node_operations(self, context)

    def _cancel_all_node_operations(self) -> None:
        ui_node_runtime.cancel_all_node_operations(self)

    def _sync_selected_context_mirrors(self, context: NodeContext) -> None:
        ui_node_runtime.sync_selected_context_mirrors(self, context)

    def _render_selected_node(self, context: NodeContext) -> None:
        ui_node_runtime.render_selected_node(self, context)

    def _get_discovery_session(self) -> DiscoverySession:
        return ui_window_discovery.get_discovery_session(self)

    def _listener_endpoint(self) -> tuple[bool, int | None]:
        return ui_window_discovery.listener_endpoint(self)

    def _start_peer_listener(self) -> None:
        ui_window_discovery.start_peer_listener(self)

    def _start_discovery(self) -> None:
        ui_window_discovery.start_discovery(self)

    def _tick_discovery(self) -> None:
        ui_window_discovery.tick_discovery(self)

    def _peer_connections(self) -> PeerConnectionManager | None:
        return ui_window_discovery.peer_connections(self)

    def _cancel_peer_connection(self, context: NodeContext) -> None:
        ui_window_discovery.cancel_peer_connection(self, context)

    def _reconcile_peer_connections(self) -> None:
        ui_window_discovery.reconcile_peer_connections(self)

    def _schedule_peer_reconciliation(self, deadline: float | None) -> None:
        ui_window_discovery.schedule_peer_reconciliation(self, deadline)

    def _run_peer_reconciliation(self) -> None:
        ui_window_discovery.run_peer_reconciliation(self)

    def _on_discovered_candidate(self, candidate: Any) -> None:
        ui_window_discovery.on_discovered_candidate(self, candidate)

    def _on_discovered_lost(self, stable_id: str) -> None:
        ui_window_discovery.on_discovered_lost(self, stable_id)

    def _queue_discovery_presentation(self, trusted_involved: bool) -> None:
        ui_window_discovery.queue_discovery_presentation(self, trusted_involved)

    def _sync_trusted_node_endpoint(self, candidate: Any) -> bool:
        return ui_window_discovery.sync_trusted_node_endpoint(self, candidate)

    def _refresh_discovery_status(self) -> None:
        ui_window_discovery.refresh_discovery_status(self)

    def _stop_discovery(self) -> None:
        ui_window_discovery.stop_discovery(self)

    def _configure_styles(self) -> None:
        ui_window_lifecycle.configure_styles(self)

    def _apply_appearance(self) -> None:
        ui_window_lifecycle.apply_appearance(self)

    def _presentation_targets(self) -> list[tuple[Any, Any]]:
        return ui_window_lifecycle.presentation_targets(self)

    def _for_each_presentation_target(
        self,
        action: Callable[[Any, Any], Any],
    ) -> None:
        """Apply ``action`` to every ``(status_label, progress_bar)`` target.

        All callers render the same shared scan state into both the dashboard
        pair and the optional Preferences pair so the two can never drift.
        """

        ui_window_lifecycle.for_each_presentation_target(self, action)

    def _set_busy(self, is_busy: bool) -> None:
        ui_window_lifecycle.set_busy(self, is_busy)

    def _completion_transition(self) -> ui_transition.PendingTransition:
        return ui_window_lifecycle.completion_transition(self)

    def _cancel_analysis(self) -> None:
        ui_window_lifecycle.cancel_analysis(self)

    def _show_progress(self, message: str) -> None:
        ui_window_lifecycle.show_progress(self, message)

    def _progress_total(self) -> int:
        return ui_window_lifecycle.progress_total(self)

    def _run_daemon(
        self,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        ui_window_lifecycle.run_daemon(self, task, on_success, on_error, on_finished)

    def _run_in_background(
        self,
        task: Callable[[], DashboardSnapshot],
        on_success: Callable[[DashboardSnapshot], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> bool:
        return ui_window_lifecycle.run_in_background(self, task, on_success, on_error)

    def _submit_ui(self, callback: Callable[[], None]) -> None:
        """Deliver one UI callback through the shared background queue.

        Thread-safe (a plain queue put) and drained on the Tkinter thread by
        ``_drain_background_queue``; worker threads never touch widgets.
        """

        ui_window_lifecycle.submit_ui(self, callback)

    def _start_background_poll(self) -> None:
        ui_window_lifecycle.start_background_poll(self)

    def _drain_background_queue(self) -> None:
        ui_window_lifecycle.drain_background_queue(self)

    @staticmethod
    def _invoke_delivered(callback: Callable[[], None]) -> None:
        ui_window_lifecycle.invoke_delivered(callback)

    def handle_analyze(self) -> None:
        ui_window_scan.handle_analyze(self)

    def _show_snapshot(
        self,
        snapshot: DashboardSnapshot,
        *,
        node_snapshot: NodeSnapshot | None = None,
    ) -> None:
        ui_window_presentation.show_snapshot(
            self, snapshot, node_snapshot=node_snapshot
        )

    def _show_ready_after_completion_hold(self) -> None:
        """Return the status to Ready after the completion hold expires.

        The progress bar itself stays full until the next scan starts, so a
        finished scan remains visibly distinct from a frozen partial bar.
        """

        ui_window_presentation.show_ready_after_completion_hold(self)

    def _refresh_health(self) -> None:
        ui_window_presentation.refresh_health(self)

    def _merge_snapshot(
        self,
        snapshot: DashboardSnapshot,
    ) -> DashboardSnapshot:
        return ui_window_components.merge_snapshot(self, snapshot)

    def _merge_resource(
        self,
        key: str,
        resource: ResourceSummary,
    ) -> ResourceSummary:
        return ui_window_components.merge_resource(self, key, resource)

    def open_resource(self, resource_key: str) -> None:
        ui_window_presentation.open_resource(self, resource_key)

    def _rescan_after_change(self) -> None:
        self._schedule_timer(500, self.handle_analyze)

    def _rescan_node_after_change(self, node_id: NodeId | None) -> None:
        """Rescan only when an action's original target remains selected."""

        if node_id is None or node_id == self.__dict__.get("_selected_node_id"):
            self._rescan_after_change()

    def _apply_preferences(self, candidate: AppPreferences) -> None:
        ui_window_preferences.apply_preferences(self, candidate)

    def _try_apply_preference(
        self,
        builder: Callable[[], AppPreferences],
    ) -> bool:
        return ui_window_preferences.try_apply_preference(self, builder)

    def _on_interval_commit(self, key: str, seconds: int) -> None:
        ui_window_preferences.on_interval_commit(self, key, seconds)

    def _on_card_visibility_change(self, key: str, visible: bool) -> None:
        ui_window_preferences.on_card_visibility_change(self, key, visible)

    def _on_auto_hide_change(self, enabled: bool) -> None:
        ui_window_preferences.on_auto_hide_change(self, enabled)

    def _on_appearance_change(self, theme: str) -> None:
        ui_window_preferences.on_appearance_change(self, theme)

    def _on_reset(self) -> None:
        ui_window_preferences.on_reset(self)

    def _component_poll_delay(self) -> int | None:
        return ui_window_components.component_poll_delay(self)

    def _schedule_component_poll(
        self, *, force: bool = False, delay_override: int | None = None
    ) -> None:
        ui_window_components.schedule_component_poll(
            self, force=force, delay_override=delay_override
        )

    def _run_component_cycle(self) -> None:
        ui_window_components.run_component_cycle(self)

    def _launch_component_scan(self, key: str) -> None:
        ui_window_components.launch_component_scan(self, key)

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
        ui_window_components.queue_component_result(
            self,
            key,
            started_at,
            value,
            node_id=node_id,
            scheduler=scheduler,
            scheduler_finished=scheduler_finished,
        )

    def _failed_component_summary(self, key: str) -> ResourceSummary:
        return ui_window_components.failed_component_summary(self, key)

    def _record_thermal_summary(
        self, key: str, resource: ResourceSummary
    ) -> TemperatureTelemetryUpdate | None:
        return ui_window_components.record_thermal_summary(self, key, resource)

    def _thermal_render_state(self, context: Any) -> TemperatureRenderState:
        return ui_window_components.thermal_render_state(self, context)

    def _refresh_thermals_page(
        self, state: TemperatureRenderState | None = None
    ) -> None:
        ui_window_components.refresh_thermals_page(self, state)

    def _fallback_component_title(self, key: str) -> str:
        return ui_window_components.fallback_component_title(self, key)

    def _apply_component(self, key: str, resource: ResourceSummary) -> None:
        ui_window_components.apply_component(self, key, resource)

    def _observe_capability(self, key: str, resource: ResourceSummary) -> None:
        ui_window_components.observe_capability(self, key, resource)

    def _is_card_visible(self, key: str) -> bool:
        return ui_window_components.is_card_visible(self, key)

    def _polling_policy(self, key: str) -> bool:
        return ui_window_components.polling_policy(self, key)

    def _grid_card(self, card: Any, index: int, columns: int) -> None:
        ui_window_components.grid_card(card, index, columns)

    def _layout_dashboard_cards(self) -> None:
        ui_window_components.layout_dashboard_cards(self)

    def _reconcile_cards_and_polling(self) -> None:
        ui_window_components.reconcile_cards_and_polling(self)

    def _request_component_refresh(self, key: str) -> None:
        ui_window_components.request_component_refresh(self, key)

    def _reconcile_intervals(self) -> None:
        ui_window_components.reconcile_intervals(self)

    def _update_snapshot_resource(self, key: str, resource: ResourceSummary) -> None:
        ui_window_components.update_snapshot_resource(self, key, resource)

    def _schedule_timer(
        self,
        delay: int,
        callback: Callable[..., None],
        *args: object,
    ) -> str | None:
        return ui_window_lifecycle.schedule_timer(self, delay, callback, *args)

    def _cancel_timer(self, identifier: str | None) -> bool:
        return ui_window_lifecycle.cancel_timer(self, identifier)

    def _cancel_pending_timers(self) -> None:
        ui_window_lifecycle.cancel_pending_timers(self)

    def _timer_delivery_for_window(self) -> TimerDelivery:
        return ui_window_lifecycle.timer_delivery_for_window(self)

    def _finalize_shutdown(self) -> None:
        ui_window_lifecycle.finalize_shutdown(self)

    def _stop_all_node_workers(self) -> None:
        ui_window_lifecycle.stop_all_node_workers(self)

    def _close(self) -> None:
        ui_window_lifecycle.close(self)

    def _show_error(self, message: str) -> None:
        ui_window_lifecycle.show_error(self, message)

    def _reset_progress_bar(self) -> None:
        ui_window_lifecycle.reset_progress_bar(self)

    def run(self) -> None:
        ui_window_lifecycle.run(self)

    def _claim_scan_resolution(self, generation: int) -> tuple[bool, bool]:
        return ui_window_scan.claim_scan_resolution(self, generation)

    def _handle_scan_timeout(self, generation: int) -> None:
        ui_window_scan.handle_scan_timeout(self, generation)

    def _release_timed_out_lease(
        self, generation: int, *, cancel_grace_timer: bool
    ) -> None:
        ui_window_scan.release_timed_out_lease(
            self, generation, cancel_grace_timer=cancel_grace_timer
        )

    def _release_lease_after_grace(self, generation: int) -> None:
        ui_window_scan.release_lease_after_grace(self, generation)

    def _resolve_completed_worker(self) -> None:
        ui_window_scan.resolve_completed_worker(self)

    def _cancel_scan_timeout(self) -> None:
        ui_window_scan.cancel_scan_timeout(self)

    def _resolve_generation(self, generation: int) -> tuple[bool, bool]:
        return ui_window_scan.resolve_generation(self, generation)

    def _schedule_rerun_if_requested(self, rerun_requested: bool) -> None:
        ui_window_scan.schedule_rerun_if_requested(self, rerun_requested)

    def _resolution_for_generation(self, generation: int) -> bool | None:
        return ui_window_scan.resolution_for_generation(self, generation)

    def _show_snapshot_for_generation(
        self,
        generation: int,
        snapshot: DashboardSnapshot,
        *,
        node_snapshot: NodeSnapshot | None = None,
        node_id: NodeId | None = None,
    ) -> None:
        ui_window_scan.show_snapshot_for_generation(
            self,
            generation,
            snapshot,
            node_snapshot=node_snapshot,
            node_id=node_id,
        )

    def _show_node_snapshot_if_current(
        self,
        generation: int,
        node_snapshot: NodeSnapshot,
        *,
        node_id: NodeId | None = None,
    ) -> None:
        ui_window_scan.show_node_snapshot_if_current(
            self, generation, node_snapshot, node_id=node_id
        )

    def _show_snapshot_if_current(
        self,
        generation: int,
        snapshot: DashboardSnapshot,
        *,
        node_snapshot: NodeSnapshot | None = None,
        node_id: NodeId | None = None,
    ) -> None:
        ui_window_scan.show_snapshot_if_current(
            self,
            generation,
            snapshot,
            node_snapshot=node_snapshot,
            node_id=node_id,
        )

    def _show_error_for_generation(
        self,
        generation: int,
        message: str,
        *,
        node_id: NodeId | None = None,
    ) -> None:
        ui_window_scan.show_error_for_generation(
            self, generation, message, node_id=node_id
        )
