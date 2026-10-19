"""Standalone Qt presentation for the cluster overview (5C)."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
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

from maintenance.ui import qt_layout as ui_layout
from maintenance.ui import styles as ui_styles


@dataclass(frozen=True, slots=True)
class QtClusterSummary:
    """Presentation values already resolved by cluster/domain owners."""

    cluster_id: str
    coordinator_id: str | None
    epoch: int | None


@dataclass(frozen=True, slots=True)
class QtClusterActionSpec:
    """A policy-owned action projection; this widget does not infer authority."""

    key: str
    label: str
    visible: bool
    enabled: bool
    confirmation_intent: str | None = None


@dataclass(frozen=True, slots=True)
class QtClusterNodeSpec:
    """One node's independent trust, connection, and cluster presentation state."""

    node_id: str
    display_name: str
    hostname: str
    trust_state: str
    connection_state: str
    cluster_member: bool
    roles: tuple[str, ...] = ()
    coordinator_id: str | None = None
    paused: bool = False
    actions: tuple[QtClusterActionSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class QtClusterCallbacks:
    """Controller callbacks for navigation and named, policy-approved actions."""

    on_back: Callable[[], None]
    on_action: Mapping[str, Callable[[str, str | None], None]]


class QtClusterPage(QWidget):
    """Scrollable cluster overview. All state and action policy are injected."""

    def __init__(
        self,
        summary: QtClusterSummary,
        nodes: Sequence[QtClusterNodeSpec],
        *,
        callbacks: QtClusterCallbacks,
        colors: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.colors = ui_styles.COLORS if colors is None else colors
        self.callbacks = callbacks
        self.setAccessibleName("Cluster overview")
        ui_styles.configure_qt_styles(self, colors=self.colors)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            *(
                ui_styles.SPACING[key]
                for key in ("page_x", "page_y", "page_x", "page_y")
            )
        )
        title = QLabel("Cluster", self)
        title.setProperty("role", "title")
        description = QLabel(
            "Cluster assignments, node trust, and connection state are shown separately.",
            self,
        )
        description.setWordWrap(True)
        description.setProperty("role", "description")
        root.addWidget(title)
        root.addWidget(description)

        self.back_button = QPushButton("Back to System Overview", self)
        self.back_button.setAccessibleName("Back to System Overview")
        self.back_button.clicked.connect(callbacks.on_back)
        root.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.scroll_area, self.content = ui_layout.qt_scrollable_area(self)
        self.scroll_area.setAccessibleName("Cluster details")
        root.addWidget(self.scroll_area, 1)
        content_layout = cast(QVBoxLayout, self.content.layout())

        self.cluster_label = QLabel(f"Cluster: {summary.cluster_id}", self.content)
        self.cluster_label.setWordWrap(True)
        self.cluster_label.setProperty("role", "section")
        coordinator = summary.coordinator_id or "Not reported"
        epoch = f" · Epoch {summary.epoch}" if summary.epoch is not None else ""
        self.coordinator_label = QLabel(
            f"Coordinator: {coordinator}{epoch}", self.content
        )
        self.coordinator_label.setWordWrap(True)
        self.coordinator_label.setAccessibleName("Coordinator and epoch")
        content_layout.addWidget(self.cluster_label)
        content_layout.addWidget(self.coordinator_label)

        section = QLabel("Members and known nodes", self.content)
        section.setProperty("role", "section")
        content_layout.addWidget(section)
        self.node_labels: dict[str, QLabel] = {}
        self.node_names: dict[str, QLabel] = {}
        self.action_buttons: dict[str, dict[str, QPushButton]] = {}
        self._node_rows: dict[str, QFrame] = {}
        self._summary = summary
        self._nodes: tuple[QtClusterNodeSpec, ...] = ()
        self._content_layout = content_layout
        seen: set[str] = set()
        for node in nodes:
            if node.node_id in seen:
                raise ValueError(f"Duplicate cluster node id: {node.node_id}")
            seen.add(node.node_id)
            self._add_node(node)
        self._nodes = tuple(nodes)
        content_layout.addStretch(1)

    def refresh(
        self,
        summary: QtClusterSummary,
        nodes: Sequence[QtClusterNodeSpec],
    ) -> None:
        """Replace the projected cluster state while retaining this page widget."""

        node_specs = tuple(nodes)
        node_ids = [node.node_id for node in node_specs]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Duplicate cluster node id")
        self._summary = summary
        self.cluster_label.setText(f"Cluster: {summary.cluster_id}")
        coordinator = summary.coordinator_id or "Not reported"
        epoch = f" · Epoch {summary.epoch}" if summary.epoch is not None else ""
        self.coordinator_label.setText(f"Coordinator: {coordinator}{epoch}")
        for node_id, row in tuple(self._node_rows.items()):
            self._content_layout.removeWidget(row)
            row.deleteLater()
            del self._node_rows[node_id]
        self.node_labels.clear()
        self.node_names.clear()
        self.action_buttons.clear()
        for node in node_specs:
            self._add_node(node)
        self._nodes = node_specs

    def _add_node(self, node: QtClusterNodeSpec) -> None:
        row = QFrame(self.content)
        row.setObjectName("cluster-node-row")
        row.setFrameShape(QFrame.Shape.StyledPanel)
        row.setMinimumWidth(0)
        row.setStyleSheet(
            "QFrame#cluster-node-row { border: 1px solid "
            f"{self.colors['border']}; border-radius: 4px; }}"
        )
        layout = QVBoxLayout(row)
        layout.setContentsMargins(
            *(
                ui_styles.SPACING[key]
                for key in ("card_pad_x", "card_pad_y", "card_pad_x", "card_pad_y")
            )
        )
        name = QLabel(node.display_name, row)
        name.setWordWrap(True)
        name.setMinimumWidth(0)
        name.setProperty("role", "section")
        name.setAccessibleName(f"Node {node.display_name}")
        roles = (
            ", ".join(node.roles) if node.cluster_member else "No cluster assignment"
        )
        membership = (
            f"Cluster member · {roles}"
            if node.cluster_member
            else "Not in cluster · No cluster assignment"
        )
        pieces = [
            f"Trust: {node.trust_state}",
            f"Connection: {node.connection_state}",
            membership,
        ]
        if node.paused:
            pieces.append("Paused")
        if node.hostname and node.hostname != node.display_name:
            pieces.append(f"Host: {node.hostname}")
        if node.cluster_member and node.coordinator_id and "Worker" in node.roles:
            pieces.append(f"Coordinator: {node.coordinator_id}")
        details = QLabel(" · ".join(pieces), row)
        details.setObjectName("cluster-node-state")
        details.setWordWrap(True)
        details.setMinimumWidth(0)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(name)
        layout.addWidget(details)
        self.node_labels[node.node_id] = details
        self.node_names[node.node_id] = name
        self._node_rows[node.node_id] = row
        buttons: dict[str, QPushButton] = {}
        actions_row = QHBoxLayout()
        actions_row.addStretch(1)
        for action in node.actions:
            if not action.visible:
                continue
            button = QPushButton(action.label, row)
            button.setProperty("role", "neutral")
            button.setAccessibleName(f"{action.label} {node.display_name}")
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            callback = self.callbacks.on_action.get(action.key)
            button.setEnabled(action.enabled and callback is not None)
            if callback is not None:
                button.clicked.connect(
                    lambda _checked=False, callback=callback, node_id=node.node_id, intent=action.confirmation_intent: (
                        callback(node_id, intent)
                    )
                )
            actions_row.addWidget(button)
            buttons[action.key] = button
        if buttons:
            layout.addLayout(actions_row)
        self.action_buttons[node.node_id] = buttons
        cast(QVBoxLayout, self.content.layout()).addWidget(row)

    def focus_back(self) -> None:
        """Move keyboard focus to the page's predictable return control."""

        self.back_button.setFocus()
