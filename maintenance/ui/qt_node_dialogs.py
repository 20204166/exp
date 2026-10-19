"""Isolated Qt dialogs for node connection, details, pairing, and sharing.

These widgets only render supplied state and emit explicit user intent through
callbacks. They do not perform network work or make trust/cluster decisions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from maintenance.ui import qt_layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.node_dialog_contracts import (
    ConnectionDialogCallbacks,
    NodeDetailsDialogCallbacks,
    NodeDetailsDialogSpec,
    PairingDialogSpec,
    SharingDialogCallbacks,
)


class _NodeDialog(QDialog):
    def __init__(
        self, parent: QWidget | None, *, title: str, colors: dict[str, str] | None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setAccessibleName(title)
        self.colors = ui_styles.COLORS if colors is None else colors
        ui_styles.configure_qt_styles(self, colors=self.colors)
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(
            ui_styles.SPACING["dialog_pad_x"],
            ui_styles.SPACING["dialog_pad_y"],
            ui_styles.SPACING["dialog_pad_x"],
            ui_styles.SPACING["dialog_pad_y"],
        )
        self.root_layout.setSpacing(ui_styles.SPACING["row_gap"])
        self._closed = False

    def _scroll_content(self) -> tuple[QScrollArea, QWidget]:
        self.scroll_area, content = ui_layout.qt_scrollable_area(self)
        self.scroll_area.setAccessibleName(f"{self.windowTitle()} details")
        self.root_layout.addWidget(self.scroll_area, 1)
        return self.scroll_area, content

    def _action_button(
        self,
        text: str,
        accessible_name: str,
        callback: Callable[[], object],
        *,
        role: str = "neutral",
        parent: QWidget | None = None,
    ) -> QPushButton:
        button = QPushButton(text, parent or self)
        button.setProperty("role", role)
        button.setAccessibleName(accessible_name)
        button.clicked.connect(callback)
        return button


class QtConnectionDialog(_NodeDialog):
    """Manual connection form preserving the existing local validation rules."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        callbacks: ConnectionDialogCallbacks | None = None,
        node_id: str | None = None,
        colors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent, title="Add Connection", colors=colors)
        self.callbacks = callbacks or ConnectionDialogCallbacks()
        self.node_id = node_id
        form = QFormLayout()
        self.name_input = QLineEdit(self)
        self.host_input = QLineEdit(self)
        self.port_input = QLineEdit(self)
        self.name_input.setAccessibleName("Display name")
        self.host_input.setAccessibleName("Host")
        self.port_input.setAccessibleName("Port")
        self.port_input.setInputMethodHints(Qt.InputMethodHint.ImhDigitsOnly)
        form.addRow("Display name", self.name_input)
        form.addRow("Host", self.host_input)
        form.addRow("Port", self.port_input)
        self.root_layout.addLayout(form)
        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Connection form status")
        self.status_label.setProperty("role", "danger")
        self.root_layout.addWidget(self.status_label)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.test_button: QPushButton | None = None
        if node_id is not None and self.callbacks.on_test is not None:
            self.test_button = self._action_button(
                "Test connection",
                "Test connection",
                self.test_connection,
                parent=self,
            )
            footer.addWidget(self.test_button)
        self.add_button: QPushButton | None = None
        if self.callbacks.on_add is not None:
            self.add_button = self._action_button(
                "Add", "Add connection", self.submit, role="primary", parent=self
            )
            footer.addWidget(self.add_button)
        self.root_layout.addLayout(footer)
        self.setMinimumSize(360, 220)
        self.resize(460, 320)

    def submit(self) -> None:
        callback = self.callbacks.on_add
        if callback is None:
            self.close()
            return
        name = self.name_input.text().strip()
        host = self.host_input.text().strip()
        port_text = self.port_input.text().strip()
        if not host:
            self.status_label.setText("Host is required.")
            return
        if port_text:
            try:
                port = int(port_text)
            except ValueError:
                self.status_label.setText("Port must be a number.")
                return
            if not 0 <= port <= 65535:
                self.status_label.setText("Port must be between 0 and 65535.")
                return
        else:
            port = None
        self.status_label.clear()
        callback(name, host, port)
        self.close()

    def test_connection(self) -> None:
        if self.node_id is not None and self.callbacks.on_test is not None:
            self.callbacks.on_test(self.node_id)


