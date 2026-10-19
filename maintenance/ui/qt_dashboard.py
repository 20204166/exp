"""Standalone Qt dashboard and resource cards for the shell migration."""

from collections.abc import Callable, Iterable
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from maintenance.components.catalog import ResourceFeature
from maintenance.models import ResourceSummary, resource_status
from maintenance.ui import qt_layout as ui_layout
from maintenance.ui import scan_status as shared_scan_status
from maintenance.ui import styles as ui_styles
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.qt_scan_status import (
    apply_cancelling,
    apply_complete,
    apply_error,
    apply_ready,
    apply_reset,
    apply_scanning,
    apply_step,
)
from maintenance.ui.resource_details import action_label_text, metric_label_pairs


class QtResourceCard(QFrame):
    """Accessible Qt rendering of one catalog resource summary."""

    USAGE_BAR_KEYS = frozenset({"cpu", "memory", "storage", "battery"})

    def __init__(
        self,
        feature: ResourceFeature,
        on_open: Callable[[str], None],
        *,
        colors: dict[str, str] | None = None,
        button_coordinator: ButtonCoordinator | None = None,
    ) -> None:
        super().__init__()
        self.key = feature.key
        self.colors = ui_styles.COLORS if colors is None else colors
        self.button_coordinator = button_coordinator
        self.action_id = f"dashboard:resource:{feature.key}"
        self.setObjectName(f"resource-card-{feature.key}")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(f"{feature.title} resource card")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet(
            "QFrame#resource-card-"
            + feature.key
            + " { border: 1px solid "
            + self.colors["border"]
            + "; border-radius: 4px; }"
        )
        layout = QVBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(
            ui_styles.SPACING["card_pad_x"],
            ui_styles.SPACING["card_pad_y"],
            ui_styles.SPACING["card_pad_x"],
            ui_styles.SPACING["card_pad_y"],
        )
        layout.setSpacing(ui_styles.SPACING["row_gap"])
        self.title_label = QLabel(feature.title.upper(), self)
        self.title_label.setObjectName("resource-title")
        self.value_label = QLabel("—", self)
        self.value_label.setObjectName("resource-value")
        self.subtitle_label = QLabel("No data yet", self)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setObjectName("resource-status")
        for label in (self.title_label, self.value_label, self.subtitle_label):
            label.setMinimumWidth(0)
        self.metric_rows: list[tuple[QLabel, QLabel]] = []
        self.metrics_widget = QWidget(self)
        self.metrics_layout = QVBoxLayout(self.metrics_widget)
        self.metrics_layout.setContentsMargins(0, 0, 0, 0)
        self.metrics_layout.setSpacing(ui_styles.SPACING["caption_gap"])
        self.progress: QProgressBar | None = None
        self.details_button = QPushButton("View details  →", self)
        self.details_button.setProperty("role", "neutral")
        self.details_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.details_button.setAccessibleName(f"Open {feature.title} details")
        if button_coordinator is None:
            self.details_button.clicked.connect(lambda: on_open(self.key))
        else:
            button_coordinator.register(
                self.action_id, lambda: on_open(self.key), enabled=False
            )
            button_coordinator.bind(self.details_button, self.action_id)
        for item in (
            self.title_label,
            self.value_label,
            self.subtitle_label,
            self.metrics_widget,
            self.details_button,
        ):
            layout.addWidget(item)
        self._apply_typography()

    def _apply_typography(self) -> None:
        self.title_label.setStyleSheet(f"color: {self.colors['secondary']};")
        self.value_label.setStyleSheet(
            f"color: {self.colors['text']}; font-size: 22px; font-weight: 700;"
        )
        self.subtitle_label.setStyleSheet(f"color: {self.colors['secondary']};")

    @classmethod
    def should_show_usage_bar(cls, summary: ResourceSummary) -> bool:
        return summary.key in cls.USAGE_BAR_KEYS and summary.percent is not None

    def set_action_enabled(self, enabled: bool) -> None:
        if self.button_coordinator is not None:
            self.button_coordinator.set_enabled(self.action_id, enabled)
        else:
            self.details_button.setEnabled(enabled)

    def update_summary(self, summary: ResourceSummary) -> None:
        self.value_label.setText(summary.value)
        status = resource_status(summary)
        self.subtitle_label.setText(
            f"{summary.subtitle} · {status}" if status is not None else summary.subtitle
        )
        self.details_button.setText(action_label_text(summary.actionable))
        self.set_action_enabled(summary.actionable)
        if self.should_show_usage_bar(summary):
            if self.progress is None:
                self.progress = QProgressBar(self)
                self.progress.setRange(0, 100)
                self.progress.setTextVisible(False)
                self.progress.setAccessibleName(f"{summary.title} usage")
                self.progress.setStyleSheet(
                    "QProgressBar { border: 0; background: "
                    + self.colors["card_bar_trough"]
                    + "; } QProgressBar::chunk { background: "
                    + self.colors["accent"]
                    + "; }"
                )
                self._layout.insertWidget(
                    self._layout.indexOf(self.details_button), self.progress
                )
            self.progress.setValue(round(max(0.0, min(100.0, summary.percent or 0.0))))
        elif self.progress is not None:
            self._layout.removeWidget(self.progress)
            self.progress.deleteLater()
            self.progress = None
        pairs = metric_label_pairs(summary.details, summary.value)
        while len(self.metric_rows) < len(pairs):
            row = QWidget(self.metrics_widget)
            row_layout = QGridLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            name, value = QLabel(row), QLabel(row)
            name.setStyleSheet(f"color: {self.colors['secondary']};")
            name.setMinimumWidth(0)
            value.setMinimumWidth(0)
            value.setWordWrap(True)
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            row_layout.addWidget(name, 0, 0)
            row_layout.addWidget(value, 0, 1)
            row_layout.setColumnStretch(0, 1)
            self.metrics_layout.addWidget(row)
            self.metric_rows.append((name, value))
        while len(self.metric_rows) > len(pairs):
            name, value = self.metric_rows.pop()
            row = name.parentWidget()
            if row is None:
                raise RuntimeError("Metric labels must remain parented to their row")
            self.metrics_layout.removeWidget(row)
            row.deleteLater()
        for (name, value), pair in zip(self.metric_rows, pairs):
            name.setText(pair[0])
            value.setText(pair[1])

    def reset_summary(self) -> None:
        self.value_label.setText("—")
        self.subtitle_label.setText("No data yet")
        self.details_button.setText("View details  →")
        self.set_action_enabled(False)
        for name, _value in self.metric_rows:
            row = name.parentWidget()
            if row is None:
                raise RuntimeError("Metric labels must remain parented to their row")
            self.metrics_layout.removeWidget(row)
            row.deleteLater()
        self.metric_rows.clear()
        if self.progress is not None:
            self._layout.removeWidget(self.progress)
            self.progress.deleteLater()
            self.progress = None


