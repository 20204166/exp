import logging
import platform
import threading
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from queue import Empty, Queue
from tkinter import messagebox, simpledialog, ttk
from typing import Any, cast

import algo
from maintenance import __version__
from maintenance.actions import FileManager, ProcessManager
from maintenance.cluster import (
    ClusterSaveError,
    ClusterState,
    ClusterStore,
    default_cluster_path,
    trusted_node_record,
)
from maintenance.components import (
    DOWNLOADS_SCAN_CANCELLED,
    JobProfile,
    ResourceFeatureCatalog,
    ResourceGovernor,
    ScanCoordinator,
)
from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
)
from maintenance.components.network_discovery import (
    PROTOCOL_VERSION,
    REAP_TICK_SECONDS,
    DiscoveryAdvertisement,
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
    LOCAL_NODE_ID,
    NodeCapability,
    NodeContext,
    NodeDescriptor,
    NodeId,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
    is_trusted_descriptor,
    local_node_descriptor,
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
    READ_CAPABILITIES,
    AuthenticatedNodeProvider,
    SocketRemoteTransport,
)
from maintenance.ui import cluster_page as ui_cluster
from maintenance.ui import discovery_refresh as ui_discovery_refresh
from maintenance.ui import layout as ui_layout
from maintenance.ui import nodes_connections as ui_nodes
from maintenance.ui import preferences_page as ui_preferences
from maintenance.ui import render_coordinator as ui_render
from maintenance.ui import scan_status
from maintenance.ui import settings_home as ui_settings_home
from maintenance.ui import styles as ui_styles
from maintenance.ui import thermals_page as ui_thermals
from maintenance.ui import transition as ui_transition
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.navigation import PageRouter, PageSpec

LOGGER = logging.getLogger(__name__)

DASHBOARD_PAGE = "dashboard"
SETTINGS_PAGE = "settings"
PREFERENCES_PAGE = "preferences"
NODES_PAGE = "nodes"
CLUSTER_PAGE = "cluster"
THERMALS_PAGE = "thermals"


