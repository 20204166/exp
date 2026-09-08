"""Reusable Preferences page adapter for the System Analyzer UI.

This module owns only the Preferences page's presentation and page-local
behaviour: widget construction, Tk variables, interval commit validation,
card checkboxes, the Manual Scan controls, and the preferences status line.

It never imports the window, scanners, managers, or the preferences store.
The controller supplies typed callbacks and initial values (dependency-style
composition) and maps page events to application behaviour; ``refresh_from``
accepts any object exposing ``refresh_intervals.as_dict()``,
``visible_cards`` and ``hide_unavailable_cards`` so the page stays decoupled
from the preferences model.
"""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.ui import layout as ui_layout
from maintenance.ui import scan_status
from maintenance.ui import styles as ui_styles
from maintenance.ui.action_coordinator import ButtonCoordinator

_SECONDS_UNIT = "seconds"


@dataclass(frozen=True, slots=True)
class PreferencesPageCallbacks:
    """The semantic events the Preferences page can emit.

    The controller wires these to persistence, scheduling and navigation;
    the page never decides what they do.
    """

    on_back: Callable[[], None]
    on_interval_commit: Callable[[str, int], None]
    on_card_visibility_change: Callable[[str, bool], None]
    on_auto_hide_change: Callable[[bool], None]
    on_scan: Callable[[], None]
    on_cancel_scan: Callable[[], None]
    on_reset: Callable[[], None]
    on_appearance_change: Callable[[str], None] | None = None


@dataclass(frozen=True, slots=True)
class IntervalControlSpec:
    """Presentation data for one interval Spinbox (values in whole seconds)."""

    key: str
    title: str
    seconds: int
    minimum_seconds: int
    maximum_seconds: int
    step_seconds: int


@dataclass(frozen=True, slots=True)
class CardControlSpec:
    """Presentation data for one card visibility Checkbutton."""

    key: str
    title: str
    enabled: bool


