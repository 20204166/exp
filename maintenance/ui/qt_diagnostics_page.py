"""Standalone Qt diagnostics page; snapshot and actions remain controller-owned."""

from collections.abc import Callable, Sequence
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayoutItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from maintenance.diagnostics import (
    DiagnosticsSnapshot,
    format_timestamp,
    serialize_diagnostics,
)
from maintenance.ui import qt_layout as ui_layout
from maintenance.ui import styles as ui_styles


class QtDiagnosticsPage(QWidget):
    """Render supplied diagnostics and emit copy/save/navigation callbacks."""

    def __init__(
        self,
        snapshot: DiagnosticsSnapshot,
        *,
        on_back: Callable[[], None],
        on_copy: Callable[[str], None],
        on_save_capture: Callable[[], str | None] | None = None,
        developer_mode_visible: bool = False,
        colors: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.colors = ui_styles.COLORS if colors is None else colors
        self._on_copy = on_copy
        self._on_save_capture = on_save_capture
        self.setAccessibleName("Diagnostics")
        ui_styles.configure_qt_styles(self, colors=self.colors)
        root = QVBoxLayout(self)
        root.setContentsMargins(
            *(
                ui_styles.SPACING[key]
                for key in ("page_x", "page_y", "page_x", "page_y")
            )
        )
        self.title_label = QLabel("Diagnostics", self)
        self.title_label.setProperty("role", "title")
        description = QLabel(
            "Current application, component, connection, and rendering state.", self
        )
        description.setWordWrap(True)
        description.setProperty("role", "description")
        root.addWidget(self.title_label)
        root.addWidget(description)
        self.back_button = QPushButton("Back to Settings", self)
        self.back_button.setAccessibleName("Back to Settings")
        self.back_button.clicked.connect(on_back)
        root.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignLeft)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.copy_button = QPushButton("Copy diagnostics", self)
        self.copy_button.setProperty("role", "neutral")
        self.copy_button.setAccessibleName("Copy diagnostics")
        self.copy_button.clicked.connect(self._copy)
        actions.addWidget(self.copy_button)
        self.save_capture_button = QPushButton("Save performance capture", self)
        self.save_capture_button.setProperty("role", "neutral")
        self.save_capture_button.setAccessibleName("Save performance capture")
        self.save_capture_button.setVisible(
            developer_mode_visible and on_save_capture is not None
        )
        self.save_capture_button.clicked.connect(self._save_capture)
        actions.addWidget(self.save_capture_button)
        root.addLayout(actions)
        self.capture_status = QLabel(
            "Captures stay in memory until you save one.", self
        )
        self.capture_status.setWordWrap(True)
        self.capture_status.setAccessibleName("Performance capture status")
        self.capture_status.setProperty("role", "description")
        root.addWidget(self.capture_status)

        self.scroll_area, self.content = ui_layout.qt_scrollable_area(self)
        self.scroll_area.setAccessibleName("Diagnostics details")
        root.addWidget(self.scroll_area, 1)
        self.value_labels: dict[str, QLabel] = {}
        self.value_colors: dict[str, str | None] = {}
        self._row_widgets: dict[str, list[QWidget]] = {}
        self._empty_labels: dict[str, QLabel] = {}
        self.render(snapshot)

    def render(self, snapshot: DiagnosticsSnapshot) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self._snapshot = snapshot
        self.value_labels.clear()
        self.value_colors.clear()
        active_count = sum(item.in_flight for item in snapshot.operations)
        failure = snapshot.most_recent_failure
        self._render_section(
            "Live health pulse",
            [
                (
                    "Active work",
                    str(active_count),
                    self.colors["warning"]
                    if active_count
                    else self.colors["secondary"],
                ),
                (
                    "Recent failures",
                    failure or "No recent failures",
                    self.colors["danger"] if failure else self.colors["muted_text"],
                ),
                (
                    "Nodes",
                    str(len(snapshot.nodes))
                    if snapshot.nodes
                    else "No remote nodes configured",
                    self.colors["success"]
                    if snapshot.nodes
                    else self.colors["muted_text"],
                ),
                (
                    "Render pressure",
                    f"{snapshot.render.pending} pending"
                    if snapshot.render.pending
                    else "No pending renders",
                    self.colors["warning"]
                    if snapshot.render.pending
                    else self.colors["secondary"],
                ),
            ],
        )
        self._render_section(
            "Summary",
            [
                (
                    "Most recent failure",
                    failure or "No recent failures",
                    self.colors["danger"] if failure else self.colors["muted_text"],
                ),
                (
                    "Active work",
                    str(active_count),
                    self.colors["warning"]
                    if active_count
                    else self.colors["secondary"],
                ),
            ],
        )
        self._render_section(
            "Components",
            [
                (
                    item.key,
                    f"{item.state} · {item.capability} · {item.last_error or ('Last success: ' + format_timestamp(item.last_success) if item.last_success else 'No data yet')}",
                    self._component_color(item.state, item.capability, item.last_error),
                )
                for item in snapshot.components
            ],
            empty="No data yet",
        )
        self._render_section(
            "Running work",
            [
                (item.key, f"generation {item.generation}", None)
                for item in snapshot.operations
                if item.in_flight
            ],
            empty="Nothing currently running",
        )
        placement = snapshot.placement
        self._render_section(
            "Placement",
            [
                (
                    placement.job_type,
                    f"{placement.selected_worker} · {placement.eligible_count} eligible · {placement.reason}",
                    None,
                )
            ]
            if placement
            else [],
            empty="No placement decision yet",
        )
        cluster = snapshot.cluster
        cluster_rows = (
            []
            if cluster is None
            else [
                ("Role", cluster.role, None),
                ("Coordinator", cluster.coordinator_id, None),
                ("Epoch", str(cluster.epoch), None),
                (
                    "Heartbeat",
                    "No heartbeat"
                    if cluster.heartbeat_age_seconds is None
                    else f"{cluster.heartbeat_age_seconds:.1f}s ago",
                    None,
                ),
                (
                    "History (logical bytes)",
                    f"{cluster.database_bytes} / {cluster.database_cap_bytes} bytes",
                    None,
                ),
                (
                    "Standby",
                    f"{cluster.standby_bytes} / {cluster.standby_cap_bytes} bytes",
                    None,
                ),
                ("Retention", cluster.retention_pressure, None),
                (
                    "Writes",
                    "History writes paused"
                    if cluster.history_writes_paused
                    else "Collecting",
                    None,
                ),
                ("Failure", cluster.failure or "None", None),
            ]
        )
        self._render_section("Cluster", cluster_rows, empty="No cluster configured")
        self._render_section(
            "Nodes and connections",
            [
                (
                    item.display_name,
                    f"{item.trust} · {item.reason or item.connection}",
                    None,
                )
                for item in snapshot.nodes
            ],
            empty="No remote nodes configured",
        )
        render_rows: list[tuple[str, str, str | None]] = [
            ("Stale result rejections", str(snapshot.render.stale_rejections), None),
            ("Pending render targets", str(snapshot.render.pending), None),
        ]
        if snapshot.observability is not None:
            render_rows.extend(
                (
                    metric.target,
                    f"{metric.count} events · p95 {metric.distribution.get('p95', 0.0):.3f}s · coalesced {metric.coalesced} · stale {metric.stale} · rejected {metric.rejected}",
                    None,
                )
                for metric in snapshot.observability.metrics
            )
        self._render_section("Rendering", render_rows)

    def _render_section(
        self,
        title: str,
        rows: Sequence[tuple[str, str, str | None]],
        *,
        empty: str | None = None,
    ) -> None:
        key = title
        if key not in self._row_widgets:
            frame = QFrame(self.content)
            frame.setObjectName("diagnostics-section")
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame.setStyleSheet(
                f"QFrame#diagnostics-section {{ border: 1px solid {self.colors['border']}; }}"
            )
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(
                *(
                    ui_styles.SPACING[name]
                    for name in (
                        "section_pad_x",
                        "section_pad_y",
                        "section_pad_x",
                        "section_pad_y",
                    )
                )
            )
            heading = QLabel(title, frame)
            heading.setProperty("role", "section")
            layout.addWidget(heading)
            cast(QVBoxLayout, self.content.layout()).addWidget(frame)
            self._row_widgets[key] = [frame]
        frame = self._row_widgets[key][0]
        layout = cast(QVBoxLayout, frame.layout())
        prior_rows = self._row_widgets[key][1:]
        empty_label = self._empty_labels.get(key)
        if rows and empty_label is not None:
            layout.removeWidget(empty_label)
            empty_label.deleteLater()
            del self._empty_labels[key]
        desired_count = len(rows)
        while len(prior_rows) > desired_count:
            widget = prior_rows.pop()
            layout.removeWidget(widget)
            widget.deleteLater()
        if not rows and empty is not None:
            if empty_label is None:
                empty_label = QLabel(empty, frame)
                empty_label.setProperty("role", "description")
                layout.addWidget(empty_label)
                self._empty_labels[key] = empty_label
            else:
                empty_label.setText(empty)
        elif rows:
            for index, (name, value, color) in enumerate(rows):
                if index >= len(prior_rows):
                    row = QWidget(frame)
                    row_layout = QVBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(ui_styles.SPACING["caption_gap"])
                    label = QLabel(row)
                    label.setProperty("role", "description")
                    val = QLabel(row)
                    val.setWordWrap(True)
                    val.setMinimumWidth(0)
                    val.setTextInteractionFlags(
                        Qt.TextInteractionFlag.TextSelectableByMouse
                    )
                    row_layout.addWidget(label)
                    row_layout.addWidget(val)
                    layout.addWidget(row)
                    prior_rows.append(row)
                row_layout = cast(QVBoxLayout, prior_rows[index].layout())
                label = cast(QLabel, cast(QLayoutItem, row_layout.itemAt(0)).widget())
                val = cast(QLabel, cast(QLayoutItem, row_layout.itemAt(1)).widget())
                label.setText(name)
                val.setText(value)
                val.setAccessibleName(f"{name} diagnostic value")
                val.setAccessibleDescription(f"{name}: {value}")
                if color:
                    val.setStyleSheet(f"color: {color};")
                else:
                    val.setStyleSheet("")
                self.value_labels[name] = val
                self.value_colors[name] = color
        self._row_widgets[key] = [frame, *prior_rows]

    def _component_color(self, state: str, capability: str, error: str | None) -> str:
        if error is not None or state == "failed":
            return self.colors["danger"]
        if state == "in_flight":
            return self.colors["warning"]
        if state == "paused" or capability in {"unavailable", "unsupported"}:
            return self.colors["muted_text"]
        return self.colors["success"]

    def _copy(self) -> None:
        self._on_copy(serialize_diagnostics(self._snapshot))

    def _save_capture(self) -> None:
        if self._on_save_capture is None:
            return
        try:
            path = self._on_save_capture()
        except Exception as error:  # noqa: BLE001
            # This callback boundary reports unexpected save errors to the user.
            message = f"Capture could not be saved: {error}"
            role = "danger"
        else:
            message = (
                f"Saved: {path}" if path is not None else "Capture could not be saved"
            )
            role = "success" if path is not None else "danger"
        self.capture_status.setText(message)
        self.capture_status.setProperty("role", role)
        self.capture_status.style().unpolish(self.capture_status)
        self.capture_status.style().polish(self.capture_status)

    def focus_back(self) -> None:
        self.back_button.setFocus()