class QtNodeDetailsDialog(_NodeDialog):
    """Scrollable read-only projection of a node spec and explicitly allowed actions."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        spec: NodeDetailsDialogSpec,
        callbacks: NodeDetailsDialogCallbacks | None = None,
        colors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent, title="Node Details", colors=colors)
        self.spec = spec
        self.callbacks = callbacks or NodeDetailsDialogCallbacks()
        _area, content = self._scroll_content()
        content_layout = cast(QVBoxLayout, content.layout())
        fields = (
            ("Name", spec.display_name),
            ("Node ID", spec.node_id),
            ("Hostname", spec.hostname),
            ("Host", spec.host),
            ("Port", "" if spec.port is None else str(spec.port)),
            ("Pairing", spec.pairing_state),
            ("Target", spec.target_state),
            ("Role", spec.role),
            ("Permissions", ", ".join(spec.permissions)),
            ("Selectable", "Yes" if spec.selectable else "No"),
            ("Openable", "Yes" if spec.openable else "No"),
            ("Manual host", "Yes" if spec.is_manual else "No"),
            ("Paused", "Yes" if spec.paused else "No"),
            ("Role editable", "Yes" if spec.role_editable else "No"),
            ("Active job", "Yes" if spec.has_active_job else "No"),
            ("Identity status", spec.identity_status),
        )
        form = QFormLayout()
        self.detail_labels: dict[str, QLabel] = {}
        for label, value in fields:
            detail = QLabel(value or "—", content)
            detail.setWordWrap(True)
            detail.setMinimumWidth(0)
            detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(f"{label}:", detail)
            self.detail_labels[label] = detail
        content_layout.addLayout(form)
        self.identity_fingerprint_label: QLabel | None = None
        self.transport_fingerprint_label: QLabel | None = None
        for attr, label, value in (
            (
                "identity_fingerprint_label",
                "Identity fingerprint",
                spec.identity_fingerprint,
            ),
            (
                "transport_fingerprint_label",
                "TLS transport fingerprint",
                spec.transport_fingerprint,
            ),
        ):
            if value:
                fingerprint = QLabel(f"{label}: {value}", content)
                fingerprint.setWordWrap(True)
                fingerprint.setMinimumWidth(0)
                fingerprint.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                fingerprint.setAccessibleName(label)
                content_layout.addWidget(fingerprint)
                setattr(self, attr, fingerprint)
        content_layout.addStretch(1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self._actions: dict[str, QPushButton] = {}
        action_specs: tuple[
            tuple[str, str, bool, Callable[[str], None] | None], ...
        ] = (
            ("open", "Open", spec.openable, self.callbacks.on_open),
            ("test", "Test connection", spec.selectable, self.callbacks.on_test),
            (
                "revoke",
                "Revoke",
                spec.role_editable and not spec.is_manual,
                self.callbacks.on_revoke,
            ),
            (
                "remove_connection",
                "Remove connection",
                spec.is_manual,
                self.callbacks.on_remove_connection,
            ),
            (
                "remove_job",
                "Remove job",
                spec.role_editable and not spec.is_manual and spec.has_active_job,
                self.callbacks.on_remove_job,
            ),
            (
                "pause",
                "Resume" if spec.paused else "Pause",
                spec.role_editable,
                self.callbacks.on_resume if spec.paused else self.callbacks.on_pause,
            ),
        )
        for action, text, allowed, callback in action_specs:
            if allowed and callback is not None:
                button = self._action_button(
                    text,
                    text,
                    lambda action=action: self.invoke_action(action),
                    role="danger" if action == "revoke" else "neutral",
                    parent=self,
                )
                self._actions[action] = button
                footer.addWidget(button)
        self.close_button = self._action_button(
            "Close", "Close node details", self.close, parent=self
        )
        footer.addWidget(self.close_button)
        self.root_layout.addLayout(footer)
        self.setMinimumSize(360, 260)
        self.resize(520, 520)

    def action(self, action: str) -> QPushButton | None:
        return self._actions.get(action)

    def invoke_action(self, action: str) -> None:
        button = self._actions.get(action)
        if button is None:
            return
        callback = {
            "open": self.callbacks.on_open,
            "test": self.callbacks.on_test,
            "revoke": self.callbacks.on_revoke,
            "remove_connection": self.callbacks.on_remove_connection,
            "remove_job": self.callbacks.on_remove_job,
            "pause": self.callbacks.on_resume
            if self.spec.paused
            else self.callbacks.on_pause,
        }[action]
        if callback is not None:
            callback(self.spec.node_id)


class QtPairingDialog(_NodeDialog):
    """Pairing prompt with presentation-only pending, error, and completion states."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        spec: PairingDialogSpec,
        on_pair: Callable[[str], None],
        on_cancel: Callable[[str], None] | None = None,
        on_complete: Callable[[str], None] | None = None,
        colors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent, title="Pair Node", colors=colors)
        self.spec = spec
        self._on_pair = on_pair
        self._on_cancel = on_cancel
        self._on_complete = on_complete
        self._pending = False
        self._completed = False
        name = QLabel(spec.display_name or spec.node_id, self)
        name.setProperty("role", "section")
        self.root_layout.addWidget(name)
        self.identity_fingerprint_label = QLabel(
            f"Identity fingerprint: {spec.identity_fingerprint or 'Unavailable'}", self
        )
        self.transport_fingerprint_label = QLabel(
            f"TLS transport fingerprint: {spec.transport_fingerprint or 'Unavailable'}",
            self,
        )
        for label in (
            self.identity_fingerprint_label,
            self.transport_fingerprint_label,
        ):
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.root_layout.addWidget(label)
        self.status_label = QLabel("Review this node before pairing.", self)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Pairing status")
        self.status_label.setProperty("role", "status")
        self.root_layout.addWidget(self.status_label)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.cancel_button = self._action_button(
            "Cancel", "Cancel pairing", self.close, parent=self
        )
        self.pair_button = self._action_button(
            "Pair", "Pair with node", self.confirm, role="primary", parent=self
        )
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.pair_button)
        self.root_layout.addLayout(footer)
        self.setMinimumSize(360, 240)
        self.resize(500, 340)

    def confirm(self) -> None:
        if not self._closed and not self._pending:
            self._on_pair(self.spec.node_id)

    def set_pending(self) -> None:
        if self._closed or self._completed:
            return
        self._pending = True
        self.status_label.setText("Waiting for target approval...")
        self.pair_button.setEnabled(False)

    def complete(self) -> None:
        if self._closed or self._completed:
            return
        self._completed = True
        self._pending = False
        if self._on_complete is not None:
            self._on_complete(self.spec.node_id)
        self.close()

    def show_error(self, message: str) -> None:
        if self._closed or self._completed:
            return
        self._pending = False
        self.status_label.setText(message)
        self.pair_button.setEnabled(True)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._notify_cancel()
        super().closeEvent(event)

    def reject(self) -> None:
        self._notify_cancel()
        super().reject()

    def _notify_cancel(self) -> None:
        if not self._closed:
            self._closed = True
            if not self._completed and self._on_cancel is not None:
                self._on_cancel(self.spec.node_id)


