"""In-app Help & Guide pages: a topic hub plus one page per topic.

Wired through the real ``PageRouter`` exactly like every other page in this
app (Dashboard, Settings, Preferences, Nodes & Connections, ...): each page
is built once at startup and thereafter only ``pack``/``pack_forget``ed
(see ``maintenance/ui/navigation.py``). No page-local rebuild-on-click
mechanism -- that was measured at ~1.5s per topic switch (destroying and
rebuilding the header/canvas/scrollbar/cards on every click, almost all of
it Tk/Tcl geometry-management calls, not this module's own code) versus the
router's own instant ``pack`` for every other page in the app.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.help_content import HELP_TOPICS, HelpSection, HelpTopic


@dataclass(frozen=True, slots=True)
class HelpPageCallbacks:
    """The semantic events the Help hub page can emit."""

    on_back: Callable[[], None]
    on_open_topic: Callable[[str], None]


class HelpPage:
    """Build and own the Help & Guide topic list (the hub page).

    The page root is provided by the caller and is never packed by this
    class; the page router controls page visibility. All widget classes are
    injectable so tests can run headlessly.
    """

    def __init__(
        self,
        parent: Any,
        *,
        callbacks: HelpPageCallbacks,
        topics: tuple[HelpTopic, ...] = HELP_TOPICS,
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
        self.topics = tuple(topics)
        self._button_coordinator = button_coordinator
        self._topic_buttons: dict[str, Any] = {}

        (
            self.back_button,
            self.canvas,
            self.content,
            self._refresh_scrollbar,
        ) = ui_layout.page_shell(
            parent,
            title="Help & Guide",
            description=(
                "How System Analyzer works, feature by feature. Choose a topic."
            ),
            back_text="Back to Settings",
            on_back=self.callbacks.on_back,
            style_frame_cls=style_frame_cls,
            style_label_cls=style_label_cls,
            button_cls=button_cls,
            canvas_cls=canvas_cls,
            scrollbar_cls=scrollbar_cls,
            colors=self.colors,
        )
        for topic in self.topics:
            self._build_topic_card(
                topic, frame_cls=frame_cls, label_cls=label_cls, button_cls=button_cls
            )

    @property
    def topic_keys(self) -> tuple[str, ...]:
        return tuple(topic.key for topic in self.topics)

    def topic_button(self, key: str) -> Any:
        return self._topic_buttons[key]

    def focus_back(self) -> None:
        self.back_button.focus_set()

    def _build_topic_card(
        self,
        topic: HelpTopic,
        *,
        frame_cls: Callable[..., Any],
        label_cls: Callable[..., Any],
        button_cls: Callable[..., Any],
    ) -> None:
        _card, button = ui_layout.navigation_card(
            self.content,
            topic.title,
            topic.summary,
            "Open",
            lambda: self.callbacks.on_open_topic(topic.key),
            frame_cls=frame_cls,
            label_cls=label_cls,
            button_cls=button_cls,
            colors=self.colors,
            fonts=self.fonts,
            wraplength=ui_styles.LAYOUT["navigation_card_wrap"],
            action_id=f"help:topic:{topic.key}",
            button_coordinator=self._button_coordinator,
        )
        self._topic_buttons[topic.key] = button


@dataclass(frozen=True, slots=True)
class HelpTopicPageCallbacks:
    """The semantic events one Help topic detail page can emit."""

    on_back: Callable[[], None]


class HelpTopicPage:
    """Build and own one topic's detail page.

    One instance per topic, registered with the page router exactly like
    any other page -- built once, never rebuilt on navigation.
    """

    def __init__(
        self,
        parent: Any,
        *,
        topic: HelpTopic,
        callbacks: HelpTopicPageCallbacks,
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
        self.topic = topic
        self.callbacks = callbacks
        self.colors = ui_styles.COLORS if colors is None else colors
        self.fonts = ui_styles.FONTS if fonts is None else fonts

        (
            self.back_button,
            self.canvas,
            self.content,
            self._refresh_scrollbar,
        ) = ui_layout.page_shell(
            parent,
            title=topic.title,
            description=topic.summary,
            back_text="All topics",
            on_back=self.callbacks.on_back,
            style_frame_cls=style_frame_cls,
            style_label_cls=style_label_cls,
            button_cls=button_cls,
            canvas_cls=canvas_cls,
            scrollbar_cls=scrollbar_cls,
            colors=self.colors,
        )
        for section in topic.sections:
            self._build_section(section, frame_cls=frame_cls, label_cls=label_cls)

    def focus_back(self) -> None:
        self.back_button.focus_set()

    def _build_section(
        self,
        section: HelpSection,
        *,
        frame_cls: Callable[..., Any],
        label_cls: Callable[..., Any],
    ) -> None:
        _card, body = ui_layout.section_card(
            self.content,
            section.heading,
            frame_cls=frame_cls,
            label_cls=label_cls,
            colors=self.colors,
            fonts=self.fonts,
        )
        for paragraph in section.paragraphs:
            self._build_text_line(body, paragraph, label_cls=label_cls)
        for bullet in section.bullets:
            self._build_text_line(body, f"• {bullet}", label_cls=label_cls)

    def _build_text_line(
        self, body: Any, text: str, *, label_cls: Callable[..., Any]
    ) -> None:
        label_cls(
            body,
            text=text,
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
            wraplength=ui_styles.LAYOUT["section_description_wrap"],
            justify="left",
        ).pack(anchor="w", pady=(0, ui_styles.SPACING["heading_desc_gap"]))
