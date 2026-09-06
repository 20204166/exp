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

_CARD_WRAP = 560


@dataclass(frozen=True, slots=True)
class SettingsHomeCallbacks:
    """The semantic events the Settings home page can emit.

    The controller wires these to page navigation; the page never decides
    where a category leads.
    """

    on_back: Callable[[], None]
    on_select_category: Callable[[str], None]


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
        frame_cls: Callable[..., Any] = tk.Frame,
        label_cls: Callable[..., Any] = tk.Label,
        style_frame_cls: Callable[..., Any] = ttk.Frame,
        style_label_cls: Callable[..., Any] = ttk.Label,
        button_cls: Callable[..., Any] = ttk.Button,
        canvas_cls: Callable[..., Any] = tk.Canvas,
        scrollbar_cls: Callable[..., Any] = ttk.Scrollbar,
        colors: dict[str, str] | None = None,
        fonts: dict[str, Any] | None = None,
    ) -> None:
        self.callbacks = callbacks
        self.colors = ui_styles.COLORS if colors is None else colors
        self.fonts = ui_styles.FONTS if fonts is None else fonts
        self.categories = list(categories)
        self._category_buttons: dict[str, Any] = {}

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
        self._category_buttons[spec.key] = button

    def focus_back(self) -> None:
        self.back_button.focus_set()

    def category_button(self, key: str) -> Any:
        return self._category_buttons[key]
