"""In-app Help & Guide page: a topic hub with drill-down topic detail views.

Mirrors the Settings hub exactly (one navigation card per topic, the shared
``page_shell``/``section_card`` primitives, no live-data machinery) except
that "opening a category" here means swapping this page's own content
between the topic list and one topic's detail, rather than switching to a
separately-registered page -- there is no live data to coordinate, so this
stays a page-local concern.
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
    """The semantic events the Help page can emit.

    Leaving the page entirely (from the topic list) is the only event the
    controller cares about; moving between the topic list and one topic's
    detail is page-local navigation the page handles itself.
    """

    on_back: Callable[[], None]


class HelpPage:
    """Build and own the Help & Guide hub and its topic detail views.

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
        initial_topic: str | None = None,
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
        self._selected_topic: str | None = (
            initial_topic if self._find(initial_topic or "") is not None else None
        )

        self.frame_cls = frame_cls
        self.label_cls = label_cls
        self.style_frame_cls = style_frame_cls
        self.style_label_cls = style_label_cls
        self.button_cls = button_cls
        self.canvas_cls = canvas_cls
        self.scrollbar_cls = scrollbar_cls

        self._parent = parent
        self._render()

    @property
    def topic_keys(self) -> tuple[str, ...]:
        return tuple(topic.key for topic in self.topics)

    @property
    def selected_topic(self) -> str | None:
        return self._selected_topic

    def _find(self, key: str) -> HelpTopic | None:
        return next((topic for topic in self.topics if topic.key == key), None)

    def open_topic(self, key: str) -> None:
        """Show one topic's detail directly (used by cross-links)."""

        if self._find(key) is None:
            return
        self._selected_topic = key
        self._render()

    def show_topics(self) -> None:
        """Return to the topic list (used when re-entering the page fresh)."""

        self._selected_topic = None
        self._render()

    def topic_button(self, key: str) -> Any:
        return self._topic_buttons[key]

    def focus_back(self) -> None:
        self.back_button.focus_set()

    def _render(self) -> None:
        for child in self._parent.winfo_children():
            child.destroy()
        if self._selected_topic is None:
            self._render_topic_list()
        else:
            self._render_topic_detail(self._selected_topic)

    def _render_topic_list(self) -> None:
        (
            self.back_button,
            self.canvas,
            self.content,
            self._refresh_scrollbar,
        ) = ui_layout.page_shell(
            self._parent,
            title="Help & Guide",
            description=(
                "How System Analyzer works, feature by feature. Choose a topic."
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
        self._topic_buttons = {}
        for topic in self.topics:
            self._build_topic_card(topic)

    def _build_topic_card(self, topic: HelpTopic) -> None:
        _card, button = ui_layout.navigation_card(
            self.content,
            topic.title,
            topic.summary,
            "Open",
            lambda: self.open_topic(topic.key),
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            button_cls=self.button_cls,
            colors=self.colors,
            fonts=self.fonts,
            wraplength=ui_styles.LAYOUT["navigation_card_wrap"],
            action_id=f"help:topic:{topic.key}",
            button_coordinator=self._button_coordinator,
        )
        self._topic_buttons[topic.key] = button

    def _render_topic_detail(self, key: str) -> None:
        topic = self._find(key)
        if topic is None:
            self._selected_topic = None
            self._render_topic_list()
            return
        (
            self.back_button,
            self.canvas,
            self.content,
            self._refresh_scrollbar,
        ) = ui_layout.page_shell(
            self._parent,
            title=topic.title,
            description=topic.summary,
            back_text="All topics",
            on_back=self.show_topics,
            style_frame_cls=self.style_frame_cls,
            style_label_cls=self.style_label_cls,
            button_cls=self.button_cls,
            canvas_cls=self.canvas_cls,
            scrollbar_cls=self.scrollbar_cls,
            colors=self.colors,
        )
        for section in topic.sections:
            self._build_section(section)

    def _build_section(self, section: HelpSection) -> None:
        _card, body = ui_layout.section_card(
            self.content,
            section.heading,
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
        )
        for paragraph in section.paragraphs:
            self._build_text_line(body, paragraph)
        for bullet in section.bullets:
            self._build_text_line(body, f"• {bullet}")

    def _build_text_line(self, body: Any, text: str) -> None:
        self.label_cls(
            body,
            text=text,
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
            wraplength=ui_styles.LAYOUT["section_description_wrap"],
            justify="left",
        ).pack(anchor="w", pady=(0, ui_styles.SPACING["heading_desc_gap"]))
