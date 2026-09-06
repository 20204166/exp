import logging
import threading
import time
import tkinter as tk
from collections.abc import Callable
from queue import Empty, Queue
from tkinter import messagebox, ttk
from typing import Any, cast

import algo
from maintenance.actions import FileManager, ProcessManager
from maintenance.components import (
    DOWNLOADS_SCAN_CANCELLED,
    ResourceFeatureCatalog,
    ScanCoordinator,
)
from maintenance.components.coordinator import (
    AppCoordinator,
    ComponentRefreshScheduler,
)
from maintenance.components.scan_support import (
    SCAN_CANCELLED_NOTICE,
    call_legacy_compatible,
)
from maintenance.dialogs import (
    InfoDialog,
    ProcessDialog,
    ResourceCard,
    StorageDialog,
)
from maintenance.health import health_warnings
from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    ResourceSummary,
    unavailable_summary,
)
from maintenance.preferences import (
    INTERVAL_POLICIES,
    AppPreferences,
    PreferencesSaveError,
    PreferencesStore,
    default_preferences_path,
)
from maintenance.ui import layout as ui_layout
from maintenance.ui import preferences_page as ui_preferences
from maintenance.ui import scan_status
from maintenance.ui import settings_home as ui_settings_home
from maintenance.ui import styles as ui_styles
from maintenance.ui import transition as ui_transition
from maintenance.ui.navigation import PageRouter, PageSpec

LOGGER = logging.getLogger(__name__)