class PreferencesPage:
    """Build and own the Preferences page content inside the given page root.

    The page root is provided by the caller (an ``AppWindow`` page frame) and
    is never packed by this class; the page router controls page visibility.
    All widget classes are injectable so tests can run headlessly.
    """

    def __init__(
        self,
        parent: Any,
        *,
        callbacks: PreferencesPageCallbacks,
        intervals: list[IntervalControlSpec],
        cards: list[CardControlSpec],
        hide_unavailable_cards: bool,
        appearance: str = ui_styles.DEFAULT_APPEARANCE,
        appearance_options: tuple[str, ...] | None = None,
        frame_cls: Callable[..., Any] = tk.Frame,
        label_cls: Callable[..., Any] = tk.Label,
        style_frame_cls: Callable[..., Any] = ttk.Frame,
        style_label_cls: Callable[..., Any] = ttk.Label,
        button_cls: Callable[..., Any] = ttk.Button,
        canvas_cls: Callable[..., Any] = tk.Canvas,
        scrollbar_cls: Callable[..., Any] = ttk.Scrollbar,
        spinbox_cls: Callable[..., Any] = ttk.Spinbox,
        checkbutton_cls: Callable[..., Any] = ttk.Checkbutton,
        combobox_cls: Callable[..., Any] = ttk.Combobox,
        progressbar_cls: Callable[..., Any] = ttk.Progressbar,
        var_factory: Callable[[], Any] | None = None,
        boolean_var_factory: Callable[[], Any] | None = None,
        button_coordinator: ButtonCoordinator | None = None,
        colors: dict[str, str] | None = None,
        fonts: dict[str, Any] | None = None,
    ) -> None:
        self.callbacks = callbacks
        self.colors = ui_styles.COLORS if colors is None else colors
        self.fonts = ui_styles.FONTS if fonts is None else fonts
        self._intervals = {spec.key: spec for spec in intervals}
        self._cards = {spec.key: spec for spec in cards}
        self._var_factory = var_factory or (lambda: tk.StringVar())
        self._boolean_var_factory = boolean_var_factory or (lambda: tk.BooleanVar())
        self._updating = False
        self._appearance = appearance
        self._appearance_options = appearance_options or tuple(
            sorted(ui_styles.ACCENT_THEMES)
        )
        self._button_coordinator = button_coordinator

        self.frame_cls = frame_cls
        self.label_cls = label_cls
        self.style_frame_cls = style_frame_cls
        self.style_label_cls = style_label_cls
        self.button_cls = button_cls
        self.canvas_cls = canvas_cls
        self.scrollbar_cls = scrollbar_cls
        self.spinbox_cls = spinbox_cls
        self.checkbutton_cls = checkbutton_cls
        self.combobox_cls = combobox_cls
        self.progressbar_cls = progressbar_cls

        self._interval_vars: dict[str, Any] = {}
        self._interval_committed: dict[str, int] = {}
        self._card_vars: dict[str, Any] = {}

        self._build(parent, hide_unavailable_cards)

    def _build(self, parent: Any, hide_unavailable_cards: bool) -> None:
        (
            self.back_button,
            self.canvas,
            self.content,
            self._refresh_scrollbar,
        ) = ui_layout.page_shell(
            parent,
            title="Preferences",
            description=(
                "Configure how System Analyzer refreshes components, shows "
                "cards, and scans on demand."
            ),
            back_text="Back to Settings",
            on_back=self.callbacks.on_back,
            style_frame_cls=self.style_frame_cls,
            style_label_cls=self.style_label_cls,
            button_cls=self.button_cls,
            canvas_cls=self.canvas_cls,
            scrollbar_cls=self.scrollbar_cls,
            colors=self.colors,
        )

        self._build_scanning_section()
        self._build_cards_section()
        self._build_manual_scan_section()
        self._build_interface_section(hide_unavailable_cards)
        self._build_reset()

        self.status_label = ui_layout.page_status(
            parent,
            "",
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
        )

    def _build_scanning_section(self) -> None:
        _, body = ui_layout.section_card(
            self.content,
            "Scanning",
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            description=(
                "How often each live component refreshes while the dashboard "
                "is open. Values are shown in seconds."
            ),
        )
        for spec in self._intervals.values():
            self._build_interval_row(body, spec)

    def _build_interval_row(self, body: Any, spec: IntervalControlSpec) -> None:
        var = self._var_factory()
        var.set(str(spec.seconds))
        self._interval_vars[spec.key] = var
        self._interval_committed[spec.key] = spec.seconds

        def control_factory(row: Any) -> Any:
            holder = self.frame_cls(row, bg=self.colors["card"])
            holder.pack(side="right")
            spin = self.spinbox_cls(
                holder,
                from_=spec.minimum_seconds,
                to=spec.maximum_seconds,
                increment=spec.step_seconds,
                textvariable=var,
                width=6,
                justify="right",
                style="App.TSpinbox",
                command=lambda: self._commit_interval(spec.key),
            )
            spin.pack(side="left")
            unit = self.label_cls(
                holder,
                text=_SECONDS_UNIT,
                bg=self.colors["card"],
                fg=self.colors["secondary"],
                font=self.fonts["body"],
            )
            unit.pack(side="left", padx=(6, 0))
            spin.bind("<Return>", lambda _event: self._commit_interval(spec.key))
            spin.bind("<FocusOut>", lambda _event: self._commit_interval(spec.key))
            return holder

        ui_layout.setting_row(
            body,
            spec.title,
            control_factory,
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
        )

    def _commit_interval(self, key: str) -> None:
        if self._updating:
            return
        spec = self._intervals[key]
        raw = self._interval_vars[key].get()
        try:
            seconds = int(raw)
        except (TypeError, ValueError):
            self._restore_interval(key)
            self.show_error(f"{spec.title} must be a whole number of seconds")
            return
        if not spec.minimum_seconds <= seconds <= spec.maximum_seconds:
            self._restore_interval(key)
            self.show_error(
                f"{spec.title} refresh must be "
                f"{spec.minimum_seconds}-{spec.maximum_seconds} seconds"
            )
            return
        self._interval_committed[key] = seconds
        self.callbacks.on_interval_commit(key, seconds)

    def _restore_interval(self, key: str) -> None:
        self._interval_vars[key].set(str(self._interval_committed[key]))

    def _build_cards_section(self) -> None:
        _, body = ui_layout.section_card(
            self.content,
            "Dashboard Cards",
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            description=(
                "Choose which cards appear on the overview. Cards you hide "
                "here stay hidden; automatic unavailable-card hiding only "
                "applies to hardware proven absent."
            ),
        )
        for spec in self._cards.values():
            var = self._boolean_var_factory()
            var.set(spec.enabled)
            self._card_vars[spec.key] = var

            def toggle_card(key: str = spec.key) -> None:
                self._on_card_toggle(key)

            ui_layout.boolean_setting_row(
                body,
                spec.title,
                variable=var,
                control_text="Show card",
                on_change=toggle_card,
                action_id=f"preferences:card:{spec.key}:visibility",
                button_coordinator=self._button_coordinator,
                frame_cls=self.frame_cls,
                label_cls=self.label_cls,
                checkbutton_cls=self.checkbutton_cls,
                colors=self.colors,
                fonts=self.fonts,
            )

    def _on_card_toggle(self, key: str) -> None:
        if self._updating:
            return
        self.callbacks.on_card_visibility_change(key, self._card_vars[key].get())

    def _build_manual_scan_section(self) -> None:
        _, body = ui_layout.section_card(
            self.content,
            "Manual Scan",
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            description=(
                "Run a full system scan on demand. Scan state stays visible "
                "here and on the dashboard."
            ),
        )
        actions = self.frame_cls(body, bg=self.colors["card"])
        actions.pack(fill="x")
        self.cancel_button = self.button_cls(
            actions,
            text="Cancel",
            command=self.callbacks.on_cancel_scan,
            style="Danger.TButton",
            state=tk.DISABLED,
        )
        self.cancel_button.pack(side="right")
        self.analyze_button = self.button_cls(
            actions,
            text="Scan System",
            command=self.callbacks.on_scan,
            style="Primary.TButton",
            cursor="hand2",
        )
        self.analyze_button.pack(side="right", padx=(0, 10))
        if self._button_coordinator is not None:
            self._button_coordinator.register(
                "preferences:scan",
                self.callbacks.on_scan,
                replace=True,
            )
            self._button_coordinator.bind(self.analyze_button, "preferences:scan")
            self._button_coordinator.register(
                "preferences:cancel-scan",
                self.callbacks.on_cancel_scan,
                enabled=False,
                replace=True,
            )
            self._button_coordinator.bind(
                self.cancel_button,
                "preferences:cancel-scan",
            )
        self.manual_status_label = self.style_label_cls(
            body,
            text=scan_status.READY_TEXT,
            style=scan_status.READY_STYLE,
        )
        self.manual_status_label.pack(anchor="w", pady=(12, 0))
        self.manual_progress_bar = self.progressbar_cls(
            body,
            mode="determinate",
            maximum=6,
            style=scan_status.ANALYSIS_BAR_STYLE,
        )
        self.manual_progress_bar.pack(fill="x", pady=(10, 0))

    def _build_interface_section(self, hide_unavailable_cards: bool) -> None:
        _, body = ui_layout.section_card(
            self.content,
            "Interface",
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            description="Interface behaviour and automatic layout options.",
        )
        var = self._boolean_var_factory()
        var.set(hide_unavailable_cards)
        self._auto_hide_var = var

        ui_layout.boolean_setting_row(
            body,
            "Hide unavailable cards automatically",
            variable=var,
            control_text="Enabled",
            on_change=lambda: self.callbacks.on_auto_hide_change(var.get()),
            action_id="preferences:auto-hide",
            button_coordinator=self._button_coordinator,
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            checkbutton_cls=self.checkbutton_cls,
            colors=self.colors,
            fonts=self.fonts,
            help_text=(
                "Hides cards for hardware proven absent (for example Battery "
                "on a desktop). A transient scan failure never hides a card."
            ),
        )

        appearance_var = self._var_factory()
        appearance_var.set(self._appearance)
        self._appearance_var = appearance_var

        def appearance_factory(row: Any) -> Any:
            holder = self.frame_cls(row, bg=self.colors["card"])
            holder.pack(side="right")
            combo = self.combobox_cls(
                holder,
                textvariable=appearance_var,
                state="readonly",
                values=list(self._appearance_options),
                width=12,
                style="App.TSpinbox",
            )
            combo.pack(side="left")
            return holder

        ui_layout.setting_row(
            body,
            "Accent theme",
            appearance_factory,
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            help_text=(
                "Changes the accent colour used for buttons, progress bars "
                "and the dashboard cards."
            ),
        )
        appearance_var.trace_add(
            "write",
            lambda *_args: self._on_appearance_change(),
        )

    def _on_appearance_change(self) -> None:
        if self._updating:
            return
        callback = self.callbacks.on_appearance_change
        if callback is None:
            return
        var = getattr(self, "_appearance_var", None)
        if var is not None:
            callback(var.get())

    def _build_reset(self) -> None:
        reset_row = self.frame_cls(self.content, bg=self.colors["background"])
        reset_row.pack(fill="x", pady=(4, 0))
        self.reset_button = self.button_cls(
            reset_row,
            text="Reset Preferences to Defaults",
            command=self.callbacks.on_reset,
            style="Neutral.TButton",
        )
        self.reset_button.pack(anchor="w")
        if self._button_coordinator is not None:
            self._button_coordinator.register(
                "preferences:reset",
                self.callbacks.on_reset,
                replace=True,
            )
            self._button_coordinator.bind(self.reset_button, "preferences:reset")

    def show_status(self, message: str) -> None:
        self.status_label.config(text=message, fg=self.colors["secondary"])

    def show_error(self, message: str) -> None:
        self.status_label.config(text=message, fg=self.colors["danger"])

    def refresh_from(self, preferences: Any) -> None:
        """Synchronise every control from a preferences-like object.

        Accepts anything exposing ``refresh_intervals.as_dict()``,
        ``visible_cards`` and ``hide_unavailable_cards`` so the page does not
        import the preferences model. Callbacks are suppressed while values
        are being written.
        """

        self._updating = True
        try:
            for key, milliseconds in preferences.refresh_intervals.as_dict().items():
                var = self._interval_vars.get(key)
                if var is None:
                    continue
                seconds = milliseconds // 1000
                var.set(str(seconds))
                self._interval_committed[key] = seconds
            for key, var in self._card_vars.items():
                var.set(key in preferences.visible_cards)
            self._auto_hide_var.set(preferences.hide_unavailable_cards)
            appearance = getattr(preferences, "appearance", self._appearance)
            var = getattr(self, "_appearance_var", None)
            if var is not None:
                var.set(appearance)
        finally:
            self._updating = False

    def focus_back(self) -> None:
        self.back_button.focus_set()

    def scroll_to_top(self) -> None:
        """Return the scrolling body to its top (the Preferences anchor)."""

        try:
            self.canvas.yview_moveto(0.0)
        except AttributeError:
            pass
