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
from maintenance.ui import node_presentation
from maintenance.ui import styles as ui_styles
from maintenance.ui.action_coordinator import ButtonCoordinator

_DEFAULT_COLOR = "indigo"

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
    on_pause: Callable[[str], None] | None = None
    on_resume: Callable[[str], None] | None = None
    on_revoke: Callable[[str], None] | None = None
    on_remove_connection: Callable[[str], None] | None = None
    on_remove_job: Callable[[str], None] | None = None
    on_share_dashboard: Callable[[], None] | None = None


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
    role: str = "worker"
    paused: bool = False
    role_editable: bool = False
    has_active_job: bool = True


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
        self._rows: dict[str, Any] = {}
        self._empty_label: Any | None = None
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

    _STRUCTURAL = (
        "selectable",
        "status",
        "role",
        "role_editable",
        "paused",
        "has_active_job",
        "capabilities",
        "trust",
        "is_local",
        "pairing_state",
        "target_state",
    )

    def refresh_nodes(self, nodes: list[ClusterNodeSpec]) -> None:
        if self._disposed:
            return
        incoming = {spec.node_id: spec for spec in nodes}
        for node_id in [key for key in self._rows if key not in incoming]:
            self._remove_row(node_id)
        for spec in nodes:
            previous = self._nodes.get(spec.node_id)
            if spec.node_id not in self._rows:
                self._rows[spec.node_id] = self._node_row(self._body, spec)
            elif previous is not None and not self._same_row(previous, spec):
                self._remove_row(spec.node_id)
                self._rows[spec.node_id] = self._node_row(self._body, spec)
            else:
                self._update_row(spec)
        self._nodes = {spec.node_id: spec for spec in nodes}
        self._repack_in_order(nodes)
        self._update_empty_state(nodes)

    @staticmethod
    def _same_row(previous: ClusterNodeSpec, current: ClusterNodeSpec) -> bool:
        return all(
            getattr(previous, name) == getattr(current, name)
            for name in ClusterPage._STRUCTURAL
        )

    def _remove_row(self, node_id: str) -> None:
        coordinator = self._button_coordinator
        if coordinator is not None:
            coordinator.clear_prefix(f"cluster:node:{node_id}:")
        row = self._rows.pop(node_id, None)
        if row is not None:
            row.destroy()

    def _repack_in_order(self, nodes: list[ClusterNodeSpec]) -> None:
        for spec in nodes:
            row = self._rows.get(spec.node_id)
            if row is not None:
                row.pack(fill="x", pady=(0, 10))

    def _update_empty_state(self, nodes: list[ClusterNodeSpec]) -> None:
        if nodes:
            if self._empty_label is not None:
                self._empty_label.destroy()
                self._empty_label = None
        elif self._empty_label is None:
            label = self.label_cls(
                self._body,
                text="No machines registered yet.",
                bg=self.colors["card"],
                fg=self.colors["muted_text"],
                font=self.fonts["body"],
                anchor="w",
            )
            label.pack(anchor="w", pady=(0, 4))
            self._empty_label = label

    def _update_row(self, spec: ClusterNodeSpec) -> None:
        row = self._rows.get(spec.node_id)
        if row is None:
            return
        meta = getattr(row, "_meta_label", None)
        if meta is not None:
            meta.config(text=self._meta_text(spec))
        name = getattr(row, "_name_label", None)
        if name is not None:
            name.config(text=spec.display_name)

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        if self._button_coordinator is not None:
            self._button_coordinator.clear_prefix("cluster:node:")

    def _node_row(self, body: Any, spec: ClusterNodeSpec) -> Any:
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
        name_label = self.label_cls(
            text_column,
            text=name_line,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.fonts["body"],
            anchor="w",
        )
        name_label.pack(anchor="w")
        row._name_label = name_label

        meta = self._meta_text(spec)
        status_role = node_presentation.status_color_role(spec.status)
        if spec.target_state == "Permission denied":
            status_role = "danger"
        meta_label = self.label_cls(
            text_column,
            text=meta,
            bg=self.colors["card"],
            fg=self.colors[status_role],
            font=self.fonts["body"],
            anchor="w",
        )
        meta_label.pack(anchor="w", pady=(2, 0))
        row._meta_label = meta_label

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
        if (
            spec.role_editable
            and not spec.is_local
            and self.callbacks.on_revoke is not None
        ):
            revoke = self.button_cls(
                row,
                text="Revoke",
                command=lambda: self.callbacks.on_revoke(spec.node_id),
                style=ui_styles.STYLE_DANGER_BUTTON,
            )
            revoke.pack(side="right", padx=(0, 8))
        if (
            spec.role_editable
            and not spec.is_local
            and self.callbacks.on_remove_connection is not None
        ):
            remove_connection = self.button_cls(
                row,
                text="Remove connection",
                command=lambda: self.callbacks.on_remove_connection(spec.node_id),
                style=ui_styles.STYLE_NEUTRAL_BUTTON,
            )
            remove_connection.pack(side="right", padx=(0, 8))
        if (
            spec.role_editable
            and not spec.is_local
            and self.callbacks.on_remove_job is not None
        ):
            remove_job = self.button_cls(
                row,
                text="Remove job",
                command=lambda: self.callbacks.on_remove_job(spec.node_id),
                style=ui_styles.STYLE_NEUTRAL_BUTTON,
            )
            remove_job.pack(side="right", padx=(0, 8))
        if spec.is_local and self.callbacks.on_share_dashboard is not None:
            share = self.button_cls(
                row,
                text="Share dashboard",
                command=self.callbacks.on_share_dashboard,
                style=ui_styles.STYLE_NEUTRAL_BUTTON,
            )
            share.pack(side="right", padx=(0, 8))
        if (
            spec.role_editable
            and not spec.is_local
            and (
                self.callbacks.on_pause is not None
                or self.callbacks.on_resume is not None
            )
        ):
            paused = spec.paused
            if paused and self.callbacks.on_resume is not None:
                command = lambda: self.callbacks.on_resume(spec.node_id)
            elif not paused and self.callbacks.on_pause is not None:
                command = lambda: self.callbacks.on_pause(spec.node_id)
            else:
                command = lambda: None
            pause = self.button_cls(
                row,
                text="Re-enable" if paused else "Pause",
                command=command,
                style=ui_styles.STYLE_NEUTRAL_BUTTON,
            )
            pause.pack(side="right", padx=(0, 8))
        return row

    def _meta_text(self, spec: ClusterNodeSpec) -> str:
        trust_text = node_presentation.trust_label(spec.trust, is_local=spec.is_local)
        pairing_text = _PAIRING_TEXT.get(spec.pairing_state, spec.pairing_state)
        meta = f"{trust_text} · {node_presentation.status_label(spec.status)}"
        meta += f" · {spec.role.title()}"
        if spec.paused:
            meta += " · Paused"
        if spec.hostname and spec.hostname != spec.display_name:
            meta += f" · {spec.hostname}"
        if spec.target_state != "Unknown":
            meta += f" · {spec.target_state}"
        meta += f" · {pairing_text}"
        if spec.role == "worker" and not spec.is_local and not spec.has_active_job:
            meta += " · 20% participation"
        if spec.capabilities:
            meta += f" · {', '.join(node_presentation.capability_labels(spec.capabilities))}"
        if spec.last_refresh:
            meta += f"  ·  last refreshed {spec.last_refresh}"
        return meta

    def focus_back(self) -> None:
        self.back_button.focus_set()