class QtSharingDialog(_NodeDialog):
    """Explicit dashboard-sharing action with its existing five-minute wording."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        active: bool,
        callbacks: SharingDialogCallbacks,
        colors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent, title="Share Dashboard", colors=colors)
        self.active = active
        heading = QLabel("Dashboard sharing", self)
        heading.setProperty("role", "section")
        self.root_layout.addWidget(heading)
        self.state_label = QLabel("Active" if active else "Inactive", self)
        self.state_label.setAccessibleName("Dashboard sharing state")
        self.root_layout.addWidget(self.state_label)
        duration = QLabel("Sharing duration: 5 minutes", self)
        duration.setWordWrap(True)
        self.root_layout.addWidget(duration)
        self.action_button = self._action_button(
            "Stop sharing" if active else "Share for 5 minutes",
            "Stop dashboard sharing" if active else "Share dashboard for 5 minutes",
            lambda: self.confirm(callbacks),
            role="danger" if active else "primary",
        )
        self.root_layout.addWidget(
            self.action_button, alignment=Qt.AlignmentFlag.AlignRight
        )
        self.setMinimumSize(340, 200)
        self.resize(420, 260)

    def confirm(self, callbacks: SharingDialogCallbacks) -> None:
        if self.active:
            accepted = callbacks.on_stop()
        else:
            accepted = callbacks.on_share()
        if accepted is not False:
            self.close()

    def set_active(self, active: bool) -> None:
        self.active = active
        self.state_label.setText("Active" if active else "Inactive")
        self.action_button.setText("Stop sharing" if active else "Share for 5 minutes")
        self.action_button.setAccessibleName(
            "Stop dashboard sharing" if active else "Share dashboard for 5 minutes"
        )
        self.action_button.setProperty("role", "danger" if active else "primary")
        self.action_button.style().unpolish(self.action_button)
        self.action_button.style().polish(self.action_button)
