"""Qt-only resource dialogs; all discovery and safe actions are injected."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from maintenance.models import FileCandidate, ProcessCandidate, ResourceSummary
from maintenance.ui import styles as ui_styles
from maintenance.ui.resource_details import detail_sections


def _colors(colors: dict[str, str]) -> dict[str, str]:
    return {**ui_styles.COLORS, **colors}


def _configure_dialog(dialog: QDialog, title: str, colors: dict[str, str]) -> None:
    dialog.setWindowTitle(title)
    dialog.setMinimumSize(620, 420)
    dialog.resize(900, 560)
    dialog.setStyleSheet(
        "QDialog { background: "
        + colors["background"]
        + "; color: "
        + colors["text"]
        + "; } QTableWidget { background: "
        + colors["card"]
        + "; gridline-color: "
        + colors["border"]
        + "; } QTableWidget::item:selected { background: "
        + colors.get("selection", "#E0E7FF")
        + "; color: "
        + colors["text"]
        + "; } QPushButton:focus, QLineEdit:focus, QTableWidget:focus { border: 2px solid "
        + colors.get("focus", colors["accent"])
        + "; }"
    )


def _base_layout(dialog: QDialog) -> QVBoxLayout:
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(
        ui_styles.SPACING["dialog_pad_x"],
        ui_styles.SPACING["dialog_pad_y"],
        ui_styles.SPACING["dialog_pad_x"],
        ui_styles.SPACING["dialog_pad_y"],
    )
    layout.setSpacing(ui_styles.SPACING["section_gap"])
    return layout


class _CloseAwareDialog(QDialog):
    def __init__(self, on_close: Callable[[], None], parent: QWidget | None = None):
        super().__init__(parent)
        self._on_close = on_close
        self._close_notified = False

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)
        if event.isAccepted():
            self._notify_close()

    def done(self, result: int) -> None:
        self._notify_close()
        super().done(result)

    def _notify_close(self) -> None:
        if not self._close_notified:
            self._close_notified = True
            self._on_close()


class QtInfoDialog(_CloseAwareDialog):
    """Scrollable read-only presentation of an existing resource summary."""

    def __init__(
        self,
        summary: ResourceSummary,
        *,
        on_close: Callable[[], None],
        colors: dict[str, str],
    ) -> None:
        super().__init__(on_close)
        self.summary = summary
        self.colors = _colors(colors)
        _configure_dialog(self, f"{summary.title} Details", self.colors)
        self.setAccessibleName(f"{summary.title} details dialog")
        self.setAccessibleDescription(" ".join(summary.details))
        layout = _base_layout(self)
        heading = QLabel(summary.title, self)
        heading.setStyleSheet("font-size: 22px; font-weight: 700;")
        subtitle = QLabel(summary.subtitle, self)
        subtitle.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        if summary.value:
            value = QLabel(summary.value, self)
            value.setWordWrap(True)
            value.setStyleSheet("font-size: 20px; font-weight: 700;")
            layout.addWidget(value)

        self.details_scroll = QScrollArea(self)
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setAccessibleName("Resource details")
        body = QWidget(self.details_scroll)
        form = QFormLayout(body)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        groups = detail_sections(summary.key, summary.details)
        if not groups:
            form.addRow(QLabel("No further details available.", body))
        for section, pairs in groups:
            label = QLabel(section, body)
            label.setStyleSheet("font-weight: 700;")
            form.addRow(label)
            for name, value_text in pairs:
                name_label = QLabel(name, body) if name else QLabel("", body)
                value_label = QLabel(value_text, body)
                value_label.setWordWrap(True)
                value_label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                    | Qt.TextInteractionFlag.TextSelectableByKeyboard
                )
                form.addRow(name_label, value_label)
        self.details_scroll.setWidget(body)
        layout.addWidget(self.details_scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setAccessibleName(
            "Close details"
        )
        buttons.rejected.connect(self.close)
        buttons.accepted.connect(self.close)
        layout.addWidget(buttons)


class QtProcessDialog(_CloseAwareDialog):
    """Process candidate table; the shell owns scans, safety and actions."""

    COLUMNS = ("name", "pid", "memory", "cpu", "activity", "permission")
    HEADERS = ("Application / Process", "PID", "Memory", "CPU", "Activity", "Action")

    def __init__(
        self,
        *,
        resource_key: str,
        node_title: str,
        read_only: bool,
        on_refresh: Callable[[], None],
        on_quit: Callable[[list[int], dict[int, float]], None],
        on_force_quit: Callable[[list[int], dict[int, float]], None],
        on_close: Callable[[], None],
        colors: dict[str, str],
    ) -> None:
        title = "Memory Processes" if resource_key == "memory" else "CPU Processes"
        super().__init__(on_close)
        self.colors = _colors(colors)
        self.read_only = read_only
        self.on_refresh = on_refresh
        self.on_quit = on_quit
        self.on_force_quit = on_force_quit
        self._candidates: dict[int, ProcessCandidate] = {}
        self._busy = False
        self._unknown = False
        self._sort_column = "memory" if resource_key == "memory" else "cpu"
        self._sort_reverse = True
        _configure_dialog(self, f"{title} — {node_title}", self.colors)
        self.setAccessibleName(f"{title} dialog")
        layout = _base_layout(self)
        description = QLabel(
            "This node is read-only: processes can be reviewed but not terminated."
            if read_only
            else "Select user processes to request a normal quit. Protected processes cannot be selected.",
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Filter processes by name")
        self.search_edit.setAccessibleName("Filter processes by name")
        self.search_edit.textChanged.connect(self._render_processes)
        layout.addWidget(self.search_edit)
        self.table = QTableWidget(0, len(self.COLUMNS), self)
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setAccessibleName("Process candidates")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().sectionClicked.connect(self.sort_by)
        self.table.setWordWrap(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.table, 1)
        self.status_label = QLabel("No processes available for cleanup review.", self)
        self.status_label.setAccessibleName("Process status")
        layout.addWidget(self.status_label)
        footer = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.setAccessibleName("Refresh process candidates")
        self.refresh_button.clicked.connect(on_refresh)
        self.quit_button = QPushButton("Quit selected", self)
        self.quit_button.setAccessibleName("Request normal quit for selected processes")
        self.quit_button.clicked.connect(self.quit_selected)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.close)
        footer.addWidget(self.refresh_button)
        footer.addWidget(self.quit_button)
        footer.addStretch(1)
        footer.addWidget(close_button)
        layout.addLayout(footer)
        self._sync_controls()

    def update_candidates(self, candidates: Iterable[ProcessCandidate]) -> None:
        self._candidates = {item.pid: item for item in candidates}
        self._busy = False
        self._unknown = False
        self._render_processes()

    def _render_processes(self, _query: str = "") -> None:
        query = self.search_edit.text().casefold().strip()
        candidates = [
            item for item in self._candidates.values() if query in item.name.casefold()
        ]
        candidates.sort(key=self._sort_key, reverse=self._sort_reverse)
        self.table.setRowCount(0)
        for candidate in candidates:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                candidate.name,
                str(candidate.pid),
                _format_bytes(candidate.memory_bytes),
                f"{candidate.cpu_percent:.1f}%",
                candidate.activity,
                "Can quit" if candidate.action_allowed else "Protected",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, candidate.pid)
                if column == 1:
                    item.setData(Qt.ItemDataRole.UserRole + 1, candidate.pid)
                if not candidate.action_allowed:
                    item.setForeground(Qt.GlobalColor.darkGray)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self._sync_controls()

    def _sort_key(self, candidate: ProcessCandidate) -> str | int | float:
        return {
            "name": candidate.name.casefold(),
            "pid": candidate.pid,
            "memory": candidate.memory_bytes,
            "cpu": candidate.cpu_percent,
            "activity": (0 if candidate.activity == "Active" else 1),
            "permission": (0 if candidate.action_allowed else 1),
        }[self._sort_column]

    def sort_by(self, column_index: int) -> None:
        if not 0 <= column_index < len(self.COLUMNS):
            return
        column = self.COLUMNS[column_index]
        self._sort_reverse = (
            not self._sort_reverse
            if column == self._sort_column
            else column in ("pid", "memory", "cpu")
        )
        self._sort_column = column
        self._render_processes()

    def select_candidate(self, pid: int) -> bool:
        candidate = self._candidates.get(pid)
        if candidate is None or not candidate.action_allowed:
            return False
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == pid:
                self.table.selectionModel().select(
                    self.table.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
                return True
        return False

    def set_selected_pids(self, pids: Iterable[int]) -> None:
        self.table.clearSelection()
        for pid in pids:
            self.select_candidate(pid)

    def selected_candidates(self) -> list[ProcessCandidate]:
        selected: list[ProcessCandidate] = []
        for index in sorted(
            self.table.selectionModel().selectedRows(), key=lambda item: item.row()
        ):
            item = self.table.item(index.row(), 0)
            if item is None:
                continue
            pid = int(item.data(Qt.ItemDataRole.UserRole))
            candidate = self._candidates.get(pid)
            if candidate is not None and candidate.action_allowed:
                selected.append(candidate)
        return selected

    def _confirm(self, pids: list[int]) -> bool:
        names = ", ".join(self._candidates[pid].name for pid in pids[:5])
        if len(pids) > 5:
            names += f" and {len(pids) - 5} more"
        return (
            QMessageBox.question(
                self,
                "Quit selected processes?",
                f"Request a normal quit for: {names}?\n\nUnsaved work could be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _confirm_force(self, pids: list[int]) -> bool:
        return (
            QMessageBox.warning(
                self,
                "Force quit processes?",
                f"{len(pids)} process(es) did not quit normally. Force quit them now?\n\nUnsaved work may be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        )

    def quit_selected(self) -> None:
        if self.read_only or self._busy or self._unknown:
            return
        selected = self.selected_candidates()
        if not selected:
            self.status_label.setText("Select one or more processes marked Can quit.")
            return
        pids = [item.pid for item in selected]
        if self._confirm(pids):
            self._busy = True
            self.status_label.setText("Requesting a normal quit...")
            self._sync_controls()
            self.on_quit(pids, _create_times(selected))

    def request_force_quit(self, pids: Iterable[int]) -> None:
        selected = [
            self._candidates[pid]
            for pid in pids
            if pid in self._candidates and self._candidates[pid].action_allowed
        ]
        if self.read_only or self._busy or self._unknown or not selected:
            return
        force_pids = [item.pid for item in selected]
        if self._confirm_force(force_pids):
            self._busy = True
            self.status_label.setText("Force quitting selected processes...")
            self._sync_controls()
            self.on_force_quit(force_pids, _create_times(selected))

    def set_action_state(
        self, *, busy: bool = False, unknown: bool = False, message: str | None = None
    ) -> None:
        self._busy, self._unknown = busy, unknown
        if message:
            self.status_label.setText(message)
        elif unknown:
            self.status_label.setText(
                "Termination outcome unknown; refresh before acting again"
            )
        elif busy:
            self.status_label.setText("Process action in progress...")
        self._sync_controls()

    def set_action_result(self, message: str) -> None:
        self._busy = self._unknown = False
        self._sync_controls()
        self.status_label.setText(message)

    def _sync_controls(self) -> None:
        query = self.search_edit.text().strip()
        visible_count = self.table.rowCount()
        available = sum(item.action_allowed for item in self._visible_candidates())
        if self._unknown:
            text = "Termination outcome unknown; refresh before acting again"
        elif self._busy:
            text = "Process action in progress..."
        elif not self._candidates:
            text = "No processes available for cleanup review."
        elif not visible_count and query:
            text = f'No processes match "{query}"'
        elif not visible_count:
            text = "No processes available for cleanup review."
        else:
            text = f"{visible_count} shown • {available} available for review"
        if not self._busy and not self._unknown:
            self.status_label.setText(text)
        self.quit_button.setEnabled(
            not self.read_only
            and not self._busy
            and not self._unknown
            and available > 0
        )
        self.refresh_button.setEnabled(not self._busy)

    def _visible_candidates(self) -> list[ProcessCandidate]:
        return [
            self._candidates[int(item.data(Qt.ItemDataRole.UserRole))]
            for row in range(self.table.rowCount())
            if (item := self.table.item(row, 0)) is not None
        ]


class QtStorageDialog(_CloseAwareDialog):
    """Storage candidate review UI; receives candidate snapshots and callbacks."""

    def __init__(
        self,
        *,
        node_title: str,
        read_only: bool,
        scan_root_label: str | None,
        on_scan: Callable[[], None],
        on_cancel_scan: Callable[[], None],
        on_move_selected: Callable[[list[FileCandidate]], None],
        on_close: Callable[[], None],
        colors: dict[str, str],
    ) -> None:
        super().__init__(on_close)
        self.colors = _colors(colors)
        self.read_only = read_only
        self.scan_root_label = scan_root_label
        self.on_scan = on_scan
        self.on_cancel_scan = on_cancel_scan
        self.on_move_selected = on_move_selected
        self._candidates: list[FileCandidate] = []
        self._busy = False
        self._scan_busy = False
        self._cancel_requested = False
        _configure_dialog(self, f"Storage Cleanup — {node_title}", self.colors)
        self.setAccessibleName("Storage cleanup dialog")
        layout = _base_layout(self)
        description = (
            "This node is read-only: files can be reviewed but not moved to Trash."
            if read_only
            else f"Reviewing {scan_root_label or 'Downloads'}. Selected files require confirmation before dispatch."
        )
        label = QLabel(description, self)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(
            ("File path", "Reason", "Size", "Modified")
        )
        self.table.setAccessibleName("Storage cleanup candidates")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.status_label = QLabel("Ready to scan.", self)
        self.status_label.setAccessibleName("Storage scan status")
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setAccessibleName("Storage scan progress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        footer = QHBoxLayout()
        self.scan_button = QPushButton("Scan", self)
        self.scan_button.setAccessibleName("Start storage scan")
        self.scan_button.clicked.connect(on_scan)
        self.cancel_button = QPushButton("Cancel scan", self)
        self.cancel_button.setAccessibleName("Cancel storage scan")
        self.cancel_button.clicked.connect(self._request_cancel_scan)
        self.cancel_button.setEnabled(False)
        self.move_button = QPushButton("Move selected to Trash", self)
        self.move_button.setAccessibleName("Move selected files to Trash")
        self.move_button.clicked.connect(self.move_selected)
        self.move_button.setEnabled(False)
        self.table.itemSelectionChanged.connect(self._sync_move_enabled)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.close)
        for button in (self.scan_button, self.cancel_button, self.move_button):
            footer.addWidget(button)
        footer.addStretch(1)
        footer.addWidget(close_button)
        layout.addLayout(footer)

    def update_candidates(self, candidates: Iterable[FileCandidate]) -> None:
        self._candidates = list(candidates)
        self.table.setRowCount(0)
        for candidate in self._candidates:
            row = self.table.rowCount()
            self.table.insertRow(row)
            modified = candidate.modified_at
            if modified.tzinfo is not None:
                modified = modified.astimezone()
            values = (
                str(candidate.path),
                candidate.reason,
                _format_bytes(candidate.size_bytes),
                modified.strftime("%Y-%m-%d %H:%M"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.status_label.setText(
            "No cleanup candidates found."
            if not self._candidates
            else f"{len(self._candidates)} candidate(s) • up to {_format_bytes(sum(item.size_bytes for item in self._candidates))} reviewable"
        )
        self._sync_move_enabled()

    def set_scan_state(
        self,
        message: str,
        *,
        busy: bool,
        progress: int | None = None,
        error: bool = False,
    ) -> None:
        was_busy = self._scan_busy
        self._scan_busy = busy
        if not busy or not was_busy:
            self._cancel_requested = False
        self.status_label.setText(message)
        if error:
            self.status_label.setStyleSheet(f"color: {self.colors['danger']};")
        else:
            self.status_label.setStyleSheet("")
        self.progress_bar.setVisible(busy or progress is not None)
        if progress is not None:
            self.progress_bar.setValue(max(0, min(100, progress)))
        self.scan_button.setEnabled(not busy and not self._busy)
        self.cancel_button.setEnabled(busy and not self._cancel_requested)
        self._sync_move_enabled()

    def _request_cancel_scan(self) -> None:
        if not self._scan_busy or self._cancel_requested:
            return
        self._cancel_requested = True
        self.cancel_button.setEnabled(False)
        self.status_label.setText(
            f"Cancelling {self.scan_root_label or 'Downloads'} scan..."
        )
        self.on_cancel_scan()

    def set_action_state(self, *, busy: bool, message: str) -> None:
        self._busy = busy
        self.status_label.setText(message)
        self.scan_button.setEnabled(not busy and not self._scan_busy)
        self._sync_move_enabled()

    def _confirm_move(self, selected: list[FileCandidate]) -> bool:
        total = _format_bytes(sum(item.size_bytes for item in selected))
        return (
            QMessageBox.question(
                self,
                "Move files to Trash?",
                f"Move {len(selected)} selected file(s) ({total}) to Trash?\n\nThe files will not be permanently deleted.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        )

    def move_selected(self) -> None:
        if self.read_only or self._busy or self._scan_busy:
            return
        selected_rows = sorted(
            {index.row() for index in self.table.selectionModel().selectedRows()}
        )
        selected = [
            self._candidates[index]
            for index in selected_rows
            if index < len(self._candidates)
        ]
        if not selected:
            self.status_label.setText("Select one or more files to move to Trash.")
            return
        if self._confirm_move(selected):
            self._busy = True
            self.status_label.setText("Moving selected files to Trash...")
            self._sync_move_enabled()
            self.scan_button.setEnabled(False)
            self.on_move_selected(selected)

    def _sync_move_enabled(self) -> None:
        has_selection = bool(self.table.selectionModel().selectedRows())
        self.move_button.setEnabled(
            has_selection
            and not self.read_only
            and not self._busy
            and not self._scan_busy
        )


def _create_times(candidates: Iterable[ProcessCandidate]) -> dict[int, float]:
    return {
        item.pid: item.create_time
        for item in candidates
        if item.create_time is not None
    }


def _format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{amount:.2f} TiB"
