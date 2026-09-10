"""Presentation-only Settings diagnostics page."""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.diagnostics import DiagnosticsSnapshot, serialize_diagnostics
from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.action_coordinator import ButtonCoordinator


@dataclass(frozen=True, slots=True)
class DiagnosticsPageCallbacks:
    on_back: Callable[[], None]
    on_copy: Callable[[str], None]


class DiagnosticsPage:
    """Render bounded runtime diagnostics supplied by the controller."""

    def __init__(
        self,
        parent: Any,
        *,
        callbacks: DiagnosticsPageCallbacks,
        snapshot: DiagnosticsSnapshot,
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
        self.frame_cls = frame_cls
        self.label_cls = label_cls
        self.style_frame_cls = style_frame_cls
        self.style_label_cls = style_label_cls
        self.button_cls = button_cls
        self.canvas_cls = canvas_cls
        self.scrollbar_cls = scrollbar_cls
        self._button_coordinator = button_coordinator
        self._section_rows: dict[Any, list[tuple[Any, Any, Any]]] = {}
        self._empty_labels: dict[Any, Any] = {}
        self._build(parent)
        self.render(snapshot)

    def _build(self, parent: Any) -> None:
        (
            self.back_button,
            self.canvas,
            self.content,
            self._refresh_scrollbar,
        ) = ui_layout.page_shell(
            parent,
            title="Diagnostics",
            description="Current application, component, connection, and rendering state.",
            back_text="Back to Settings",
            on_back=self.callbacks.on_back,
            style_frame_cls=self.style_frame_cls,
            style_label_cls=self.style_label_cls,
            button_cls=self.button_cls,
            canvas_cls=self.canvas_cls,
            scrollbar_cls=self.scrollbar_cls,
            colors=self.colors,
        )
        self.copy_button = self.button_cls(
            self.content,
            text="Copy diagnostics",
            command=self._copy,
            style=ui_styles.STYLE_NEUTRAL_BUTTON,
        )
        self.copy_button.pack(anchor="e", pady=(0, 10))
        self._summary_body = self._section(self.content, "Summary")
        self._components_body = self._section(self.content, "Components")
        self._operations_body = self._section(self.content, "Running work")
        self._nodes_body = self._section(self.content, "Nodes and connections")
        self._render_body = self._section(self.content, "Rendering")

    def _section(self, parent: Any, title: str) -> Any:
        _, body = ui_layout.section_card(
            parent,
            title,
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
        )
        return body

    def render(self, snapshot: DiagnosticsSnapshot) -> None:
        self._snapshot = snapshot
        self._render_rows(
            self._summary_body,
            [
                (
                    "Most recent failure",
                    snapshot.most_recent_failure or "No recent failures",
                ),
                (
                    "Active work",
                    str(sum(item.in_flight for item in snapshot.operations)),
                ),
            ],
        )
        self._render_rows(
            self._components_body,
            [
                (
                    item.key,
                    (
                        f"{item.state} · {item.capability} · "
                        f"{item.last_error or ('Last success: ' + str(item.last_success) if item.last_success else 'No data yet')}"
                    ),
                )
                for item in snapshot.components
            ],
            empty_text="No data yet",
        )
        active = [item for item in snapshot.operations if item.in_flight]
        self._render_rows(
            self._operations_body,
            [(item.key, f"generation {item.generation}") for item in active],
            empty_text="Nothing currently running",
        )
        self._render_rows(
            self._nodes_body,
            [
                (item.display_name, f"{item.trust} · {item.reason or item.connection}")
                for item in snapshot.nodes
            ],
            empty_text="No remote nodes configured",
        )
        self._render_rows(
            self._render_body,
            [
                ("Stale result rejections", str(snapshot.render.stale_rejections)),
                ("Pending render targets", str(snapshot.render.pending)),
            ],
        )

    def _render_rows(
        self,
        parent: Any,
        rows: list[tuple[str, str]],
        *,
        empty_text: str | None = None,
    ) -> None:
        existing = self._section_rows.setdefault(parent, [])
        if empty_text is not None:
            empty = self._empty_labels.get(parent)
            if not rows:
                if empty is None:
                    empty = self._empty(parent, empty_text)
                    self._empty_labels[parent] = empty
                else:
                    empty.configure(text=empty_text)
            elif empty is not None:
                empty.destroy()
                del self._empty_labels[parent]
        for index, (title, value) in enumerate(rows):
            if index >= len(existing):
                existing.append(self._row(parent, title, value))
            else:
                _frame, title_label, value_label = existing[index]
                title_label.configure(text=title)
                value_label.configure(text=value)
        while len(existing) > len(rows):
            frame, _title_label, _value_label = existing.pop()
            frame.destroy()

    def _row(self, parent: Any, title: str, value: str) -> tuple[Any, Any, Any]:
        row = self.frame_cls(parent, bg=self.colors["card"])
        row.pack(fill="x", pady=(0, 5))
        title_label = self.label_cls(
            row,
            text=title,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.fonts["body"],
        )
        title_label.pack(side="left")
        value_label = self.label_cls(
            row,
            text=value,
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
            wraplength=520,
            justify="left",
        )
        value_label.pack(side="right", anchor="e")
        return row, title_label, value_label

    def _empty(self, parent: Any, text: str) -> Any:
        label = self.label_cls(
            parent,
            text=text,
            bg=self.colors["card"],
            fg=self.colors["muted_text"],
            font=self.fonts["body"],
        )
        label.pack(anchor="w")
        return label

    def _copy(self) -> None:
        self.callbacks.on_copy(serialize_diagnostics(self._snapshot))

    def focus_back(self) -> None:
        self.back_button.focus_set()
