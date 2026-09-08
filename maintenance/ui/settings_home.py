"""Reusable Settings category hub page for the System Analyzer UI.

The Settings page is the expandable category hub: a lightweight landing page
that lists one navigation card per available settings category. The page owns
only presentation and page-local behaviour (widget construction, category
cards, the back control); it never imports the window, scanners, managers, or
the preferences store. The controller supplies typed callbacks and category
specs (dependency-style composition), so adding a future category means one
more ``SettingsCategorySpec`` plus its page and navigation hook — nothing in
this module changes.
"""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.action_coordinator import ButtonCoordinator

_CARD_WRAP = 560


@dataclass(frozen=True, slots=True)
class SettingsHomeCallbacks:
    """The semantic events the Settings home page can emit.

    The controller wires these to page navigation; the page never decides
    where a category leads.
    """

    on_back: Callable[[], None]
    on_select_category: Callable[[str], None]
    on_start_discovery: Callable[[], None] = lambda: None


@dataclass(frozen=True, slots=True)
class SettingsCategorySpec:
    """Presentation data for one navigation card on the Settings hub."""

    key: str
    title: str
    description: str


class SettingsHome:
    """Build and own the Settings category hub inside the given page root.

    The page root is provided by the caller (an ``AppWindow`` page frame) and
    is never packed by this class; the page router controls page visibility.
    All widget classes are injectable so tests can run headlessly.
    """

    def __init__(
        self,
        parent: Any,
        *,
        callbacks: SettingsHomeCallbacks,
        categories: list[SettingsCategorySpec],
        version: str | None = None,
        frame_cls: Callable[..., Any] = tk.Frame,
        label_cls: Callable[..., Any] = tk.Label,
        style_frame_cls: Callable[..., Any] = ttk.Frame,
        style_label_cls: Callable[..., Any] = ttk.Label,
        button_cls: Callable[..., Any] = ttk.Button,
        canvas_cls: Callable[..., Any] = tk.Canvas,
        scrollbar_cls: Callable[..., Any] = ttk.Scrollbar,
        button_coordinator: ButtonCoordinator | None = None,
        colors: dict[str, str] | None = None,
        fonts: dict[str, Any] | None = None,
    ) -> None:
        self.callbacks = callbacks
        self.colors = ui_styles.COLORS if colors is None else colors
        self.fonts = ui_styles.FONTS if fonts is None else fonts
        self.categories = list(categories)
        self.version = version
        self._category_buttons: dict[str, Any] = {}
        self._button_coordinator = button_coordinator

        self.frame_cls = frame_cls
        self.label_cls = label_cls
        self.style_frame_cls = style_frame_cls
        self.style_label_cls = style_label_cls
        self.button_cls = button_cls
        self.canvas_cls = canvas_cls
        self.scrollbar_cls = scrollbar_cls

        self._build(parent)

    @property
    def category_keys(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self.categories)

    def _build(self, parent: Any) -> None:
        if self.version:
            self.version_label = self.label_cls(
                parent,
                text=f"System Analyzer {self.version}",
                bg=self.colors["background"],
                fg=self.colors["muted_text"],
                font=self.fonts["body"],
            )
            self.version_label.pack(side="bottom", anchor="w", pady=(6, 0))

        (
            self.back_button,
            self.canvas,
            self.content,
            self._refresh_scrollbar,
        ) = ui_layout.page_shell(
            parent,
            title="Settings",
            description=(
                "Application configuration and options. Choose a category to continue."
            ),
            back_text="Back to System Overview",
            on_back=self.callbacks.on_back,
            style_frame_cls=self.style_frame_cls,
            style_label_cls=self.style_label_cls,
            button_cls=self.button_cls,
            canvas_cls=self.canvas_cls,
            scrollbar_cls=self.scrollbar_cls,
            colors=self.colors,
        )

        for spec in self.categories:
            self._build_category_card(spec)
        self._build_discovery_action()

    def _build_discovery_action(self) -> None:
        card = self.frame_cls(
            self.content,
            bg=self.colors["card"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["border"],
        )
        card.pack(fill="x", pady=(0, 14))
        text_column = self.frame_cls(card, bg=self.colors["card"])
        text_column.pack(side="left", fill="x", expand=True)
        self.label_cls(
            text_column,
            text="Network discovery",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.fonts["section"],
        ).pack(anchor="w")
        self.label_cls(
            text_column,
            text="Start local-network discovery directly without opening Nodes & Connections.",
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
            wraplength=_CARD_WRAP,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))
        button = self.button_cls(
            card,
            text="Start Discovery",
            command=self.callbacks.on_start_discovery,
            style="Neutral.TButton",
            cursor="hand2",
        )
        button.pack(side="right", padx=(16, 0), anchor="center")
        if self._button_coordinator is not None:
            self._button_coordinator.register(
                "settings:discovery:start",
                self.callbacks.on_start_discovery,
                replace=True,
            )
            self._button_coordinator.bind(button, "settings:discovery:start")
        self.discovery_button = button

    def _build_category_card(self, spec: SettingsCategorySpec) -> None:
        card = self.frame_cls(
            self.content,
            bg=self.colors["card"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["border"],
        )
        card.pack(fill="x", pady=(0, 14))

        text_column = self.frame_cls(card, bg=self.colors["card"])
        text_column.pack(side="left", fill="x", expand=True)
        self.label_cls(
            text_column,
            text=spec.title,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.fonts["section"],
        ).pack(anchor="w")
        self.label_cls(
            text_column,
            text=spec.description,
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
            wraplength=_CARD_WRAP,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        action_column = self.frame_cls(card, bg=self.colors["card"])
        action_column.pack(side="right", padx=(16, 0), anchor="center")
        button = self.button_cls(
            action_column,
            text="Open",
            command=lambda: self.callbacks.on_select_category(spec.key),
            style="Neutral.TButton",
            cursor="hand2",
        )
        button.pack(side="right")
        coordinator = self._button_coordinator
        if coordinator is not None:
            action_id = f"settings:category:{spec.key}"

            def open_category(key: str = spec.key) -> None:
                self.callbacks.on_select_category(key)

            coordinator.register(
                action_id,
                open_category,
                replace=True,
            )
            coordinator.bind(button, action_id)
        self._category_buttons[spec.key] = button

    def focus_back(self) -> None:
        self.back_button.focus_set()

    def category_button(self, key: str) -> Any:
        return self._category_buttons[key]