class AppWindow:
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
        master: tk.Tk | None = None,
        *,
        preferences_store: PreferencesStore | None = None,
        cluster_store: ClusterStore | None = None,
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
        self._background_queue: Queue[
            tuple[Callable[..., None], tuple[object, ...]] | None | tuple[str, Any]
        ] = Queue()
        self._coordinator = AppCoordinator(
            deliver=self._submit_ui,
            on_activity=self._start_background_poll,
        )
        self._resource_governor = ResourceGovernor()
        self._resource_governor.request_pressure_sample()
        self._component_scheduler = ComponentRefreshScheduler(
            self._preferences.refresh_intervals.as_dict()
        )
        self._button_coordinator = ButtonCoordinator()
        self._ui_coordinator = ui_render.UICoordinator()
        self._feature_catalog = ResourceFeatureCatalog()
        self._component_poll_id: str | None = None
        self._capabilities: dict[str, CapabilityState] = {}
        self._node_registry = NodeRegistry()
        self._selected_node_id: NodeId | None = None
        self._discovery_tick_id: str | None = None
        self._build_local_node_context()
        self._restore_trusted_nodes()

        self.master = master or tk.Tk()
        self.master.title("System Analyzer")
        self.master.geometry("1040x760")
        self.master.minsize(900, 680)
        self.master.configure(bg=self.BACKGROUND)
        self.master.protocol("WM_DELETE_WINDOW", self._close)

        self._configure_styles()
        self._build_window()
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

        descriptor = local_node_descriptor(
            hostname=platform.node(),
            display_name="This System",
            platform_name=platform.system(),
        )
        context = NodeContext(
            descriptor=descriptor,
            provider=self.analyzer,
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
        for record in state.trusted_nodes:
            if record.node_id == LOCAL_NODE_ID:
                continue
            node_id = NodeId(record.node_id)
            try:
                registry.context(node_id)
                continue
            except KeyError:
                pass
            descriptor = NodeDescriptor(
                id=node_id,
                display_name=record.display_name,
                hostname=record.hostname,
                is_local=False,
                trust=NodeTrustState.TRUSTED,
                status=NodeStatus.UNKNOWN,
                capabilities=record.capabilities,
                platform=record.platform,
                color=record.color,
            )
            context = NodeContext(
                descriptor=descriptor,
                provider=None,
                process_manager=None,
                file_manager=None,
                scheduler=None,
                coordinator=None,
            )
            try:
                registry.register_context(context)
            except ValueError as error:
                LOGGER.warning(
                    "Failed to restore trusted node %s: %s", record.node_id, error
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

    def _selected_context(self) -> NodeContext | None:
        """Return the selected node's runtime context, or None outside the app.

        Tests construct ``AppWindow`` with ``object.__new__`` and no registry,
        so callers must treat ``None`` as the legacy single-node behaviour.
        """

        registry = self.__dict__.get("_node_registry")
        selected = self.__dict__.get("_selected_node_id")
        if registry is None or selected is None:
            return None
        try:
            return registry.context(selected)
        except KeyError:
            return None

    def _operation_key(self, operation: str) -> str:
        """Return a node-qualified coordinator key for the selected node.

        Outside the registry (tests) the legacy unqualified key is returned so
        existing coordinator-key assertions keep passing; inside the app every
        shared operation key is namespaced so two nodes can never coalesce or
        overwrite each other's work.
        """

        registry = self.__dict__.get("_node_registry")
        selected = self.__dict__.get("_selected_node_id")
        if registry is None or selected is None:
            return operation
        return node_operation_key(selected, operation)

    def _multi_node_selectable(self) -> bool:
        registry = self.__dict__.get("_node_registry")
        return registry is not None and len(registry.selectable_descriptors()) > 1

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
        coordinator = self._render_coordinator()
        if coordinator is None:
            return
        dashboard_visible = active_page == DASHBOARD_PAGE
        coordinator.set_visible("dashboard-snapshot", dashboard_visible)
        coordinator.set_visible(
            "scan-status",
            active_page in {DASHBOARD_PAGE, PREFERENCES_PAGE},
        )
        coordinator.set_visible("dashboard-discovery", active_page == DASHBOARD_PAGE)
        coordinator.set_visible(THERMALS_PAGE, active_page == THERMALS_PAGE)
        coordinator.set_visible(
            "discovery-pages",
            active_page in {NODES_PAGE, CLUSTER_PAGE},
        )
        coordinator.set_visible("nodes-status", active_page == NODES_PAGE)
        for feature in self._feature_catalog.all():
            coordinator.set_visible(f"component:{feature.key}", dashboard_visible)

    def _build_dashboard_page(self, parent: Any) -> Any:
        self.main_frame = ttk.Frame(
            parent,
            padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
            style="App.TFrame",
        )

        node_title = None
        if self._multi_node_selectable():
            context = self._selected_context()
            if context is not None:
                node_title = context.descriptor.display_name

        self.header_actions = ui_layout.dashboard_header(
            self.main_frame,
            title="System Analyzer",
            description=(
                "Scan your system, open any category, and review safe cleanup "
                "actions before anything changes."
            ),
            frame_cls=ttk.Frame,
            label_cls=ttk.Label,
            wrap=680,
            node_title=node_title,
        )
        self.node_title_label = getattr(
            self.header_actions,
            "_dashboard_node_label",
            None,
        )
        self.discovery_status_label = getattr(
            self.header_actions,
            "_dashboard_discovery_label",
            None,
        )
        ui_discovery_refresh.render_discovery_status(
            self.discovery_status_label,
            self._node_registry.discovered_candidates(),
        )

        self.settings_button = ttk.Button(
            self.header_actions,
            text="Settings",
            command=self._show_settings_page,
            style="Neutral.TButton",
            cursor="hand2",
        )
        self.cluster_button = ttk.Button(
            self.header_actions,
            text="All Systems",
            command=self._show_cluster_page,
            style="Neutral.TButton",
            cursor="hand2",
        )
        self.thermals_button = ttk.Button(
            self.header_actions,
            text="Thermals",
            command=self._show_thermals_page,
            style="Neutral.TButton",
            cursor="hand2",
        )
        self._button_coordinator.register(
            "dashboard:settings",
            self._show_settings_page,
            replace=True,
        )
        self._button_coordinator.bind(self.settings_button, "dashboard:settings")
        self._button_coordinator.register(
            "dashboard:cluster",
            self._show_cluster_page,
            replace=True,
        )
        self._button_coordinator.bind(self.cluster_button, "dashboard:cluster")
        self._button_coordinator.register(
            "dashboard:thermals",
            self._show_thermals_page,
            replace=True,
        )
        self._button_coordinator.bind(self.thermals_button, "dashboard:thermals")
        self._build_node_selector(self.header_actions)
        self.settings_button.pack(anchor="e")
        self.cluster_button.pack(anchor="e", padx=(8, 0))
        self.thermals_button.pack(anchor="e", padx=(8, 0))

        self.status_label = ttk.Label(
            self.header_actions,
            text="●  Ready",
            style="Ready.Status.TLabel",
        )
        self.status_label.pack(anchor="e", pady=(9, 0))

        self.progress_bar = ttk.Progressbar(
            self.main_frame,
            mode="determinate",
            maximum=len(self._feature_catalog.all()),
            style="Analysis.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill="x", pady=(22, 20))

        self.overview_frame = ttk.Frame(self.main_frame, style="App.TFrame")
        self.overview_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(
            self.overview_frame,
            text="System overview",
            style="Section.TLabel",
        ).pack(side="left")
        self.scan_time_label = ttk.Label(
            self.overview_frame,
            text="Not scanned yet",
            style="Description.TLabel",
        )
        self.scan_time_label.pack(side="right")

        self.cards_container = ttk.Frame(self.main_frame, style="App.TFrame")
        self.cards_container.pack(fill="both", expand=True)
        (
            self.cards_canvas,
            self.cards_frame,
            self._refresh_cards_scrollbar,
        ) = ui_layout.scrollable_area(
            self.cards_container,
            bg=self.BACKGROUND,
            frame_cls=ttk.Frame,
            canvas_cls=tk.Canvas,
            scrollbar_cls=ttk.Scrollbar,
            frame_kwargs={"style": "App.TFrame"},
        )

        for column in range(3):
            self.cards_frame.grid_columnconfigure(column, weight=1, uniform="cards")

        self.cards: dict[str, ResourceCard] = {}
        for index, feature in enumerate(self._feature_catalog.all()):
            action_id = f"dashboard:resource:{feature.key}"

            def open_feature(key: str = feature.key) -> None:
                self.open_resource(key)

            self._button_coordinator.register(
                action_id,
                open_feature,
                replace=True,
            )
            card = ResourceCard(
                self.cards_frame,
                key=feature.key,
                title=feature.title,
                on_open=self.open_resource,
                colors=self.colors,
                action_id=action_id,
                button_coordinator=self._button_coordinator,
            )
            self._grid_card(card, index, 3)
            self.cards[feature.key] = card
        self.cards_empty_label: ttk.Label | None = None

        self.refreshed_label = ttk.Label(
            self.main_frame,
            text="Not refreshed yet",
            style="Description.TLabel",
        )
        self.refreshed_label.pack(anchor="w", pady=(4, 0))

        self.health_label = ttk.Label(
            self.main_frame,
            text="Health: No issues detected",
            style="Healthy.TLabel",
        )
        self.health_label.pack(anchor="w", pady=(2, 0))

        self._layout_dashboard_cards()
        return self.main_frame

    def _build_settings_home_page(self, parent: Any) -> Any:
        self.settings_frame = ttk.Frame(
            parent,
            padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
            style="App.TFrame",
        )
        self.settings_home = ui_settings_home.SettingsHome(
            self.settings_frame,
            callbacks=ui_settings_home.SettingsHomeCallbacks(
                on_back=self._show_dashboard_page,
                on_select_category=self._on_select_settings_category,
                on_start_discovery=self._start_discovery_from_settings,
            ),
            categories=self._settings_categories(),
            version=__version__,
            button_coordinator=self._button_coordinator,
        )
        return self.settings_frame

    def _start_discovery_from_settings(self) -> None:
        """Enable and start local discovery from the Settings home page."""

        if not self._cluster_state.discovery_enabled:
            self._apply_discovery_enabled(True)
            return
        self._start_discovery()
        self._show_nodes_page()

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
        self.preferences_frame = ttk.Frame(
            parent,
            padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
            style="App.TFrame",
        )
        self.preferences_page = ui_preferences.PreferencesPage(
            self.preferences_frame,
            callbacks=ui_preferences.PreferencesPageCallbacks(
                on_back=self._show_settings_page,
                on_interval_commit=self._on_interval_commit,
                on_card_visibility_change=self._on_card_visibility_change,
                on_auto_hide_change=self._on_auto_hide_change,
                on_scan=self.handle_analyze,
                on_cancel_scan=self._cancel_analysis,
                on_reset=self._on_reset,
                on_appearance_change=self._on_appearance_change,
            ),
            intervals=self._interval_specs(),
            cards=self._card_specs(),
            hide_unavailable_cards=self._preferences.hide_unavailable_cards,
            appearance=self._preferences.appearance,
            button_coordinator=self._button_coordinator,
        )
        self.analyze_button = self.preferences_page.analyze_button
        self.cancel_button = self.preferences_page.cancel_button
        self.preferences_status_label = self.preferences_page.manual_status_label
        self.preferences_progress_bar = self.preferences_page.manual_progress_bar
        return self.preferences_frame

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
        self._page_router.show(SETTINGS_PAGE)
        self._sync_render_visibility(SETTINGS_PAGE)
        self.settings_home.focus_back()

    def _show_preferences_page(self) -> None:
        self._page_router.show(PREFERENCES_PAGE)
        self._sync_render_visibility(PREFERENCES_PAGE)
        self.preferences_page.focus_back()

    def _show_dashboard_page(self) -> None:
        self._page_router.show(DASHBOARD_PAGE)
        self._sync_render_visibility(DASHBOARD_PAGE)
        button = getattr(self, "settings_button", None)
        if button is not None:
            button.focus_set()

    def _show_thermals_page(self) -> None:
        page = getattr(self, "thermals_page", None)
        context = self._selected_context()
        if page is not None:
            page.render(
                self._thermal_render_state(context) if context is not None else None,
                getattr(context, "capabilities", None) if context is not None else None,
            )
        self._page_router.show(THERMALS_PAGE)
        self._sync_render_visibility(THERMALS_PAGE)
        if page is not None:
            page.focus_back()

    def _build_thermals_page(self, parent: Any) -> Any:
        self.thermals_frame = ttk.Frame(
            parent,
            padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
            style="App.TFrame",
        )
        self.thermals_page = ui_thermals.ThermalsPage(
            self.thermals_frame,
            callbacks=ui_thermals.ThermalsPageCallbacks(
                on_back=self._show_dashboard_page,
            ),
            colors=self.colors,
        )
        return self.thermals_frame

    def _on_select_settings_category(self, key: str) -> None:
        """Route one Settings category card to its dedicated page.

        Unknown keys are ignored defensively so adding a category later is a
        matter of registering its page and a handler here.
        """

        handlers = {
            "preferences": self._show_preferences_page,
            "nodes": self._show_nodes_page,
            "cluster": self._show_cluster_page,
        }
        handler = handlers.get(key)
        if handler is not None:
            handler()

    def _show_nodes_page(self) -> None:
        self._refresh_nodes_page()
        self._page_router.show(NODES_PAGE)
        self._sync_render_visibility(NODES_PAGE)
        page = getattr(self, "nodes_page", None)
        if page is not None:
            page.focus_back()

    def _build_nodes_page(self, parent: Any) -> Any:
        self.nodes_frame = ttk.Frame(
            parent,
            padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
            style="App.TFrame",
        )
        self.nodes_page = ui_nodes.NodesConnectionsPage(
            self.nodes_frame,
            callbacks=ui_nodes.NodesConnectionsCallbacks(
                on_back=self._show_settings_page,
                on_discovery_toggle=self._apply_discovery_enabled,
                on_pair=self._pair_discovered_node,
                on_reject=self._reject_discovered_node,
                on_rename=self._rename_node,
                on_color=self._set_node_color,
                on_revoke=self._revoke_trusted_node,
                on_test_connection=self._test_connection,
                on_open_node=self._open_cluster_node,
                on_add_manual_host=self._add_manual_host,
                on_remove_manual=self._remove_manual_host,
            ),
            discovery_enabled=self._cluster_state.discovery_enabled,
            discovered=self._nodes_peer_specs(),
            trusted=self._nodes_trusted_specs(),
            manual=self._nodes_manual_specs(),
            button_coordinator=self._button_coordinator,
        )
        return self.nodes_frame

    def _nodes_peer_specs(self) -> list[ui_nodes.DiscoveredPeerSpec]:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return []
        return [
            ui_nodes.DiscoveredPeerSpec(
                node_id=candidate.stable_id,
                hostname=candidate.hostname,
                app_version=candidate.app_version,
                compatible=candidate.compatible,
                connectable=candidate.connectable,
                port=candidate.port,
            )
            for candidate in registry.discovered_candidates()
        ]

    def _nodes_trusted_specs(self) -> list[ui_nodes.TrustedNodeSpec]:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return []
        manual: set[str] = getattr(self, "_manual_host_ids", set())
        selectable = {descriptor.id for descriptor in registry.selectable_descriptors()}
        specs: list[ui_nodes.TrustedNodeSpec] = []
        for context in registry.contexts():
            descriptor = context.descriptor
            if descriptor.is_local:
                continue
            if not is_trusted_descriptor(descriptor):
                continue
            if descriptor.id.value in manual:
                continue
            record = self._cluster_state.record(descriptor.id.value)
            specs.append(
                ui_nodes.TrustedNodeSpec(
                    node_id=descriptor.id.value,
                    display_name=descriptor.display_name,
                    hostname=descriptor.hostname,
                    color=descriptor.color,
                    status=descriptor.status.value,
                    host=record.host if record is not None else descriptor.hostname,
                    port=record.port if record is not None else None,
                    selectable=descriptor.id in selectable,
                )
            )
        return specs

    def _nodes_manual_specs(self) -> list[ui_nodes.TrustedNodeSpec]:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return []
        specs: list[ui_nodes.TrustedNodeSpec] = []
        for node_id in tuple(getattr(self, "_manual_host_ids", set())):
            try:
                context = registry.context(NodeId(node_id))
            except KeyError:
                continue
            descriptor = context.descriptor
            record = self._cluster_state.record(node_id)
            specs.append(
                ui_nodes.TrustedNodeSpec(
                    node_id=node_id,
                    display_name=descriptor.display_name,
                    hostname=descriptor.hostname,
                    color=descriptor.color,
                    status=descriptor.status.value,
                    host=record.host if record is not None else descriptor.hostname,
                    port=record.port if record is not None else None,
                    selectable=False,
                    is_manual=True,
                )
            )
        return specs

    def _refresh_nodes_page(self) -> None:
        page = getattr(self, "nodes_page", None)
        if page is None:
            return
        page.set_discovery_enabled(self._cluster_state.discovery_enabled)
        page.refresh_discovered(self._nodes_peer_specs())
        page.refresh_trusted(self._nodes_trusted_specs())
        page.refresh_manual(self._nodes_manual_specs())

    def _nodes_status(self, message: str) -> None:
        page = getattr(self, "nodes_page", None)
        if page is not None:
            self._request_render(
                ui_render.RenderIntent(
                    target="nodes-status",
                    payload=message,
                    payload_set=True,
                    priority=1,
                ),
                lambda intent: page.show_status(cast(str, intent.payload)),
            )

    def _nodes_error(self, message: str) -> None:
        page = getattr(self, "nodes_page", None)
        if page is not None:
            self._request_render(
                ui_render.RenderIntent(
                    target="nodes-status",
                    payload=message,
                    payload_set=True,
                    priority=1,
                ),
                lambda intent: page.show_error(cast(str, intent.payload)),
            )

    def _show_cluster_page(self) -> None:
        self._refresh_cluster_page()
        self._page_router.show(CLUSTER_PAGE)
        self._sync_render_visibility(CLUSTER_PAGE)
        page = getattr(self, "cluster_page", None)
        if page is not None:
            page.focus_back()

    def _build_cluster_page(self, parent: Any) -> Any:
        self.cluster_frame = ttk.Frame(
            parent,
            padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
            style="App.TFrame",
        )
        self.cluster_page = ui_cluster.ClusterPage(
            self.cluster_frame,
            callbacks=ui_cluster.ClusterPageCallbacks(
                on_back=self._show_dashboard_page,
                on_open_node=self._open_cluster_node,
            ),
            nodes=self._cluster_specs(),
            button_coordinator=self._button_coordinator,
        )
        return self.cluster_frame

    def _cluster_specs(self) -> list[ui_cluster.ClusterNodeSpec]:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return []
        selectable = {descriptor.id for descriptor in registry.selectable_descriptors()}
        specs: list[ui_cluster.ClusterNodeSpec] = []
        for context in registry.contexts():
            descriptor = context.descriptor
            last_refresh = None
            snapshot = context.snapshot
            if snapshot is not None:
                last_refresh = snapshot.scanned_at.strftime("%H:%M:%S")
            specs.append(
                ui_cluster.ClusterNodeSpec(
                    node_id=descriptor.id.value,
                    display_name=descriptor.display_name,
                    hostname=descriptor.hostname,
                    color=descriptor.color,
                    trust=descriptor.trust.value,
                    status=descriptor.status.value,
                    capabilities=tuple(
                        sorted(
                            capability.value for capability in descriptor.capabilities
                        )
                    ),
                    is_local=descriptor.is_local,
                    selectable=descriptor.id in selectable,
                    last_refresh=last_refresh,
                )
            )
        for candidate in registry.discovered_candidates():
            specs.append(
                ui_cluster.ClusterNodeSpec(
                    node_id=candidate.stable_id,
                    display_name=candidate.hostname,
                    hostname=candidate.hostname,
                    color=None,
                    trust="untrusted",
                    status="online" if candidate.last_seen else "unknown",
                    capabilities=(),
                    is_local=False,
                    selectable=False,
                )
            )
        return specs

    def _refresh_cluster_page(self) -> None:
        page = getattr(self, "cluster_page", None)
        if page is not None:
            page.refresh_nodes(self._cluster_specs())

    def _save_cluster_state(self, state: ClusterState) -> bool:
        try:
            self._cluster_store.save(state)
        except ClusterSaveError as error:
            LOGGER.warning("Failed to save cluster settings: %s", error)
            return False
        return True

    def _apply_discovery_enabled(self, enabled: bool) -> None:
        candidate = ClusterState(
            discovery_enabled=enabled,
            trusted_nodes=self._cluster_state.trusted_nodes,
        )
        if not self._save_cluster_state(candidate):
            page = getattr(self, "nodes_page", None)
            if page is not None:
                page.set_discovery_enabled(self._cluster_state.discovery_enabled)
                page.show_error("Cluster settings could not be saved")
            return
        self._cluster_state = candidate
        if enabled:
            self._start_discovery()
        else:
            self._stop_discovery()
        self._nodes_status(
            f"Discovery {'enabled' if enabled else 'disabled'} and saved"
        )

    def _pair_discovered_node(self, node_id: str) -> None:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        candidates = {
            candidate.stable_id: candidate
            for candidate in registry.discovered_candidates()
        }
        candidate = candidates.get(node_id)
        if candidate is None:
            self._nodes_error("That peer is no longer visible on the network")
            return
        node = NodeId(node_id)
        try:
            descriptor = registry.promote_to_trusted(
                node, capabilities=READ_CAPABILITIES
            )
        except (KeyError, ValueError) as error:
            self._nodes_error(str(error))
            return
        host = candidate.addresses[0] if candidate.addresses else candidate.hostname
        record = trusted_node_record(
            node_id=node_id,
            display_name=descriptor.display_name,
            hostname=descriptor.hostname,
            host=host,
            platform=descriptor.platform,
            port=candidate.port,
            capabilities=READ_CAPABILITIES,
        )
        state = ClusterState(
            discovery_enabled=self._cluster_state.discovery_enabled,
            trusted_nodes=self._cluster_state.trusted_nodes + (record,),
        )
        if not self._save_cluster_state(state):
            registry.revoke_trusted(node)
            self._nodes_error("Cluster settings could not be saved")
            return
        self._cluster_state = state
        self._refresh_nodes_page()
        self._refresh_cluster_page()
        self._rebuild_node_selector()
        self._nodes_status(f"Paired {descriptor.display_name} (read-only)")

    def _reject_discovered_node(self, node_id: str) -> None:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        registry.reject_discovered(NodeId(node_id))
        ui_discovery_refresh.refresh_discovery_views(
            page=getattr(self, "nodes_page", None),
            peer_specs=self._nodes_peer_specs(),
            trusted_specs=(),
            refresh_trusted=False,
            refresh_cluster_page=self._refresh_cluster_page,
            status_label=getattr(self, "discovery_status_label", None),
            discovered_candidates=registry.discovered_candidates(),
        )
        self._nodes_status(f"Rejected {node_id}")

    def _rename_node(self, node_id: str) -> None:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        current = registry.context(NodeId(node_id)).descriptor.display_name
        name = simpledialog.askstring(
            "Rename Node",
            "Display name:",
            initialvalue=current,
            parent=self.master,
        )
        if not name:
            return
        name = name.strip()
        if not name:
            return
        try:
            descriptor = registry.set_display_name(NodeId(node_id), name)
        except KeyError as error:
            self._nodes_error(str(error))
            return
        records = [
            replace(record, display_name=name) if record.node_id == node_id else record
            for record in self._cluster_state.trusted_nodes
        ]
        state = ClusterState(
            discovery_enabled=self._cluster_state.discovery_enabled,
            trusted_nodes=tuple(records),
        )
        if not self._save_cluster_state(state):
            registry.set_display_name(NodeId(node_id), current)
            self._nodes_error("Cluster settings could not be saved")
            return
        self._cluster_state = state
        self._refresh_nodes_page()
        self._refresh_cluster_page()
        self._rebuild_node_selector()
        self._nodes_status(f"Renamed node to {descriptor.display_name}")

    def _set_node_color(self, node_id: str, color: str) -> None:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        try:
            registry.set_color(NodeId(node_id), color)
        except KeyError as error:
            self._nodes_error(str(error))
            return
        records = [
            replace(record, color=color) if record.node_id == node_id else record
            for record in self._cluster_state.trusted_nodes
        ]
        state = ClusterState(
            discovery_enabled=self._cluster_state.discovery_enabled,
            trusted_nodes=tuple(records),
        )
        if not self._save_cluster_state(state):
            registry.set_color(NodeId(node_id), None)
            self._nodes_error("Cluster settings could not be saved")
            return
        self._cluster_state = state
        self._refresh_nodes_page()
        self._refresh_cluster_page()

    def _revoke_trusted_node(self, node_id: str) -> None:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        node = NodeId(node_id)
        try:
            registry.revoke_trusted(node)
        except (KeyError, ValueError) as error:
            self._nodes_error(str(error))
            return
        state = ClusterState(
            discovery_enabled=self._cluster_state.discovery_enabled,
            trusted_nodes=tuple(
                record
                for record in self._cluster_state.trusted_nodes
                if record.node_id != node_id
            ),
        )
        if not self._save_cluster_state(state):
            self._nodes_error("Cluster settings could not be saved")
            return
        self._cluster_state = state
        getattr(self, "_manual_host_ids", set()).discard(node_id)
        self._refresh_nodes_page()
        self._refresh_cluster_page()
        self._rebuild_node_selector()
        if self.__dict__.get("_selected_node_id") != registry.selected_id():
            self.__dict__["_selected_node_id"] = registry.selected_id()
            context = registry.selected_context()
            self._sync_selected_context_mirrors(context)
            self._render_selected_node(context)
        self._nodes_status("Node removed from trusted machines")

    def _add_manual_host(
        self,
        display_name: str,
        host: str,
        port: int | None,
    ) -> None:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        node_id = f"manual-{host}:{port}" if port is not None else f"manual-{host}"
        node = NodeId(node_id)
        try:
            registry.context(node)
            self._nodes_error("That manual host is already configured")
            return
        except KeyError:
            pass
        descriptor = NodeDescriptor(
            id=node,
            display_name=display_name,
            hostname=host,
            is_local=False,
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.UNKNOWN,
            capabilities=READ_CAPABILITIES,
            platform=None,
            color=None,
        )
        context = NodeContext(
            descriptor=descriptor,
            provider=None,
            process_manager=None,
            file_manager=None,
            scheduler=None,
            coordinator=None,
        )
        record = trusted_node_record(
            node_id=node_id,
            display_name=display_name,
            hostname=host,
            host=host,
            port=port,
            capabilities=READ_CAPABILITIES,
        )
        state = ClusterState(
            discovery_enabled=self._cluster_state.discovery_enabled,
            trusted_nodes=self._cluster_state.trusted_nodes + (record,),
        )
        try:
            registry.register_context(context)
        except ValueError as error:
            self._nodes_error(str(error))
            return
        if not self._save_cluster_state(state):
            registry.revoke_trusted(node)
            self._nodes_error("Cluster settings could not be saved")
            return
        self._cluster_state = state
        manual_ids = getattr(self, "_manual_host_ids", None)
        if manual_ids is None:
            manual_ids = set()
            self._manual_host_ids = manual_ids
        manual_ids.add(node_id)
        self._refresh_nodes_page()
        self._refresh_cluster_page()
        self._nodes_status(f"Configured manual host {display_name}")

    def _remove_manual_host(self, node_id: str) -> None:
        self._revoke_trusted_node(node_id)

    def _test_connection(self, node_id: str) -> None:
        record = self._cluster_state.record(node_id)
        if record is None:
            self._nodes_error("No connection details saved for that node")
            return
        port = record.port
        if port is None:
            self._nodes_error("That node has no authenticated remote port")
            return
        node = NodeId(node_id)

        def task() -> dict[str, Any]:
            provider = AuthenticatedNodeProvider(
                node_id=node,
                secret=record.secret,
                transport=SocketRemoteTransport(record.host, port),
            )
            return provider.hello()

        def on_success(result: dict[str, Any]) -> None:
            version = result.get("app_version") or "peer"
            messagebox.showinfo(
                "Connection OK",
                f"{record.display_name} answered an authenticated hello ({version}).",
                parent=self.master,
            )

        def on_error(message: str) -> None:
            messagebox.showerror(
                "Connection Failed",
                f"Could not reach {record.display_name}: {message}",
                parent=self.master,
            )

        run_in_thread(self.master, task, on_success, on_error)

    def _open_cluster_node(self, node_id: str) -> None:
        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        try:
            registry.context(NodeId(node_id))
        except KeyError:
            return
        self._switch_selected_node(NodeId(node_id))
        self._show_dashboard_page()

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

        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        if node_id == self.__dict__.get("_selected_node_id"):
            return
        old_context = self._selected_context()
        try:
            registry.select(node_id)
        except (KeyError, ValueError):
            LOGGER.warning("Ignoring selection of unavailable node: %s", node_id)
            return
        self.__dict__["_selected_node_id"] = node_id
        context = registry.selected_context()
        self._cancel_active_scan()
        coordinator = self._render_coordinator()
        if coordinator is not None:
            generation = self._scan_coordinator_state().generation
            coordinator.invalidate(DASHBOARD_PAGE, generation, node_id=node_id)
            coordinator.invalidate("scan-status", generation, node_id=node_id)
            coordinator.invalidate("discovery-pages", 0, node_id=node_id)
            coordinator.invalidate(THERMALS_PAGE, 0, node_id=node_id)
            for feature in self._feature_catalog.all():
                coordinator.invalidate(
                    f"component:{feature.key}",
                    0,
                    node_id=node_id,
                )
        self._cancel_node_operations(old_context)
        self._sync_selected_context_mirrors(context)
        self._render_selected_node(context)
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
        self._schedule_timer(0, self.handle_analyze)

    def _cancel_active_scan(self) -> None:
        """Cancel the in-flight full scan so its result cannot land on another node."""

        cancel_event = self.__dict__.get("_analysis_cancel_event")
        if cancel_event is not None:
            cancel_event.set()
        self._analysis_cancel_event = None
        self._scan_coordinator_state().cancel()
        self._cancel_scan_timeout()
        self.__dict__["_timed_out_generation"] = None
        self._cancel_timer(self.__dict__.get("_lease_grace_id"))
        self.__dict__["_lease_grace_id"] = None

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
            node_title_label.config(text=context.descriptor.display_name.upper())
        if snapshot is None:
            self.refreshed_label.config(text="Not refreshed yet")
            self.scan_time_label.config(text="Not scanned yet")
            self.health_label.config(
                text="Health: No issues detected", style="Healthy.TLabel"
            )
            for card in self.cards.values():
                card.reset_summary()
            return
        for resource in snapshot.resources:
            if resource.key in self.cards:
                self.cards[resource.key].update_summary(resource)
        scanned_time = snapshot.scanned_at.strftime("%H:%M:%S")
        self.scan_time_label.config(
            text=f"{snapshot.system_label} • scanned {scanned_time}"
        )
        self.refreshed_label.config(text=f"Last refreshed: {scanned_time}")
        self._refresh_health()

    def _start_discovery(self) -> None:
        """Advertise this node and browse for peers via the shared coordinator.

        Discovery is optional infrastructure: when it is disabled in the
        cluster settings, or the transport is unavailable, or startup fails,
        the app continues as a normal single-node application and the registry
        simply has no discovered candidates.
        """

        registry = self.__dict__.get("_node_registry")
        if registry is None:
            return
        state = self.__dict__.get("_cluster_state")
        if state is not None and not state.discovery_enabled:
            return
        try:
            local_context = registry.context(NodeId(LOCAL_NODE_ID))
        except KeyError:
            return
        descriptor = local_context.descriptor
        advertisement = DiscoveryAdvertisement(
            stable_id=descriptor.id.value,
            display_name=descriptor.display_name,
            hostname=descriptor.hostname,
            app_version=__version__,
            protocol_version=PROTOCOL_VERSION,
            platform=descriptor.platform,
            connectable=False,
            port=None,
        )
        discovery = NetworkDiscovery(
            descriptor.id,
            advertisement=advertisement,
        )
        started = self._coordinator.start_discovery(
            discovery,
            on_candidate=self._on_discovered_candidate,
            on_lost=self._on_discovered_lost,
        )
        if started:
            self._discovery_tick_id = self._schedule_timer(
                int(REAP_TICK_SECONDS * 1000),
                self._tick_discovery,
            )
            self._start_background_poll()

    def _tick_discovery(self) -> None:
        self._discovery_tick_id = None
        if self._is_closing:
            return
        self._coordinator.discovery_tick()
        self._discovery_tick_id = self._schedule_timer(
            int(REAP_TICK_SECONDS * 1000),
            self._tick_discovery,
        )

    def _on_discovered_candidate(self, candidate: Any) -> None:
        if self._is_closing:
            return
        registry = self.__dict__.get("_node_registry")
        trusted_descriptor = None
        trusted_updated = False
        if registry is not None:
            registry.update_discovered(candidate)
            try:
                context = registry.context(NodeId(candidate.stable_id))
            except KeyError:
                context = None
            if context is not None and is_trusted_descriptor(context.descriptor):
                trusted_descriptor = context.descriptor
            trusted_updated = self._sync_trusted_node_endpoint(candidate)
            trusted_specs = self._nodes_trusted_specs() if trusted_descriptor else ()
            self._request_render(
                ui_render.RenderIntent(
                    target="discovery-pages",
                    node_id=self._selected_node_id,
                    components=frozenset({"nodes", "cluster"}),
                    layout_changed=True,
                    payload=(trusted_descriptor, trusted_specs),
                    payload_set=True,
                    priority=2,
                ),
                lambda _intent: ui_discovery_refresh.refresh_discovery_views(
                    page=getattr(self, "nodes_page", None),
                    peer_specs=self._nodes_peer_specs(),
                    trusted_specs=trusted_specs,
                    refresh_trusted=trusted_descriptor is not None,
                    refresh_cluster_page=self._refresh_cluster_page,
                    status_label=getattr(self, "discovery_status_label", None),
                    discovered_candidates=registry.discovered_candidates(),
                ),
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
        self._request_render(
            ui_render.RenderIntent(
                target="discovery-pages",
                node_id=self._selected_node_id,
                components=frozenset({"nodes", "cluster"}),
                layout_changed=True,
                payload=stable_id,
                payload_set=True,
                priority=2,
            ),
            lambda _intent: ui_discovery_refresh.refresh_discovery_views(
                page=getattr(self, "nodes_page", None),
                peer_specs=self._nodes_peer_specs(),
                trusted_specs=(),
                refresh_trusted=trusted_descriptor is not None,
                refresh_cluster_page=self._refresh_cluster_page,
                status_label=getattr(self, "discovery_status_label", None),
                discovered_candidates=registry.discovered_candidates()
                if registry is not None
                else (),
            ),
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
        address = candidate.addresses[0] if candidate.addresses else record.host
        port = candidate.port if candidate.port is not None else record.port
        if address == record.host and port == record.port:
            return False
        if port is None:
            return False
        try:
            provider = AuthenticatedNodeProvider(
                node_id=descriptor.id,
                secret=record.secret,
                transport=SocketRemoteTransport(address, port),
            )
            provider.hello()
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
        )
        if updated_record == record:
            return False
        updated_records = tuple(
            updated_record if item.node_id == record.node_id else item
            for item in state.trusted_nodes
        )
        updated_state = ClusterState(
            discovery_enabled=state.discovery_enabled,
            trusted_nodes=updated_records,
        )
        if not self._save_cluster_state(updated_state):
            self._nodes_error("Cluster settings could not be saved")
            return False
        self._cluster_state = updated_state
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
        self._cancel_timer(self.__dict__.get("_discovery_tick_id"))
        self._discovery_tick_id = None
        coordinator = self.__dict__.get("_coordinator")
        if coordinator is not None:
            coordinator.stop_discovery()

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

        targets: list[tuple[Any, Any]] = [(self.status_label, self.progress_bar)]
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
                scan_status.apply_reset(bar)
                scan_status.apply_scanning(label)

            self._for_each_presentation_target(apply_scanning_state)
        else:

            def apply_ready_state(label: Any, bar: Any) -> None:
                scan_status.apply_ready(label)
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
            lambda label, bar: scan_status.apply_step(
                label,
                bar,
                message,
                count,
                self._progress_total(),
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
        """Run one task off the UI thread and deliver its result or error.

        Shared by the full-scan worker and the per-component workers, so the
        daemon-thread + queue delivery semantics live in one place.
        """

        def worker() -> None:
            try:
                on_success(task())
            except Exception as error:  # noqa: BLE001 - failures reach the queue.
                LOGGER.warning("Background task failed: %s", error)
                on_error(error)
            finally:
                if on_finished is not None:
                    on_finished()

        threading.Thread(target=worker, daemon=True).start()

    def _run_in_background(
        self,
        task: Callable[[], DashboardSnapshot],
        on_success: Callable[[DashboardSnapshot], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        *,
        job_profile: JobProfile | None = None,
        retry_callback: Callable[[], None] | None = None,
        admitted: bool = False,
    ) -> bool:
        governor = self.__dict__.get("_resource_governor")
        decision = (
            governor.admit(job_profile, time.monotonic())
            if governor is not None and job_profile is not None and not admitted
            else None
        )
        if decision is not None and not decision.admitted:
            if (
                retry_callback is not None
                and decision.retry_at is not None
                and not self._is_closing
            ):
                delay = max(0, int((decision.retry_at - time.monotonic()) * 1000))
                self._schedule_timer(delay, retry_callback)
            return False
        self._set_busy(True)
        self._background_tasks += 1
        self._start_background_poll()
        success_callback = on_success or self._show_snapshot
        error_callback = on_error or self._show_error

        def finish_on_ui() -> None:
            if governor is not None and job_profile is not None:
                governor.release(job_profile.key)
            self._background_tasks = max(0, self._background_tasks - 1)
            self._resolve_completed_worker()

        def on_finished() -> None:
            self._background_queue.put(("finished", finish_on_ui))

        try:
            self._run_daemon(
                task,
                lambda result: self._background_queue.put(
                    (success_callback, (result,))
                ),
                lambda error: self._background_queue.put(
                    (error_callback, (str(error),))
                ),
                on_finished=on_finished,
            )
        except RuntimeError as error:
            finish_on_ui()
            error_callback(str(error))
            return False
        return True

    def _submit_ui(self, callback: Callable[[], None]) -> None:
        """Deliver one UI callback through the shared background queue.

        Thread-safe (a plain queue put) and drained on the Tkinter thread by
        ``_drain_background_queue``; worker threads never touch widgets.
        """

        self._background_queue.put(("ui", callback))

    def _start_background_poll(self) -> None:
        # Transport callbacks only enqueue; the UI-owned poll drains discovery too.
        if threading.current_thread() is not threading.main_thread():
            return
        if self._background_poll_id is None and not self._is_closing:
            self._background_poll_id = self._schedule_timer(
                self.BACKGROUND_POLL_MILLISECONDS,
                self._drain_background_queue,
            )

    def _drain_background_queue(self) -> None:
        self._background_poll_id = None

        coordinator = self._render_coordinator()
        if coordinator is not None:
            coordinator.begin_batch()
        try:
            while True:
                try:
                    item = self._background_queue.get_nowait()
                except Empty:
                    break

                if item is None:
                    self._background_tasks = max(0, self._background_tasks - 1)
                    self._resolve_completed_worker()
                    continue

                if isinstance(item, tuple) and len(item) == 2 and item[0] == "finished":
                    self._invoke_delivered(cast(Callable[[], None], item[1]))
                    continue

                if isinstance(item, tuple) and len(item) == 2 and item[0] == "ui":
                    if not self._is_closing:
                        self._invoke_delivered(cast(Callable[[], None], item[1]))
                    continue

                callback, args = cast(
                    tuple[Callable[..., None], tuple[object, ...]],
                    item,
                )
                if not self._is_closing:
                    callback(*args)
        finally:
            if coordinator is not None:
                coordinator.end_batch()

        coordinator = self.__dict__.get("_coordinator")
        pending = coordinator is not None and coordinator.has_pending_work
        if not self._is_closing and (
            self._background_tasks > 0
            or pending
            or self.__dict__.get("_discovery_tick_id") is not None
        ):
            self._start_background_poll()

    @staticmethod
    def _invoke_delivered(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception as error:  # noqa: BLE001 - a dead widget must not kill the drain.
            LOGGER.warning("Dropped UI delivery callback: %s", error)

    def handle_analyze(self) -> None:
        if self._is_closing:
            return
        scan_state = self._scan_coordinator_state()
        if scan_state.active:
            scan_state.begin()
            return
        source_node_id = self.__dict__.get("_selected_node_id")
        source_context = self._selected_context()
        source_provider = (
            source_context.provider if source_context is not None else self.analyzer
        )
        governor = self.__dict__.get("_resource_governor")
        job_profile = JobProfile(
            key=self._operation_key("dashboard"),
            kind="manual",
            node_id=str(source_node_id) if source_node_id is not None else None,
            priority=10,
        )
        admission = (
            governor.admit(job_profile, time.monotonic())
            if governor is not None
            else None
        )
        if admission is not None and not admission.admitted:
            if admission.retry_at is not None and not self._is_closing:
                delay = max(0, int((admission.retry_at - time.monotonic()) * 1000))
                self._schedule_timer(delay, self.handle_analyze)
            return

        generation, started = scan_state.begin()
        if not started:
            if admission is not None and admission.admitted and governor is not None:
                governor.release(job_profile.key)
            return
        coordinator = self._render_coordinator()
        if coordinator is not None:
            coordinator.invalidate("scan-status", generation, node_id=source_node_id)
            coordinator.invalidate(
                "dashboard-snapshot",
                generation,
                node_id=source_node_id,
            )

        cancel_event = threading.Event()
        self._analysis_cancel_event = cancel_event
        self._scan_timeout_id = self._schedule_timer(
            self.SCAN_TIMEOUT_MILLISECONDS,
            self._handle_scan_timeout,
            generation,
        )

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
            return call_legacy_compatible(
                lambda: source_provider.dashboard_snapshot(
                    cancel_event=cancel_event,
                    progress_callback=report_progress,
                ),
                lambda: source_provider.dashboard_snapshot(),
            )

        def queue_snapshot(snapshot: DashboardSnapshot) -> None:
            # Lifecycle completion cannot wait for a hidden page to be rendered.
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
                    payload=snapshot,
                    payload_set=True,
                    priority=3,
                ),
                lambda intent: self._show_snapshot_if_current(
                    generation,
                    cast(DashboardSnapshot, intent.payload),
                    node_id=source_node_id,
                ),
            )
            self._schedule_rerun_if_requested(rerun_requested)

        def queue_error(message: str) -> None:
            self._show_error_for_generation(generation, message, node_id=source_node_id)

        self._run_in_background(
            dashboard_task,
            on_success=queue_snapshot,
            on_error=queue_error,
            job_profile=job_profile,
            retry_callback=self.handle_analyze,
            admitted=True,
        )

    def _claim_scan_resolution(self, generation: int) -> tuple[bool, bool]:
        """Resolve a scan generation once and report its finish state.

        Returns ``(finished, rerun_requested)``; the first resolution of a
        generation wins, so late completions, timeouts, and errors cannot
        double-report the same scan.
        """

        if generation <= self._resolved_scan_generation:
            return False, False
        finished, rerun_requested = self._scan_coordinator_state().finish(generation)
        if not finished:
            return False, False
        self._resolved_scan_generation = generation
        return finished, rerun_requested

    def _handle_scan_timeout(self, generation: int) -> None:
        if self._is_closing:
            return
        if generation != self._scan_coordinator_state().generation:
            return
        if generation <= self._resolved_scan_generation:
            return
        if self.__dict__.get("_timed_out_generation") is not None:
            return
        self._scan_timeout_id = None
        self.__dict__["_timed_out_generation"] = generation
        self.__dict__["_lease_grace_id"] = self._schedule_timer(
            self.SCAN_LEASE_GRACE_MILLISECONDS,
            self._release_lease_after_grace,
            generation,
        )
        cancel_event = self._analysis_cancel_event
        self._analysis_cancel_event = None
        if cancel_event is not None:
            cancel_event.set()
        self._show_error(self.SCAN_TIMEOUT_MESSAGE)

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

        self._resolved_scan_generation = generation
        self.__dict__["_timed_out_generation"] = None
        if cancel_grace_timer:
            self._cancel_timer(self.__dict__.get("_lease_grace_id"))
        self.__dict__["_lease_grace_id"] = None
        finished, rerun_requested = self._scan_coordinator_state().finish(generation)
        if finished:
            self._schedule_rerun_if_requested(rerun_requested)

    def _release_lease_after_grace(self, generation: int) -> None:
        """Force-release a timed-out scan lease after a bounded grace window.

        A genuinely hung worker must not lock the dashboard out of scanning
        forever: after the grace period the lease is released anyway, so the
        rare physical overlap this bounded hold exists to prevent is accepted
        over a permanent lockout.
        """

        if self._is_closing:
            return
        if self.__dict__.get("_timed_out_generation") != generation:
            return
        if generation <= self._resolved_scan_generation:
            return
        self._release_timed_out_lease(
            generation,
            cancel_grace_timer=False,
        )

    def _resolve_completed_worker(self) -> None:
        """Release the timed-out scan lease once its worker actually finishes.

        The timeout only presents the failure; the coordinator lease stays
        held so a new scan cannot physically overlap the old worker. When the
        worker's finish marker arrives the lease is released and any queued
        rerun is honoured.
        """

        if self._is_closing:
            return
        timed_out = self.__dict__.get("_timed_out_generation")
        if timed_out is None:
            return
        if timed_out <= self._resolved_scan_generation:
            return
        self._release_timed_out_lease(
            timed_out,
            cancel_grace_timer=True,
        )

    def _cancel_scan_timeout(self) -> None:
        self._cancel_timer(self._scan_timeout_id)
        self._scan_timeout_id = None

    def _resolve_generation(self, generation: int) -> tuple[bool, bool]:
        """Resolve one scan generation, clearing its timeout and cancel event.

        Returns ``(resolved, rerun_requested)``; when the generation was
        already resolved, nothing is cleared.
        """

        finished, rerun_requested = self._claim_scan_resolution(generation)
        if not finished:
            return False, False
        self._cancel_scan_timeout()
        self._analysis_cancel_event = None
        return True, rerun_requested

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

        if self.__dict__.get("_timed_out_generation") == generation:
            return None
        resolved, rerun_requested = self._resolve_generation(generation)
        if not resolved:
            return None
        return rerun_requested

    def _show_snapshot_for_generation(
        self,
        generation: int,
        snapshot: DashboardSnapshot,
        *,
        node_id: NodeId | None = None,
    ) -> None:
        rerun_requested = self._resolution_for_generation(generation)
        if rerun_requested is None:
            return
        if node_id is None or node_id == self.__dict__.get("_selected_node_id"):
            self._show_snapshot(snapshot)
        self._schedule_rerun_if_requested(rerun_requested)

    def _show_snapshot_if_current(
        self,
        generation: int,
        snapshot: DashboardSnapshot,
        *,
        node_id: NodeId | None = None,
    ) -> None:
        """Commit a resolved snapshot only if its scan and node remain current."""

        if generation != self._scan_coordinator_state().generation:
            return
        if node_id is not None and node_id != self.__dict__.get("_selected_node_id"):
            return
        self._show_snapshot(snapshot)

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

    def _show_snapshot(self, snapshot: DashboardSnapshot) -> None:
        if self._is_closing:
            return

        merged = self._merge_snapshot(snapshot)
        self.snapshot = merged
        context = self._selected_context()
        if context is not None:
            context.snapshot = merged
            context.full_snapshot_applied_at = time.monotonic()
        coordinator = self.__dict__.get("_coordinator")
        if coordinator is not None:
            coordinator.store(self._operation_key("snapshot:dashboard"), merged)
        for resource in snapshot.resources:
            self._observe_capability(resource.key, resource)
            self._record_thermal_summary(resource.key, resource)
        for resource in merged.resources:
            self.cards[resource.key].update_summary(resource)
        self._full_snapshot_applied_at = time.monotonic()

        scanned_time = snapshot.scanned_at.strftime("%H:%M:%S")
        self.scan_time_label.config(
            text=f"{snapshot.system_label} • scanned {scanned_time}"
        )
        self.refreshed_label.config(text=f"Last refreshed: {scanned_time}")
        self._set_busy(False)
        self._for_each_presentation_target(
            lambda label, bar: scan_status.apply_complete(
                label,
                bar,
                self._progress_total(),
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

        return DashboardSnapshot(
            system_label=snapshot.system_label,
            scanned_at=snapshot.scanned_at,
            resources=tuple(
                self._merge_resource(resource.key, resource)
                for resource in snapshot.resources
            ),
        )

    def _merge_resource(
        self,
        key: str,
        resource: ResourceSummary,
    ) -> ResourceSummary:
        """Merge one incoming card against its last valid value."""

        previous = self.snapshot
        prior = (
            next((item for item in previous.resources if item.key == key), None)
            if previous is not None
            else None
        )
        counts = self.__dict__.setdefault("_failed_card_counts", {})

        if not resource.failed:
            counts[key] = 0
            return resource
        if prior is None:
            return resource
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= self.FAILED_CARD_KEEP_LIMIT:
            return resource
        return prior

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
        node_id = context.node_id if context is not None else None
        node_title = (
            context.descriptor.display_name
            if context is not None and self._multi_node_selectable()
            else None
        )
        if feature.action_kind == "process":
            read_only = context is not None and not context.descriptor.has(
                NodeCapability.PROCESS_TERMINATION
            )
            ProcessDialog(
                self.master,
                analyzer=self.analyzer,
                manager=self.process_manager,
                resource_key=resource_key,
                colors=self.colors,
                on_changed=lambda: self._rescan_node_after_change(node_id),
                coordinator=self._coordinator,
                node_id=node_id,
                node_title=node_title,
                read_only=read_only,
            )
        elif feature.action_kind == "storage":
            read_only = context is not None and not context.descriptor.has(
                NodeCapability.CLEANUP
            )
            StorageDialog(
                self.master,
                analyzer=self.analyzer,
                manager=self.file_manager,
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
            has_pending = bool(
                getattr(scheduler, "_refresh_requested", ())
                or getattr(scheduler, "_deferred_until", {})
                or getattr(scheduler, "_in_flight", ())
            )
            if deadline is None:
                return None if has_pending else self.COMPONENT_POLL_MILLISECONDS
            if deadline > now:
                return max(0, int((deadline - now) * 1000))
            return 0 if has_pending else self.COMPONENT_POLL_MILLISECONDS
        if deadline is None:
            return None
        return max(0, int((deadline - now) * 1000))

    def _schedule_component_poll(self, *, force: bool = False) -> None:
        if self._is_closing:
            return
        delay = self._component_poll_delay()
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
        for key in self._component_scheduler.due_keys(time.monotonic()):
            self._launch_component_scan(key)
        self._schedule_component_poll(force=True)

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
        governor = self.__dict__.get("_resource_governor")
        admission = (
            governor.admit(
                JobProfile(
                    key=operation_key,
                    # Card telemetry remains live under pressure; the governor
                    # still applies its active-job and per-node capacity limits.
                    kind="telemetry",
                    node_id=str(source_node_id) if source_node_id is not None else None,
                    priority=1,
                ),
                time.monotonic(),
            )
            if governor is not None
            else None
        )
        if admission is not None and not admission.admitted:
            retry_at = admission.retry_at or (time.monotonic() + 0.5)
            source_scheduler.defer(key, retry_at)
            self._schedule_component_poll(force=True)
            return
        if not source_scheduler.begin(key, time.monotonic()):
            if admission is not None and admission.admitted and governor is not None:
                governor.release(operation_key)
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
            if governor is not None:
                governor.release(operation_key)
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
            if governor is not None:
                governor.release(operation_key)
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
        preferences = self.__dict__.get("_preferences")
        if preferences is None:
            return True
        if key not in preferences.visible_cards:
            return False
        if not preferences.hide_unavailable_cards:
            return True
        capabilities = self.__dict__.get("_capabilities", {})
        return (
            capabilities.get(key, CapabilityState.UNKNOWN)
            != CapabilityState.UNSUPPORTED
        )

    def _polling_policy(self, key: str) -> bool:
        """Return whether periodic polling for one component should pause.

        CPU, Memory and Storage always keep polling because their readings
        feed health warnings. GPU pauses only when automatically hidden by a
        proven-absent capability. Network and Battery pause when manually
        hidden or when proven absent and auto-hiding is enabled.
        """

        preferences = self.__dict__.get("_preferences")
        manually_hidden = (
            preferences is not None and key not in preferences.visible_cards
        )
        capabilities = self.__dict__.get("_capabilities", {})
        auto_hidden = (
            preferences is not None
            and preferences.hide_unavailable_cards
            and capabilities.get(key, CapabilityState.UNKNOWN)
            == CapabilityState.UNSUPPORTED
        )
        if key in ("network", "battery"):
            return manually_hidden or auto_hidden
        if key == "gpu":
            return auto_hidden
        return False

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
        if self.snapshot is None:
            return
        self.snapshot = DashboardSnapshot(
            system_label=self.snapshot.system_label,
            scanned_at=self.snapshot.scanned_at,
            resources=tuple(
                resource if current.key == key else current
                for current in self.snapshot.resources
            ),
        )
        context = self._selected_context()
        if context is not None:
            context.snapshot = self.snapshot

    def _schedule_timer(
        self,
        delay: int,
        callback: Callable[..., None],
        *args: object,
    ) -> str | None:
        if self._is_closing:
            return None

        identifier: str | None = None

        def run_callback() -> None:
            if identifier is not None:
                self._pending_after_ids.discard(identifier)
            if not self._is_closing:
                callback(*args)

        try:
            identifier = self.master.after(delay, run_callback)
        except (RuntimeError, tk.TclError):
            if not self._is_closing:
                LOGGER.exception("Failed to schedule Tkinter work")
            return None

        self._pending_after_ids.add(identifier)
        return identifier

    def _cancel_timer(self, identifier: str | None) -> bool:
        if identifier is None:
            return True

        try:
            self.master.after_cancel(identifier)
        except (RuntimeError, tk.TclError):
            if not self._is_closing:
                LOGGER.exception("Failed to cancel Tkinter work")
            else:
                self._pending_after_ids.discard(identifier)
            return False

        self._pending_after_ids.discard(identifier)
        return True

    def _cancel_pending_timers(self) -> None:
        for identifier in tuple(self._pending_after_ids):
            self._cancel_timer(identifier)

    def _finalize_shutdown(self) -> None:
        """Release the scan lease and cancel every pending timer.

        Shared by the window's Close path and ``run()``'s ``finally`` so the
        two termination paths can never drift apart. Statement order is
        deliberate and preserved: the coordinator lease and per-path state are
        cleared, then all pending Tk timers are cancelled before the master is
        torn down. Discovery is stopped first so no late network event can
        reach a dying UI.
        """

        self._stop_discovery()
        self._scan_coordinator_state().cancel()
        self.__dict__["_timed_out_generation"] = None
        self.__dict__["_lease_grace_id"] = None
        coordinator = self.__dict__.get("_coordinator")
        if coordinator is not None:
            coordinator.cancel_all()
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
            lambda _label, bar: scan_status.apply_reset(bar)
        )

    def run(self) -> None:
        try:
            self.master.mainloop()
        finally:
            self._is_closing = True
            self._finalize_shutdown()
