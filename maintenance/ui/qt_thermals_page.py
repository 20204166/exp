"""Standalone Qt page for rendering prepared thermal telemetry states."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from textwrap import fill
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from maintenance.components.temperature import (
    TemperatureEvent,
    TemperatureRenderState,
    TemperatureSeriesSnapshot,
    TemperatureState,
)
from maintenance.models import CapabilityState
from maintenance.ui import qt_layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.qt_thermal_graph import QtThermalGraph

THERMAL_COMPONENTS = ("cpu", "gpu", "storage", "battery")


class QtThermalsPage(QWidget):
    """Render supplied per-node state; never read or aggregate telemetry."""

    def __init__(
        self,
        *,
        on_back: Callable[[], None],
        on_learn_more: Callable[[], None] | None = None,
        button_coordinator: ButtonCoordinator | None = None,
        colors: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.colors = ui_styles.COLORS if colors is None else colors
        self.button_coordinator = button_coordinator
        self.graphs: dict[str, QtThermalGraph] = {}
        self.graph_sections: dict[str, QFrame] = {}
        self.event_buttons: list[QPushButton] = []
        self.event_labels: list[QLabel] = []
        self.event_rows: list[QWidget] = []
        self._state: TemperatureRenderState | None = None
        self._capabilities: Mapping[str, CapabilityState] = {}
        self.setAccessibleName("Thermals page")
        ui_styles.configure_qt_styles(self, colors=self.colors)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            ui_styles.SPACING["page_x"],
            ui_styles.SPACING["page_y"],
            ui_styles.SPACING["page_x"],
            ui_styles.SPACING["page_y"],
        )
        root.setSpacing(ui_styles.SPACING["row_gap"])
        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("Thermals", self)
        title.setProperty("role", "title")
        title.setAccessibleName("Thermals")
        description = QLabel(
            "Current and recent system temperatures for the selected node.", self
        )
        description.setProperty("role", "description")
        description.setWordWrap(True)
        heading.addWidget(title)
        heading.addWidget(description)
        header.addLayout(heading, 1)
        self.back_button = QPushButton("Back to System Overview", self)
        self.back_button.setAccessibleName("Back to System Overview")
        self.back_button.setMinimumHeight(44)
        self.back_button.clicked.connect(on_back)
        header.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        self.status_label = QLabel("Waiting for thermal telemetry.", self)
        self.status_label.setProperty("role", "status")
        self.status_label.setAccessibleName("Thermal telemetry status")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        if on_learn_more is not None:
            self.learn_more_button = QPushButton("Why isn't a sensor available?", self)
            self.learn_more_button.setAccessibleName("Why isn't a sensor available?")
            self.learn_more_button.setProperty("role", "neutral")
            self.learn_more_button.setMinimumHeight(44)
            if button_coordinator is None:
                self.learn_more_button.clicked.connect(on_learn_more)
            else:
                button_coordinator.register(
                    "thermals:learn-more", on_learn_more, replace=True
                )
                button_coordinator.bind(self.learn_more_button, "thermals:learn-more")
            root.addWidget(self.learn_more_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.scroll_area, self.content = ui_layout.qt_scrollable_area(self)
        self.scroll_area.setAccessibleName("Thermal graphs and recent events")
        self.scroll_area.setMinimumHeight(0)
        self.content_layout = cast(QVBoxLayout, self.content.layout())
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        root.addWidget(self.scroll_area, 1)

    def focus_back(self) -> None:
        """Restore keyboard focus to the page's navigation return button."""

        self.back_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def render(  # type: ignore[override] -- thermal state renderer, not QWidget painting
        self,
        state: TemperatureRenderState | None,
        capabilities: Mapping[str, CapabilityState] | None = None,
    ) -> None:
        """Render a prepared immutable state without starting telemetry work."""

        self._state = state
        self._capabilities = {} if capabilities is None else capabilities
        if state is None:
            self.status_label.setText("Thermal telemetry is unavailable.")
            self._clear_content()
            return

        visible: set[str] = set()
        for component in THERMAL_COMPONENTS:
            snapshot = state.series_for(component)
            if snapshot is None or not self._should_show(component, snapshot.state):
                self._remove_component(component)
                continue
            visible.add(component)
            graph = self._ensure_component(component)
            graph.render(snapshot)

        self._render_events(visible, state.events)
        visible_snapshots: list[TemperatureSeriesSnapshot] = []
        for graph in self.graphs.values():
            if graph.snapshot is not None:
                visible_snapshots.append(graph.snapshot)
        if not visible_snapshots:
            status = "No supported temperature sensors detected."
        elif any(
            snapshot.state is TemperatureState.VALID and snapshot.samples
            for snapshot in visible_snapshots
        ):
            status = "Live history from shared node telemetry."
        elif any(
            snapshot.state is TemperatureState.NO_DATA for snapshot in visible_snapshots
        ):
            status = "Waiting for thermal samples from shared node telemetry."
        else:
            status = "No thermal readings are available; sensor states are shown below."
        self.status_label.setText(status)

    def _should_show(self, component: str, series_state: TemperatureState) -> bool:
        capability = self._capabilities.get(component)
        if capability == CapabilityState.UNSUPPORTED:
            return False
        if capability is None and series_state not in (
            TemperatureState.VALID,
            TemperatureState.ERROR,
        ):
            return False
        if component == "battery":
            return capability == CapabilityState.SUPPORTED or series_state in (
                TemperatureState.VALID,
                TemperatureState.ERROR,
            )
        # A supported resource card can still have an unsupported thermal
        # series; keep that distinction visible instead of hiding the reason.
        return True

    def _ensure_component(self, component: str) -> QtThermalGraph:
        graph = self.graphs.get(component)
        if graph is not None:
            return graph
        section = QFrame(self.content)
        section.setObjectName(f"thermal-section-{component}")
        section.setFrameShape(QFrame.Shape.StyledPanel)
        section.setStyleSheet(
            f"QFrame#thermal-section-{component} {{ border: 1px solid {self.colors['border']}; }}"
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(
            ui_styles.SPACING["section_pad_x"],
            ui_styles.SPACING["section_pad_y"],
            ui_styles.SPACING["section_pad_x"],
            ui_styles.SPACING["section_pad_y"],
        )
        graph = QtThermalGraph(
            self._title(component), colors=self.colors, parent=section
        )
        layout.addWidget(graph)
        self.content_layout.addWidget(section)
        self.graph_sections[component] = section
        self.graphs[component] = graph
        return graph

    def _remove_component(self, component: str) -> None:
        section = self.graph_sections.pop(component, None)
        self.graphs.pop(component, None)
        if section is not None:
            self.content_layout.removeWidget(section)
            section.deleteLater()

    def _clear_content(self) -> None:
        for component in tuple(self.graphs):
            self._remove_component(component)
        self._render_events(set(), ())

    def _render_events(
        self, visible_components: set[str], events: tuple[TemperatureEvent, ...]
    ) -> None:
        layout = self.content_layout
        if self.event_rows:
            for row in self.event_rows:
                layout.removeWidget(row)
                row.deleteLater()
        self.event_buttons.clear()
        self.event_labels.clear()
        self.event_rows.clear()
        displayed = sorted(
            (event for event in events if event.component in visible_components),
            key=lambda event: event.started_monotonic,
        )[-6:]
        heading = getattr(self, "events_heading", None)
        if heading is None:
            self.events_heading = QLabel("Recent thermal events", self.content)
            self.events_heading.setProperty("role", "section")
            layout.addWidget(self.events_heading)
        if not displayed:
            self.events_heading.setVisible(bool(events) or bool(visible_components))
            if visible_components:
                empty_label = getattr(self, "events_empty_label", None)
                if empty_label is None:
                    self.events_empty_label = QLabel(
                        "No recent thermal events", self.content
                    )
                    empty_label = self.events_empty_label
                    empty_label.setAccessibleName("No recent thermal events")
                    layout.addWidget(empty_label)
                empty_label.setVisible(True)
            elif getattr(self, "events_empty_label", None) is not None:
                self.events_empty_label.setVisible(False)
            return
        if getattr(self, "events_empty_label", None) is not None:
            self.events_empty_label.setVisible(False)
        self.events_heading.setVisible(True)
        for event in displayed:
            row = QWidget(self.content)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(ui_styles.SPACING["control_gap"])
            label = QLabel(self._format_event(event), row)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setAccessibleName(f"{event.component.upper()} thermal event details")
            button = QPushButton("View event", row)
            button.setProperty("role", "neutral")
            button.setMinimumHeight(44)
            button.setAccessibleName(
                f"View {event.component.upper()} event: {event.summary()}"
            )
            row_layout.addWidget(label, 1)
            row_layout.addWidget(button)
            button.clicked.connect(
                lambda _checked=False, item=event: self._show_event(item)
            )
            layout.addWidget(row)
            self.event_rows.append(row)
            self.event_buttons.append(button)
            self.event_labels.append(label)

    @staticmethod
    def _format_event(event: TemperatureEvent) -> str:
        time_text = event.started_at.strftime("%H:%M")
        detail = fill(
            f"{event.summary()} · Sensor {event.sensor_name or event.sensor_id}", 64
        )
        return f"{event.component.upper()} · {time_text}\n{detail}"

    def _show_event(self, event: TemperatureEvent) -> None:
        graph = self.graphs.get(event.component)
        if graph is not None:
            graph.render(event.snapshot(title=self._title(event.component)))

    @staticmethod
    def _title(component: str) -> str:
        return f"{component.capitalize()} Temperature"
