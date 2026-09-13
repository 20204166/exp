"""Presentation-only Settings diagnostics page."""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.diagnostics import (
    DiagnosticsSnapshot,
    format_timestamp,
    serialize_diagnostics,
)
from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.action_coordinator import ButtonCoordinator


@dataclass(frozen=True, slots=True)
class DiagnosticsPageCallbacks:
    on_back: Callable[[], None]
    on_copy: Callable[[str], None]
    on_save_capture: Callable[[], str | None] | None = None


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
        self.save_capture_button = self.button_cls(
            self.content,
            text="Save performance capture",
            command=self._save_capture,
            style=ui_styles.STYLE_NEUTRAL_BUTTON,
        )
        self.save_capture_button.pack(anchor="e", pady=(0, 10))
        self._capture_status = self.style_label_cls(
            self.content,
            text="Captures stay in memory until you save one.",
            style="Description.TLabel",
        )
        self._capture_status.pack(anchor="e", pady=(0, 10))
        if self._button_coordinator is not None:
            self._button_coordinator.register(
                "diagnostics:copy", self._copy, replace=True
            )
            self._button_coordinator.bind(self.copy_button, "diagnostics:copy")
            if self.callbacks.on_save_capture is not None:
                self._button_coordinator.register(
                    "diagnostics:save_capture",
                    self._save_capture,
                    replace=True,
                )
                self._button_coordinator.bind(
                    self.save_capture_button, "diagnostics:save_capture"
                )
        self._pulse_body = self._section(self.content, "Live health pulse")
        self._summary_body = self._section(self.content, "Summary")
        self._components_body = self._section(self.content, "Components")
        self._operations_body = self._section(self.content, "Running work")
        self._placement_body = self._section(self.content, "Placement")
        self._cluster_body = self._section(self.content, "Cluster")
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
        ui_layout.resize_aware(body, self._rewrap_section)
        return body

    def _rewrap_section(self, body: Any) -> None:
        """Keep right-hand diagnostic values readable as the page narrows."""

        width = body.winfo_width()
        if width <= 1:
            return
        wraplength = min(520, ui_layout.metric_value_wrap(width))
        for row in self._section_rows.get(body, ()):
            row[2].configure(wraplength=wraplength)

    def render(self, snapshot: DiagnosticsSnapshot) -> None:
        self._snapshot = snapshot
        active_count = sum(item.in_flight for item in snapshot.operations)
        failure = snapshot.most_recent_failure
        pending = snapshot.render.pending
        self._render_rows(
            self._pulse_body,
            [
                ("Active work", str(active_count)),
                (
                    "Recent failures",
                    failure or "No recent failures",
                ),
                (
                    "Nodes",
                    str(len(snapshot.nodes))
                    if snapshot.nodes
                    else "No remote nodes configured",
                ),
                (
                    "Render pressure",
                    f"{pending} pending" if pending else "No pending renders",
                ),
            ],
            value_colors=[
                self.colors["warning"] if active_count else self.colors["secondary"],
                self.colors["danger"] if failure else self.colors["muted_text"],
                self.colors["success"] if snapshot.nodes else self.colors["muted_text"],
                self.colors["warning"] if pending else self.colors["secondary"],
            ],
        )
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
            value_colors=[
                self.colors["danger"] if failure else self.colors["muted_text"],
                self.colors["warning"] if active_count else self.colors["secondary"],
            ],
        )
        self._render_rows(
            self._components_body,
            [
                (
                    item.key,
                    (
                        f"{item.state} · {item.capability} · "
                        f"{item.last_error or ('Last success: ' + format_timestamp(item.last_success) if item.last_success else 'No data yet')}"
                    ),
                )
                for item in snapshot.components
            ],
            empty_text="No data yet",
            value_colors=[
                self._component_color(item.state, item.capability, item.last_error)
                for item in snapshot.components
            ],
        )
        active = [item for item in snapshot.operations if item.in_flight]
        self._render_rows(
            self._operations_body,
            [(item.key, f"generation {item.generation}") for item in active],
            empty_text="Nothing currently running",
        )
        placement = snapshot.placement
        self._render_rows(
            self._placement_body,
            [
                (
                    placement.job_type,
                    f"{placement.selected_worker} · {placement.eligible_count} eligible · {placement.reason}",
                )
            ]
            if placement is not None
            else [],
            empty_text="No placement decision yet",
        )
        cluster = snapshot.cluster
        self._render_rows(
            self._cluster_body,
            [
                ("Role", cluster.role),
                ("Coordinator", cluster.coordinator_id),
                ("Epoch", str(cluster.epoch)),
                (
                    "Heartbeat",
                    "No heartbeat"
                    if cluster.heartbeat_age_seconds is None
                    else f"{cluster.heartbeat_age_seconds:.1f}s ago",
                ),
                (
                    "History (logical bytes)",
                    f"{cluster.database_bytes} / {cluster.database_cap_bytes} bytes",
                ),
                (
                    "Standby",
                    f"{cluster.standby_bytes} / {cluster.standby_cap_bytes} bytes",
                ),
                ("Retention", cluster.retention_pressure),
                (
                    "Writes",
                    "History writes paused"
                    if cluster.history_writes_paused
                    else "Collecting",
                ),
                ("Failure", cluster.failure or "None"),
            ]
            if cluster is not None
            else [],
            empty_text="No cluster configured",
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
                *(
                    [
                        (
                            metric.target,
                            (
                                f"{metric.count} events · "
                                f"p95 {metric.distribution.get('p95', 0.0):.3f}s · "
                                f"coalesced {metric.coalesced} · "
                                f"stale {metric.stale} · rejected {metric.rejected}"
                            ),
                        )
                        for metric in (
                            snapshot.observability.metrics
                            if snapshot.observability is not None
                            else ()
                        )
                    ]
                ),
            ],
        )

    def _render_rows(
        self,
        parent: Any,
        rows: list[tuple[str, str]],
        *,
        empty_text: str | None = None,
        value_colors: list[str] | None = None,
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
                existing.append(
                    self._row(
                        parent,
                        title,
                        value,
                        value_fg=(
                            value_colors[index]
                            if value_colors is not None
                            else self.colors["secondary"]
                        ),
                    )
                )
            else:
                _frame, title_label, value_label = existing[index]
                self._configure_label(title_label, text=title)
                self._configure_label(value_label, text=value)
                if value_colors is not None:
                    self._configure_label(value_label, fg=value_colors[index])
        while len(existing) > len(rows):
            frame, _title_label, _value_label = existing.pop()
            frame.destroy()

    def _row(
        self,
        parent: Any,
        title: str,
        value: str,
        *,
        value_fg: str,
    ) -> tuple[Any, Any, Any]:
        return ui_layout.metric_row(
            parent,
            title,
            value,
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            bg=self.colors["card"],
            label_fg=self.colors["text"],
            value_fg=value_fg,
            font=self.fonts["body"],
            wraplength=520,
            justify="left",
            pady=(0, 5),
        )

    def _component_color(self, state: str, capability: str, error: str | None) -> str:
        if error is not None or state == "failed":
            return self.colors["danger"]
        if state == "in_flight":
            return self.colors["warning"]
        if state == "paused":
            return self.colors["muted_text"]
        if capability in {"unavailable", "unsupported"}:
            return self.colors["muted_text"]
        return self.colors["success"]

    @staticmethod
    def _configure_label(label: Any, **options: Any) -> None:
        """Update a label through Tk while keeping recorder seams observable."""

        label.configure(**options)
        recorded_options = getattr(label, "kwargs", None)
        if isinstance(recorded_options, dict):
            recorded_options.update(options)

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

    def _save_capture(self) -> None:
        callback = self.callbacks.on_save_capture
        if callback is None:
            return
        path = callback()
        self._capture_status.configure(
            text=(
                f"Saved: {path}" if path is not None else "Capture could not be saved"
            )
        )

    def focus_back(self) -> None:
        self.back_button.focus_set()
