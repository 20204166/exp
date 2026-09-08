"""Dedicated in-window presentation for shared thermal telemetry."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.components.temperature import (
    TemperatureEvent,
    TemperatureState,
    TemperatureTelemetry,
)
from maintenance.models import CapabilityState
from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.telemetry_graph import TelemetryMiniGraph

THERMAL_COMPONENTS = ("cpu", "gpu", "storage", "battery")


@dataclass(frozen=True, slots=True)
class ThermalsPageCallbacks:
    """Controller actions exposed by the page."""

    on_back: Callable[[], None]


class ThermalsPage:
    """Retained page that renders the selected node's existing thermal state."""

    def __init__(
        self,
        parent: Any,
        *,
        callbacks: ThermalsPageCallbacks,
        frame_cls: Callable[..., Any] = ttk.Frame,
        label_cls: Callable[..., Any] = ttk.Label,
        button_cls: Callable[..., Any] = ttk.Button,
        canvas_cls: Callable[..., Any] = tk.Canvas,
        scrollbar_cls: Callable[..., Any] = ttk.Scrollbar,
        colors: dict[str, str] | None = None,
        fonts: dict[str, Any] | None = None,
    ) -> None:
        self.callbacks = callbacks
        self.frame_cls = frame_cls
        self.label_cls = label_cls
        self.button_cls = button_cls
        self.canvas_cls = canvas_cls
        self.scrollbar_cls = scrollbar_cls
        self.colors = ui_styles.COLORS if colors is None else colors
        self.fonts = ui_styles.FONTS if fonts is None else fonts
        self._graphs: dict[str, TelemetryMiniGraph] = {}
        self._graph_sections: dict[str, Any] = {}
        self._event_rows: list[Any] = []
        self._events_card: Any | None = None
        self._events_body: Any | None = None
        self._last_event_signature: tuple[Any, ...] | None = None
        self._telemetry: TemperatureTelemetry | None = None
        self._capabilities: Mapping[str, CapabilityState] = {}
        self._build(parent)

    @property
    def graph_components(self) -> tuple[str, ...]:
        return tuple(self._graphs)

    def _build(self, parent: Any) -> None:
        (
            self.back_button,
            self.canvas,
            self.content,
            self._refresh_scrollbar,
        ) = ui_layout.page_shell(
            parent,
            title="Thermals",
            description="Current and recent system temperatures for the selected node.",
            back_text="Back to System Overview",
            on_back=self.callbacks.on_back,
            style_frame_cls=self.frame_cls,
            style_label_cls=self.label_cls,
            button_cls=self.button_cls,
            canvas_cls=self.canvas_cls,
            scrollbar_cls=self.scrollbar_cls,
            colors=self.colors,
        )

        self.status_label = self.label_cls(
            self.content,
            text="Waiting for thermal telemetry.",
            style="Description.TLabel",
        )
        self.status_label.pack(anchor="w", pady=(0, 14))

    def focus_back(self) -> None:
        self.back_button.focus_set()

    def refresh_from_telemetry(
        self,
        telemetry: TemperatureTelemetry | None,
        capabilities: Mapping[str, CapabilityState] | None = None,
    ) -> None:
        """Render cached telemetry without triggering a scan."""

        self._telemetry = telemetry
        self._capabilities = capabilities or {}
        if telemetry is None:
            self.status_label.config(text="Thermal telemetry is unavailable.")
            return

        for component in THERMAL_COMPONENTS:
            snapshot = telemetry.series_snapshot(
                component, title=self._title(component)
            )
            if not self._should_show(component, snapshot.state):
                self._remove_component(component)
                continue
            graph = self._ensure_component(component)
            graph.render(snapshot)

        self._refresh_events()
        if self._graphs:
            self.status_label.config(text="Live history from shared node telemetry.")
        else:
            self.status_label.config(text="No supported temperature sensors detected.")
        self._refresh_scrollbar()

    def refresh_component(self, component: str) -> None:
        """Refresh one component from already-recorded telemetry."""

        if self._telemetry is None:
            return
        component = component.casefold()
        if component not in THERMAL_COMPONENTS:
            return
        snapshot = self._telemetry.series_snapshot(
            component,
            title=self._title(component),
        )
        if not self._should_show(component, snapshot.state):
            self._remove_component(component)
        else:
            self._ensure_component(component).render(snapshot)
        self._refresh_events()
        self._refresh_scrollbar()

    def _should_show(self, component: str, state: TemperatureState) -> bool:
        capability = self._capabilities.get(component)
        if capability == CapabilityState.UNSUPPORTED:
            return False
        if capability is None and state not in (
            TemperatureState.VALID,
            TemperatureState.ERROR,
        ):
            return False
        if component == "battery":
            return capability == CapabilityState.SUPPORTED or state in (
                TemperatureState.VALID,
                TemperatureState.ERROR,
            )
        return state != TemperatureState.UNSUPPORTED

    def _ensure_component(self, component: str) -> TelemetryMiniGraph:
        graph = self._graphs.get(component)
        if graph is not None:
            return graph
        section, body = ui_layout.section_card(
            self.content,
            self._title(component),
            frame_cls=tk.Frame,
            label_cls=tk.Label,
            colors=self.colors,
            fonts=self.fonts,
            description="Recent bounded temperature history from the shared telemetry.",
        )
        graph = TelemetryMiniGraph(
            body,
            colors=self.colors,
            title=self._title(component),
        )
        graph.pack(fill=tk.X, pady=(0, 10))
        self._graph_sections[component] = section
        self._graphs[component] = graph
        return graph

    def _remove_component(self, component: str) -> None:
        section = self._graph_sections.pop(component, None)
        self._graphs.pop(component, None)
        if section is not None:
            section.destroy()

    def _refresh_events(self) -> None:
        events = self._events()
        signature = tuple(
            (
                event.component,
                event.sensor_id,
                event.started_monotonic,
                event.ended_monotonic,
                event.peak_celsius,
            )
            for event in events
        )
        if signature == self._last_event_signature:
            return
        self._last_event_signature = signature
        for row in self._event_rows:
            row.destroy()
        self._event_rows.clear()

        if self._events_body is None:
            self._events_card, self._events_body = ui_layout.section_card(
                self.content,
                "Recent thermal events",
                frame_cls=tk.Frame,
                label_cls=tk.Label,
                colors=self.colors,
                fonts=self.fonts,
                description="Bounded snapshots of genuine thermal spikes.",
            )
        body = self._events_body
        if not events:
            row, _label, _value = ui_layout.metric_row(
                body,
                "Status",
                "No recent thermal events",
                frame_cls=tk.Frame,
                label_cls=tk.Label,
                bg=self.colors["card"],
                label_fg=self.colors["secondary"],
                value_fg=self.colors["text"],
                font=self.fonts["detail_row"],
                justify="left",
            )
            self._event_rows.append(row)
            return

        for event in events:
            row, _label, _value = ui_layout.metric_row(
                body,
                event.component.upper(),
                f"{event.started_at.strftime('%H:%M')} · {event.summary()}",
                frame_cls=tk.Frame,
                label_cls=tk.Label,
                bg=self.colors["card"],
                label_fg=self.colors["secondary"],
                value_fg=self.colors["text"],
                font=self.fonts["detail_row"],
                justify="left",
            )
            button = self.button_cls(
                row,
                text="View event",
                style=ui_styles.STYLE_NEUTRAL_BUTTON,
                command=lambda event=event: self._show_event(event),
            )
            button.pack(side=tk.RIGHT, padx=(12, 0))
            self._event_rows.append(row)

    def _show_event(self, event: TemperatureEvent) -> None:
        graph = self._graphs.get(event.component)
        if graph is not None:
            graph.render(event.snapshot(title=self._title(event.component)))

    def _events(self) -> tuple[TemperatureEvent, ...]:
        if self._telemetry is None:
            return ()
        events: list[TemperatureEvent] = []
        for component in self._graphs:
            events.extend(self._telemetry.recent_events(component))
        events.sort(key=lambda event: event.started_monotonic)
        return tuple(events[-6:])

    @staticmethod
    def _title(component: str) -> str:
        return f"{component.capitalize()} Temperature"
