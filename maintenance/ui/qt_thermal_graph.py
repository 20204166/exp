"""Qt-native thermal graph and toolkit-independent plot geometry."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from maintenance.components.temperature import (
    TemperatureSeriesSnapshot,
    TemperatureState,
)
from maintenance.ui import styles as ui_styles


@dataclass(frozen=True, slots=True)
class QtThermalGraphLayout:
    """Finite, bounded graph coordinates in widget-local pixels."""

    points: tuple[tuple[float, float], ...]
    left: float
    right: float
    top: float
    bottom: float
    warning_y: float | None
    critical_y: float | None


def build_qt_thermal_graph_layout(
    snapshot: TemperatureSeriesSnapshot,
    width: int,
    height: int,
    *,
    max_points: int = ui_styles.GRAPH["max_points"],
) -> QtThermalGraphLayout | None:
    """Map finite series values and thresholds into bounded plot geometry."""

    if max_points < 1:
        raise ValueError("max_points must be positive")
    values = tuple(
        sample.value_celsius
        for sample in snapshot.samples
        if isfinite(sample.value_celsius)
    )
    if not values:
        return None
    if len(values) > max_points:
        if max_points == 1:
            values = (values[-1],)
        else:
            step = (len(values) - 1) / (max_points - 1)
            values = tuple(values[round(index * step)] for index in range(max_points))

    left, top = 14.0, 18.0
    right = float(max(width, 1) - 14)
    bottom = float(max(height, 1) - 18)
    right = max(left + 1.0, right)
    bottom = max(top + 1.0, bottom)
    thresholds = tuple(
        value
        for value in (snapshot.warning_celsius, snapshot.critical_celsius)
        if value is not None and isfinite(value)
    )
    lowest, highest = min((*values, *thresholds)), max((*values, *thresholds))
    if lowest == highest:
        lowest -= 1.0
        highest += 1.0

    def y_for(value: float) -> float:
        return bottom - (value - lowest) / (highest - lowest) * (bottom - top)

    points = tuple(
        (
            left
            if len(values) == 1
            else left + (right - left) * index / (len(values) - 1),
            y_for(value),
        )
        for index, value in enumerate(values)
    )

    def threshold_y(value: float | None) -> float | None:
        return y_for(value) if value is not None and isfinite(value) else None

    return QtThermalGraphLayout(
        points,
        left,
        right,
        top,
        bottom,
        threshold_y(snapshot.warning_celsius),
        threshold_y(snapshot.critical_celsius),
    )


class _ThermalPlot(QWidget):
    """Native QPainter canvas with a stable graph-height contract."""

    def __init__(self, colors: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.colors = colors
        self.snapshot: TemperatureSeriesSnapshot | None = None
        self.setMinimumHeight(ui_styles.GRAPH["height"])
        self.setAccessibleName("Temperature history plot")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        snapshot = self.snapshot
        layout = (
            build_qt_thermal_graph_layout(snapshot, self.width(), self.height())
            if snapshot is not None
            and snapshot.state is TemperatureState.VALID
            and snapshot.samples
            else None
        )
        if layout is None:
            painter.setPen(
                QPen(
                    QColor(self.colors.get("graph_empty_border", self.colors["border"]))
                )
            )
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
            return

        painter.setPen(
            QPen(
                QColor(self.colors.get("graph_grid", self.colors["border"])),
                1,
                Qt.PenStyle.DotLine,
            )
        )
        for fraction in (0.25, 0.5, 0.75):
            y = layout.top + (layout.bottom - layout.top) * fraction
            painter.drawLine(QPointF(layout.left, y), QPointF(layout.right, y))
        self._draw_threshold(
            painter,
            layout.warning_y,
            self.colors.get("warning", "#B45309"),
            Qt.PenStyle.DashLine,
        )
        self._draw_threshold(
            painter,
            layout.critical_y,
            self.colors.get("danger", "#B42318"),
            Qt.PenStyle.DashDotLine,
        )
        painter.setPen(QPen(QColor(self.colors["accent"]), 2))
        if len(layout.points) > 1:
            for start, end in zip(layout.points, layout.points[1:]):
                painter.drawLine(QPointF(*start), QPointF(*end))
        for x, y in layout.points:
            painter.drawEllipse(QPointF(x, y), 2.5, 2.5)

    def _draw_threshold(
        self, painter: QPainter, y: float | None, color: str, style: Qt.PenStyle
    ) -> None:
        if y is not None:
            painter.setPen(QPen(QColor(color), 1, style))
            painter.drawLine(14, round(y), max(15, self.width() - 14), round(y))


class QtThermalGraph(QWidget):
    """Accessible state labels and custom-painted plot for one series."""

    MAX_PLOT_POINTS = ui_styles.GRAPH["max_points"]

    def __init__(
        self,
        title: str,
        *,
        colors: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.colors = ui_styles.COLORS if colors is None else colors
        self.title = title
        self._snapshot: TemperatureSeriesSnapshot | None = None
        self.setAccessibleName(title)
        self.setMinimumWidth(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ui_styles.SPACING["caption_gap"])
        self.title_label = QLabel(title, self)
        self.title_label.setProperty("role", "section")
        self.state_label = QLabel("No temperature data", self)
        self.state_label.setWordWrap(True)
        self.state_label.setAccessibleName(f"{title} state and readings")
        self.state_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.plot = _ThermalPlot(self.colors, self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.state_label)
        layout.addWidget(self.plot)

    @property
    def snapshot(self) -> TemperatureSeriesSnapshot | None:
        return self._snapshot

    def render(  # type: ignore[override] -- thermal state renderer, not QWidget painting
        self, snapshot: TemperatureSeriesSnapshot | None
    ) -> None:
        self._snapshot = snapshot
        description = self._description(snapshot)
        self.state_label.setText(description)
        self.setAccessibleDescription(description)
        self.plot.snapshot = snapshot
        self.plot.update()

    @staticmethod
    def _description(snapshot: TemperatureSeriesSnapshot | None) -> str:
        if snapshot is None:
            return "No temperature data"
        if snapshot.state is TemperatureState.UNSUPPORTED:
            return "Temperature not supported"
        if snapshot.state is TemperatureState.ERROR:
            return snapshot.error or "Temperature temporarily unavailable"
        if snapshot.state is TemperatureState.NO_DATA or not snapshot.samples:
            return "Waiting for the first sample"
        state = snapshot.state.value.replace("_", " ").title()
        readings = [f"{state}"]
        for label, value in (
            ("Current", snapshot.current_celsius),
            ("Min", snapshot.minimum_celsius),
            ("Max", snapshot.maximum_celsius),
        ):
            if value is not None and isfinite(value):
                readings.append(f"{label} {value:.0f}°C")
        if snapshot.warning_celsius is not None and isfinite(snapshot.warning_celsius):
            readings.append(f"Warning {snapshot.warning_celsius:.0f}°C")
        if snapshot.critical_celsius is not None and isfinite(
            snapshot.critical_celsius
        ):
            readings.append(f"Critical {snapshot.critical_celsius:.0f}°C")
        sensor_names = tuple(
            dict.fromkeys(
                sample.sensor_name for sample in snapshot.samples if sample.sensor_name
            )
        )
        if sensor_names:
            readings.append("Sensors: " + ", ".join(sensor_names))
        return " · ".join(readings)
