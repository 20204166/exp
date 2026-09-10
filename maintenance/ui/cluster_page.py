"""All Systems cluster overview page adapter (presentation-only).

This module owns only the All Systems overview's presentation: one row per
known machine with its colour chip, name, host, trust/status badge,
capabilities and last-refresh time, plus an Open action for selectable nodes.
It never imports the window, registry, or store; the controller supplies the
``ClusterNodeSpec`` list and typed callbacks.
"""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.action_coordinator import ButtonCoordinator

_DEFAULT_COLOR = "indigo"

_TRUST_TEXT: dict[str, str] = {
    "local": "Local",
    "trusted": "Trusted",
    "authorised": "Authorised",
    "untrusted": "Untrusted",
    "discovered": "Discovered",
}

_PAIRING_TEXT = {
    "discovered": "Discovered",
    "pairing": "Pairing",
    "trusted": "Trusted",
    "pairing_failed": "Pairing failed",
    "identity_changed": "Identity changed",
}


@dataclass(frozen=True, slots=True)
class ClusterPageCallbacks:
    """The semantic events the All Systems page can emit."""

    on_back: Callable[[], None]
    on_open_node: Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ClusterNodeSpec:
    """Presentation data for one machine on the All Systems overview."""

    node_id: str
    display_name: str
    hostname: str
    color: str | None
    trust: str
    status: str
    capabilities: tuple[str, ...]
    is_local: bool
    selectable: bool
    last_refresh: str | None = None
    pairing_state: str = "trusted"
    target_state: str = "Unknown"


class ClusterPage:
    """Build and own the All Systems overview inside the given page root.

    The page root is provided by the caller and is never packed by this class;
    all widget classes are injectable so tests can run headlessly.
    ``refresh_nodes`` re-renders the machine list after a node change.
    """

    def __init__(
        self,
        parent: Any,
        *,
        callbacks: ClusterPageCallbacks,
        nodes: list[ClusterNodeSpec],
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
        self._disposed = False

        self.frame_cls = frame_cls
        self.label_cls = label_cls
        self.style_frame_cls = style_frame_cls
        self.style_label_cls = style_label_cls
        self.button_cls = button_cls
        self.canvas_cls = canvas_cls
        self.scrollbar_cls = scrollbar_cls
        self._button_coordinator = button_coordinator

        self._nodes = {spec.node_id: spec for spec in nodes}
        self._build(parent)

    def _build(self, parent: Any) -> None:
        (
            self.back_button,
            self.canvas,
            self.content,
            self._refresh_scrollbar,
        ) = ui_layout.page_shell(
            parent,
            title="All Systems",
            description=(
                "Every known machine and its connection, trust and capability "
                "state. Only trusted, operational nodes can be opened as the "
                "selected node."
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

        _, self._body = ui_layout.section_card(
            self.content,
            "Machines",
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            description=(
                "Status reflects the last known presence. Offline or "
                "stale machines remain visible so you can reconnect later."
            ),
        )
        self.refresh_nodes(list(self._nodes.values()))

    def refresh_nodes(self, nodes: list[ClusterNodeSpec]) -> None:
        if self._disposed:
            return
        self._nodes = {spec.node_id: spec for spec in nodes}
        if self._button_coordinator is not None:
            self._button_coordinator.clear_prefix("cluster:node:")
        ui_layout.clear_children(self._body)
        if not nodes:
            self.label_cls(
                self._body,
                text="No machines registered yet.",
                bg=self.colors["card"],
                fg=self.colors["muted_text"],
                font=self.fonts["body"],
                anchor="w",
            ).pack(anchor="w", pady=(0, 4))
            return
        for spec in nodes:
            self._node_row(self._body, spec)

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        if self._button_coordinator is not None:
            self._button_coordinator.clear_prefix("cluster:node:")

    def _node_row(self, body: Any, spec: ClusterNodeSpec) -> None:
        row = self.frame_cls(body, bg=self.colors["card"])
        row.pack(fill="x", pady=(0, 10))

        colour = spec.color or _DEFAULT_COLOR
        hex_colour = ui_styles.NODE_COLORS.get(
            colour, ui_styles.NODE_COLORS[_DEFAULT_COLOR]
        )
        chip = self.label_cls(
            row,
            text=" ",
            bg=hex_colour,
            fg=hex_colour,
            width=2,
        )
        chip.pack(side="left", padx=(0, 8), pady=(2, 0))

        text_column = self.frame_cls(row, bg=self.colors["card"])
        text_column.pack(side="left", fill="x", expand=True)

        name_line = spec.display_name
        if spec.hostname and spec.hostname != spec.display_name:
            name_line += f"  ·  {spec.hostname}"
        if spec.is_local:
            name_line += "  ·  this machine"
        self.label_cls(
            text_column,
            text=name_line,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.fonts["body"],
            anchor="w",
        ).pack(anchor="w")

        trust_text = _TRUST_TEXT.get(spec.trust, spec.trust)
        pairing_text = _PAIRING_TEXT.get(spec.pairing_state, spec.pairing_state)
        meta = (
            f"{spec.target_state}  ·  {pairing_text}  ·  {trust_text}  ·  {spec.status}"
        )
        if spec.capabilities:
            meta += f"  ·  {', '.join(spec.capabilities)}"
        if spec.last_refresh:
            meta += f"  ·  last refreshed {spec.last_refresh}"
        self.label_cls(
            text_column,
            text=meta,
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        if spec.selectable and spec.status != "offline":

            def open_node(node_id: str = spec.node_id) -> None:
                self.callbacks.on_open_node(node_id)

            button = self.button_cls(
                row,
                text="Open",
                command=open_node,
                style="Neutral.TButton",
            )
            button.pack(side="right")
            coordinator = self._button_coordinator
            if coordinator is not None:
                action_id = f"cluster:node:{spec.node_id}:open"
                coordinator.register(action_id, open_node, replace=True)
                coordinator.bind(button, action_id)

    def focus_back(self) -> None:
        self.back_button.focus_set()