DASHBOARD_PAGE = "dashboard"
SETTINGS_PAGE = "settings"
PREFERENCES_PAGE = "preferences"


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
    ) -> None:
        self.analyzer = algo.Analyzer(memory_test_percent=1.0)
        self.process_manager = ProcessManager()
        self.file_manager = FileManager(self.analyzer.scanner.downloads_path)
        self._preferences_store = preferences_store or PreferencesStore(
            default_preferences_path()
        )
        self._preferences = self._preferences_store.load()
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
        self._component_scheduler = ComponentRefreshScheduler(
            self._preferences.refresh_intervals.as_dict()
        )
        self._feature_catalog = ResourceFeatureCatalog()
        self._component_poll_id: str | None = None
        self._capabilities: dict[str, CapabilityState] = {}

        self.master = master or tk.Tk()
        self.master.title("System Analyzer")
        self.master.geometry("1040x760")
        self.master.minsize(900, 680)
        self.master.configure(bg=self.BACKGROUND)
        self.master.protocol("WM_DELETE_WINDOW", self._close)

        self._configure_styles()
        self._build_window()
        self._schedule_timer(350, self.handle_analyze)

    @property
    def colors(self) -> dict[str, str]:
        return {
            "background": self.BACKGROUND,
            "card": self.CARD_BACKGROUND,
            "text": self.TEXT_PRIMARY,
            "secondary": self.TEXT_SECONDARY,
            "accent": self.ACCENT,
            "border": self.BORDER,
        }

    def _scan_coordinator_state(self) -> ScanCoordinator:
        coordinator = self.__dict__.get("_scan_coordinator")
        if coordinator is None:
            coordinator = ScanCoordinator()
            self.__dict__["_scan_coordinator"] = coordinator
        return coordinator

    def _build_window(self) -> None:
        self._page_router = PageRouter(self.master)
        self._page_router.register(PageSpec(DASHBOARD_PAGE, self._build_dashboard_page))
        self._page_router.register(
            PageSpec(SETTINGS_PAGE, self._build_settings_home_page)
        )
        self._page_router.register(
            PageSpec(PREFERENCES_PAGE, self._build_preferences_page)
        )
        self._page_router.show(DASHBOARD_PAGE)
        self._reconcile_cards_and_polling()

    def _build_dashboard_page(self, parent: Any) -> Any:
        self.main_frame = ttk.Frame(
            parent,
            padding=(30, 26),
            style="App.TFrame",
        )

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
        )

        self.settings_button = ttk.Button(
            self.header_actions,
            text="Settings",
            command=self._show_settings_page,
            style="Neutral.TButton",
            cursor="hand2",
        )
        self.settings_button.pack(anchor="e")

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
            card = ResourceCard(
                self.cards_frame,
                key=feature.key,
                title=feature.title,
                on_open=self.open_resource,
                colors=self.colors,
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
            padding=(30, 26),
            style="App.TFrame",
        )
        self.settings_home = ui_settings_home.SettingsHome(
            self.settings_frame,
            callbacks=ui_settings_home.SettingsHomeCallbacks(
                on_back=self._show_dashboard_page,
                on_select_category=self._on_select_settings_category,
            ),
            categories=self._settings_categories(),
        )
        return self.settings_frame

    def _settings_categories(self) -> list[ui_settings_home.SettingsCategorySpec]:
        return [
            ui_settings_home.SettingsCategorySpec(
                key="preferences",
                title="Preferences",
                description=(
                    "Refresh intervals, visible dashboard cards, scan "
                    "behaviour, and interface options."
                ),
            )
        ]

    def _build_preferences_page(self, parent: Any) -> Any:
        self.preferences_frame = ttk.Frame(
            parent,
            padding=(30, 26),
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
            ),
            intervals=self._interval_specs(),
            cards=self._card_specs(),
            hide_unavailable_cards=self._preferences.hide_unavailable_cards,
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
        self.settings_home.focus_back()

    def _show_preferences_page(self) -> None:
        self._page_router.show(PREFERENCES_PAGE)
        self.preferences_page.focus_back()

    def _show_dashboard_page(self) -> None:
        self._page_router.show(DASHBOARD_PAGE)
        button = getattr(self, "settings_button", None)
        if button is not None:
            button.focus_set()

    def _on_select_settings_category(self, key: str) -> None:
        """Route one Settings category card to its dedicated page.

        Unknown keys are ignored defensively so adding a category later is a
        matter of registering its page and a handler here.
        """

        handlers = {
            "preferences": self._show_preferences_page,
        }
        handler = handlers.get(key)
        if handler is not None:
            handler()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.master)
        style.theme_use("clam")
        ui_styles.configure_app_styles(style)

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

    def _set_busy(self, is_busy: bool) -> None:
        self.analyze_button.config(state=tk.DISABLED if is_busy else tk.NORMAL)
        self.cancel_button.config(state=tk.NORMAL if is_busy else tk.DISABLED)

        if is_busy:
            self.__dict__["_scan_progress_count"] = 0
            self._completion_transition().cancel()
            for label, bar in self._presentation_targets():
                scan_status.apply_reset(bar)
                scan_status.apply_scanning(label)
        else:
            for label, bar in self._presentation_targets():
                scan_status.apply_ready(label)
                bar.stop()

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
        for label, _bar in self._presentation_targets():
            scan_status.apply_cancelling(label)

    def _show_progress(self, message: str) -> None:
        if self._is_closing:
            return
        count = self.__dict__.get("_scan_progress_count", 0) + 1
        self.__dict__["_scan_progress_count"] = count
        for label, bar in self._presentation_targets():
            scan_status.apply_step(
                label,
                bar,
                message,
                count,
                self._progress_total(),
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
    ) -> None:
        self._set_busy(True)
        self._background_tasks += 1
        self._start_background_poll()
        success_callback = on_success or self._show_snapshot
        error_callback = on_error or self._show_error

        self._run_daemon(
            task,
            lambda result: self._background_queue.put((success_callback, (result,))),
            lambda error: self._background_queue.put((error_callback, (str(error),))),
            on_finished=lambda: self._background_queue.put(None),
        )

    def _submit_ui(self, callback: Callable[[], None]) -> None:
        """Deliver one UI callback through the shared background queue.

        Thread-safe (a plain queue put) and drained on the Tkinter thread by
        ``_drain_background_queue``; worker threads never touch widgets.
        """

        self._background_queue.put(("ui", callback))

    def _start_background_poll(self) -> None:
        if self._background_poll_id is None and not self._is_closing:
            self._background_poll_id = self._schedule_timer(
                self.BACKGROUND_POLL_MILLISECONDS,
                self._drain_background_queue,
            )

    def _drain_background_queue(self) -> None:
        self._background_poll_id = None

        while True:
            try:
                item = self._background_queue.get_nowait()
            except Empty:
                break

            if item is None:
                self._background_tasks = max(0, self._background_tasks - 1)
                self._resolve_completed_worker()
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

        coordinator = self.__dict__.get("_coordinator")
        pending = coordinator is not None and coordinator.has_pending_work
        if not self._is_closing and (self._background_tasks > 0 or pending):
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
        generation, started = self._scan_coordinator_state().begin()
        if not started:
            return

        cancel_event = threading.Event()
        self._analysis_cancel_event = cancel_event
        self._scan_timeout_id = self._schedule_timer(
            self.SCAN_TIMEOUT_MILLISECONDS,
            self._handle_scan_timeout,
            generation,
        )

        def report_progress(message: str) -> None:
            self._background_queue.put((self._show_progress, (message,)))

        def dashboard_task() -> DashboardSnapshot:
            return call_legacy_compatible(
                lambda: self.analyzer.dashboard_snapshot(
                    cancel_event=cancel_event,
                    progress_callback=report_progress,
                ),
                lambda: self.analyzer.dashboard_snapshot(),
            )

        self._run_in_background(
            dashboard_task,
            on_success=lambda snapshot: self._show_snapshot_for_generation(
                generation,
                snapshot,
            ),
            on_error=lambda message: self._show_error_for_generation(
                generation,
                message,
            ),
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
    ) -> None:
        rerun_requested = self._resolution_for_generation(generation)
        if rerun_requested is None:
            return
        self._show_snapshot(snapshot)
        self._schedule_rerun_if_requested(rerun_requested)

    def _show_error_for_generation(self, generation: int, message: str) -> None:
        rerun_requested = self._resolution_for_generation(generation)
        if rerun_requested is None:
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
        coordinator = self.__dict__.get("_coordinator")
        if coordinator is not None:
            coordinator.store("snapshot:dashboard", merged)
        for resource in snapshot.resources:
            self._observe_capability(resource.key, resource)
        for resource in merged.resources:
            self.cards[resource.key].update_summary(resource)
        self._full_snapshot_applied_at = time.monotonic()

        scanned_time = snapshot.scanned_at.strftime("%H:%M:%S")
        self.scan_time_label.config(
            text=f"{snapshot.system_label} • scanned {scanned_time}"
        )
        self.refreshed_label.config(text=f"Last refreshed: {scanned_time}")
        self._set_busy(False)
        for label, bar in self._presentation_targets():
            scan_status.apply_complete(
                label,
                bar,
                self._progress_total(),
            )
        self._completion_transition().start(
            self.COMPLETION_HOLD_MILLISECONDS,
            self._show_ready_after_completion_hold,
        )
        self._refresh_health()
        self._component_scheduler.mark_all_refreshed(time.monotonic())
        self._schedule_component_poll()

    def _show_ready_after_completion_hold(self) -> None:
        """Return the status to Ready after the completion hold expires.

        The progress bar itself stays full until the next scan starts, so a
        finished scan remains visibly distinct from a frozen partial bar.
        """

        if self._is_closing:
            return
        if self._scan_coordinator_state().active:
            return
        for label, _bar in self._presentation_targets():
            scan_status.apply_ready(label)

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
        if feature.action_kind == "process":
            ProcessDialog(
                self.master,
                analyzer=self.analyzer,
                manager=self.process_manager,
                resource_key=resource_key,
                colors=self.colors,
                on_changed=self._rescan_after_change,
                coordinator=self._coordinator,
            )
        elif feature.action_kind == "storage":
            StorageDialog(
                self.master,
                analyzer=self.analyzer,
                manager=self.file_manager,
                colors=self.colors,
                on_changed=self._rescan_after_change,
                coordinator=self._coordinator,
            )
        else:
            InfoDialog(self.master, summary=summary, colors=self.colors)

    def _rescan_after_change(self) -> None:
        self._schedule_timer(500, self.handle_analyze)

    def _schedule_component_poll(self) -> None:
        if self._component_poll_id is None and not self._is_closing:
            self._component_poll_id = self._schedule_timer(
                self.COMPONENT_POLL_MILLISECONDS,
                self._run_component_cycle,
            )

    def _run_component_cycle(self) -> None:
        self._component_poll_id = None
        if self._is_closing:
            return
        for key in self._component_scheduler.due_keys(time.monotonic()):
            self._launch_component_scan(key)
        self._schedule_component_poll()

    def _launch_component_scan(self, key: str) -> None:
        if not self._component_scheduler.begin(key, time.monotonic()):
            return

        started_at = time.monotonic()

        def task_factory(
            _cancel_event: threading.Event,
            _progress: Callable[[str], None],
        ) -> ResourceSummary:
            return self.analyzer.component_summary(key)

        self._coordinator.run(
            f"component:{key}",
            task_factory,
            on_result=lambda _operation, resource: self._queue_component_result(
                key,
                started_at,
                resource,
            ),
            on_error=lambda _operation, message: self._queue_component_result(
                key,
                started_at,
                RuntimeError(message),
            ),
        )

    def _queue_component_result(
        self,
        key: str,
        started_at: float,
        value: ResourceSummary | Exception,
    ) -> None:
        """Apply one component scan result delivered on the Tkinter thread."""

        self._component_scheduler.finish(key)
        applied_at = self.__dict__.get("_full_snapshot_applied_at")
        if applied_at is not None and started_at < applied_at:
            return
        if isinstance(value, Exception):
            resource = self._failed_component_summary(key)
        else:
            resource = value
        self._apply_component(key, resource)

    def _failed_component_summary(self, key: str) -> ResourceSummary:
        title = self._fallback_component_title(key)
        return unavailable_summary(key, title)

    def _fallback_component_title(self, key: str) -> str:
        """Return one card title from the feature catalog, falling back to key."""

        return self._feature_catalog.title_for(key) or key

    def _apply_component(self, key: str, resource: ResourceSummary) -> None:
        if self._is_closing:
            return
        self._observe_capability(key, resource)
        displayed = self._merge_resource(key, resource)
        coordinator = self.__dict__.get("_coordinator")
        if coordinator is not None:
            coordinator.store(f"component:{key}", displayed)
        if key in self.cards:
            self.cards[key].update_summary(displayed)
        self._update_snapshot_resource(key, displayed)
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
        self._schedule_component_poll()

    def _reconcile_intervals(self) -> None:
        now = time.monotonic()
        current = self._component_scheduler.intervals
        for key, milliseconds in self._preferences.refresh_intervals.as_dict().items():
            if current.get(key) != milliseconds:
                self._component_scheduler.set_interval(key, milliseconds, now)

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
        self.preferences_page.refresh_from(self._preferences)
        self.preferences_page.show_status("Preferences saved")

    def _on_interval_commit(self, key: str, seconds: int) -> None:
        try:
            candidate = self._preferences.with_interval(key, seconds * 1000)
        except ValueError as error:
            self.preferences_page.refresh_from(self._preferences)
            self.preferences_page.show_error(str(error))
            return
        self._apply_preferences(candidate)

    def _on_card_visibility_change(self, key: str, visible: bool) -> None:
        try:
            candidate = self._preferences.with_card_visibility(key, visible)
        except ValueError as error:
            self.preferences_page.refresh_from(self._preferences)
            self.preferences_page.show_error(str(error))
            return
        self._apply_preferences(candidate)
        if visible:
            self._request_component_refresh(key)

    def _on_auto_hide_change(self, enabled: bool) -> None:
        self._apply_preferences(self._preferences.with_hide_unavailable_cards(enabled))

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
        torn down.
        """

        self._scan_coordinator_state().cancel()
        self.__dict__["_timed_out_generation"] = None
        self.__dict__["_lease_grace_id"] = None
        self._cancel_pending_timers()
        self._component_poll_id = None
        self._background_poll_id = None
        self._scan_timeout_id = None

    def _close(self) -> None:
        self._is_closing = True
        self._finalize_shutdown()
        if self._analysis_cancel_event is not None:
            self._analysis_cancel_event.set()
        self._analysis_cancel_event = None
        analyzer = getattr(self, "analyzer", None)
        stop_workers = getattr(analyzer, "stop_background_workers", None)
        if stop_workers is not None:
            stop_workers()
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
        for _label, bar in self._presentation_targets():
            scan_status.apply_reset(bar)

    def run(self) -> None:
        try:
            self.master.mainloop()
        finally:
            self._is_closing = True
            self._finalize_shutdown()