class QtDashboard(QWidget):
    """Qt-only dashboard projection with explicit state update methods.

    This widget owns presentation only. The shell supplies catalog metadata,
    callbacks, colors and already-computed summaries/scan events.
    """

    def __init__(
        self,
        features: Iterable[ResourceFeature],
        *,
        on_open: Callable[[str], None] | None = None,
        on_scan: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        button_coordinator: ButtonCoordinator | None = None,
        colors: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.colors = ui_styles.COLORS if colors is None else colors
        self.setAccessibleName("System overview dashboard")
        ui_styles.configure_qt_styles(self, colors=self.colors)
        root = QVBoxLayout(self)
        root.setContentsMargins(
            *(ui_styles.SPACING[k] for k in ("page_x", "page_y", "page_x", "page_y"))
        )
        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("System Analyzer", header)
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        self.status_label = QLabel(shared_scan_status.READY_TEXT, header)
        self.status_label.setAccessibleName("Scan status")
        self.scan_progress = QProgressBar(header)
        self.scan_progress.setAccessibleName("Scan progress")
        self.scan_progress.setRange(0, 100)
        self.scan_progress.setValue(0)
        self.scan_progress.setTextVisible(False)
        self.scan_progress.hide()
        header_layout.addWidget(title)
        header_layout.addWidget(self.status_label)
        header_layout.addWidget(self.scan_progress)
        root.addWidget(header)
        self.empty_label = QLabel("Run a scan to load system details.", self)
        self.empty_label.setAccessibleName("Dashboard empty state")
        root.addWidget(self.empty_label)
        self.cards_scroll, self.cards_host = ui_layout.qt_scrollable_area(self)
        self.cards_scroll.setAccessibleName("Resource cards")
        self.cards_layout = QGridLayout()
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setHorizontalSpacing(ui_styles.LAYOUT["card_grid_gap"])
        self.cards_layout.setVerticalSpacing(ui_styles.LAYOUT["card_row_gap"])
        for column in range(3):
            self.cards_layout.setColumnStretch(column, 1)
        host_layout = self.cards_host.layout()
        if not isinstance(host_layout, QVBoxLayout):
            raise TypeError("Scrollable card host must have a vertical layout")
        host_layout.addLayout(self.cards_layout)
        root.addWidget(self.cards_scroll, 1)
        self.cards: dict[str, QtResourceCard] = {}
        self._visible_cards: set[str] = set()
        self._feature_order: list[str] = []
        for feature in sorted(features, key=lambda item: (item.order, item.key)):
            if feature.key in self.cards:
                raise ValueError(f"Duplicate dashboard resource key: {feature.key}")
            card = QtResourceCard(
                feature,
                on_open or (lambda _key: None),
                colors=self.colors,
                button_coordinator=button_coordinator,
            )
            self.cards[feature.key] = card
            self._visible_cards.add(feature.key)
            self._feature_order.append(feature.key)
        self._relayout_cards()
        if on_scan is not None:
            self.scan_button = QPushButton("Scan now", self)
            self.scan_button.setProperty("role", "primary")
            self.scan_button.setAccessibleName("Start system scan")
            self.scan_button.clicked.connect(on_scan)
            root.addWidget(self.scan_button)
        else:
            self.scan_button = None
        if on_cancel is not None:
            self.cancel_button = QPushButton("Cancel scan", self)
            self.cancel_button.setProperty("role", "neutral")
            self.cancel_button.setAccessibleName("Cancel system scan")
            self.cancel_button.clicked.connect(on_cancel)
            self.cancel_button.setEnabled(False)
            root.addWidget(self.cancel_button)
        else:
            self.cancel_button = None

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._relayout_cards()

    def _relayout_cards(self) -> None:
        while self.cards_layout.count():
            self.cards_layout.takeAt(0)
        # The outer width is stable during the initial resize event; the scroll
        # viewport may still report zero until Qt has completed layout.
        width = self.width()
        columns = 1 if width < 600 else 2 if width < 980 else 3
        visible_index = 0
        row_heights: dict[int, int] = {}
        for row in range(self.cards_layout.rowCount()):
            self.cards_layout.setRowMinimumHeight(row, 0)
        for key in self._feature_order:
            card = self.cards[key]
            if key not in self._visible_cards:
                continue
            row = visible_index // columns
            self.cards_layout.addWidget(card, row, visible_index % columns)
            card._layout.activate()
            row_heights[row] = max(
                row_heights.get(row, 0), card.minimumSizeHint().height()
            )
            visible_index += 1
        for row, height in row_heights.items():
            self.cards_layout.setRowMinimumHeight(row, height)
        self.cards_layout.activate()
        self.cards_host.setMinimumHeight(self.cards_layout.minimumSize().height())

    def set_summaries(self, summaries: Iterable[ResourceSummary]) -> None:
        by_key = {summary.key: summary for summary in summaries}
        for key, card in self.cards.items():
            summary = by_key.get(key)
            card.update_summary(
                summary
            ) if summary is not None else card.reset_summary()
        self.empty_label.setVisible(not by_key)
        self._relayout_cards()
        QTimer.singleShot(0, self, self._relayout_cards)

    def set_card_visible(self, key: str, visible: bool) -> None:
        if visible:
            self._visible_cards.add(key)
            self.cards[key].show()
        else:
            self._visible_cards.discard(key)
            self.cards[key].hide()
        self._relayout_cards()

    def set_scan_ready(self) -> None:
        apply_ready(self.status_label)
        apply_reset(self.scan_progress)
        self.scan_progress.hide()
        if self.scan_button is not None:
            self.scan_button.setEnabled(True)
        if self.cancel_button is not None:
            self.cancel_button.setEnabled(False)

    def set_scan_busy(self) -> None:
        apply_scanning(self.status_label)
        self.scan_progress.show()
        if self.scan_button is not None:
            self.scan_button.setEnabled(False)
        if self.cancel_button is not None:
            self.cancel_button.setEnabled(True)

    def set_scan_progress(self, message: str, count: int, total: int) -> None:
        self.scan_progress.show()
        apply_step(self.status_label, self.scan_progress, message, count, total)

    def set_scan_cancelled(self) -> None:
        apply_cancelling(self.status_label)
        if self.scan_button is not None:
            self.scan_button.setEnabled(True)
        if self.cancel_button is not None:
            self.cancel_button.setEnabled(False)

    def set_scan_complete(self, value: int = 100) -> None:
        apply_complete(
            self.status_label,
            self.scan_progress,
            value,
            success_color=self.colors["success"],
        )
        if self.scan_button is not None:
            self.scan_button.setEnabled(True)
        if self.cancel_button is not None:
            self.cancel_button.setEnabled(False)

    def set_scan_error(self, message: str) -> None:
        apply_error(self.status_label, message)
        if self.scan_button is not None:
            self.scan_button.setEnabled(True)
        if self.cancel_button is not None:
            self.cancel_button.setEnabled(False)
