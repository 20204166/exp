"""Standalone Qt settings navigation and preferences widgets.

These presentation-only widgets coexist with the active Tk shell during
migration. Callbacks remain the controller's boundary for persistence/apply.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from maintenance.ui import qt_layout as ui_layout
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


def _layout(widget: QWidget) -> QLayout:
    """Return the layout installed by this module's widget constructors."""
    return cast(QLayout, widget.layout())


def _vertical_layout(widget: QWidget) -> QVBoxLayout:
    """Return a widget's known vertical layout with its concrete API intact."""
    return cast(QVBoxLayout, widget.layout())


def _horizontal_layout(widget: QWidget) -> QHBoxLayout:
    """Return a widget's known horizontal layout with its concrete API intact."""
    return cast(QHBoxLayout, widget.layout())


@dataclass(frozen=True, slots=True)
class QtSettingsCategorySpec:
    key: str
    title: str
    description: str


class QtSettingsHome(QWidget):
    """Navigation-only Settings category selector."""

    def __init__(
        self,
        categories: Iterable[QtSettingsCategorySpec],
        *,
        on_select_category: Callable[[str], None],
        on_back: Callable[[], None] | None = None,
        selected_category: str | None = None,
        button_coordinator: ButtonCoordinator | None = None,
        colors: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.colors = ui_styles.COLORS if colors is None else colors
        self.categories = tuple(categories)
        self._on_select_category = on_select_category
        if len({item.key for item in self.categories}) != len(self.categories):
            raise ValueError("Settings category keys must be unique")
        if selected_category is not None and selected_category not in {
            item.key for item in self.categories
        }:
            raise ValueError("Selected category must exist")
        self.selected_category = selected_category or (
            self.categories[0].key if self.categories else None
        )
        self.setAccessibleName("Settings categories")
        ui_styles.configure_qt_styles(self, colors=self.colors)
        root = QVBoxLayout(self)
        root.setContentsMargins(
            *(ui_styles.SPACING[k] for k in ("page_x", "page_y", "page_x", "page_y"))
        )
        title = QLabel("Settings", self)
        title.setProperty("role", "title")
        description = QLabel(
            "Application configuration and options. Choose a category to continue.",
            self,
        )
        description.setWordWrap(True)
        description.setProperty("role", "description")
        root.addWidget(title)
        root.addWidget(description)
        if on_back is not None:
            self.back_button = QPushButton("Back to System Overview", self)
            self.back_button.clicked.connect(on_back)
            self.back_button.setAccessibleName("Back to System Overview")
            root.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignLeft)
        else:
            self.back_button = None
        self.scroll_area, content = ui_layout.qt_scrollable_area(self)
        self.scroll_area.setAccessibleName("Settings categories")
        self.category_buttons: dict[str, QPushButton] = {}
        for item in self.categories:
            card = QFrame(content)
            card.setObjectName("settings-category-card")
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card.setStyleSheet(
                "QFrame#settings-category-card { border: 1px solid "
                f"{self.colors['border']}; border-radius: 4px; }}"
            )
            row = QHBoxLayout(card)
            text_column = QVBoxLayout()
            heading = QLabel(item.title, card)
            heading.setProperty("role", "section")
            detail = QLabel(item.description, card)
            detail.setWordWrap(True)
            detail.setProperty("role", "description")
            text_column.addWidget(heading)
            text_column.addWidget(detail)
            button = QPushButton("Open", card)
            button.setProperty("role", "neutral")
            button.setAccessibleName(f"Open {item.title}")
            button.clicked.connect(
                lambda _checked=False, key=item.key: self._select(key)
            )
            if button_coordinator is not None:
                action = f"settings:category:{item.key}"
                button_coordinator.register(
                    action, lambda key=item.key: self._select(key), replace=True
                )
                button_coordinator.bind(button, action)
            row.addLayout(text_column, 1)
            row.addWidget(button)
            _layout(content).addWidget(card)
            self.category_buttons[item.key] = button
        _vertical_layout(content).addStretch(1)
        root.addWidget(self.scroll_area, 1)

    @property
    def category_keys(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.categories)

    def _select(self, key: str) -> None:
        self.selected_category = key
        self._on_select_category(key)

    def focus_back(self) -> None:
        if self.back_button is not None:
            self.back_button.setFocus()


class QtPreferencesPage(QWidget):
    """Qt preference editor; emits semantic events and never persists itself.

    ``intervals`` entries are ``(key, title, value, minimum, maximum, step)``;
    ``cards`` entries are ``(key, title, enabled)``. Callback object methods
    mirror the existing preferences page controller contract.
    """

    def __init__(
        self,
        *,
        callbacks: Any,
        intervals: Iterable[tuple[str, str, int, int, int, int]],
        cards: Iterable[tuple[str, str, bool]],
        hide_unavailable_cards: bool,
        full_system_scan_enabled: bool = False,
        appearance: str = ui_styles.DEFAULT_APPEARANCE,
        appearance_options: Iterable[str] | None = None,
        button_coordinator: ButtonCoordinator | None = None,
        colors: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.callbacks = callbacks
        self.colors = ui_styles.COLORS if colors is None else colors
        self.button_coordinator = button_coordinator
        self._interval_specs = {entry[0]: entry[1:] for entry in intervals}
        self._card_specs = {entry[0]: entry[1:] for entry in cards}
        self._updating = False
        ui_styles.configure_qt_styles(self, colors=self.colors)
        root = QVBoxLayout(self)
        root.setContentsMargins(
            *(ui_styles.SPACING[k] for k in ("page_x", "page_y", "page_x", "page_y"))
        )
        root.addWidget(self._heading())
        self.back_button = QPushButton("Back to Settings", self)
        self.back_button.setAccessibleName("Back to Settings")
        self.back_button.clicked.connect(callbacks.on_back)
        root.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.scroll_area, self.content = ui_layout.qt_scrollable_area(self)
        root.addWidget(self.scroll_area, 1)
        self.interval_controls: dict[str, QSpinBox] = {}
        self.card_controls: dict[str, QCheckBox] = {}
        self._interval_committed: dict[str, int] = {}
        self._add_section(
            "Scanning",
            "How often each live component refreshes while the dashboard is open. Values are shown in seconds.",
        )
        for key, (title, value, minimum, maximum, step) in self._interval_specs.items():
            row, label = self._setting_row(title)
            spin = QSpinBox(row)
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)
            spin.setValue(value)
            spin.setAccessibleName(title)
            spin.setSuffix(" seconds")
            spin.setKeyboardTracking(False)
            spin.editingFinished.connect(lambda key=key: self._commit_interval(key))
            label.setBuddy(spin)
            _horizontal_layout(row).addWidget(spin)
            self.interval_controls[key] = spin
            self._interval_committed[key] = value
        self.full_system_scan_control = self._check_row(
            "Review my entire local system, not just Downloads",
            full_system_scan_enabled,
            callbacks.on_full_system_scan_change,
        )
        self._add_section(
            "Dashboard Cards",
            "Choose which cards appear on the overview. Cards you hide here stay hidden; automatic unavailable-card hiding only applies to hardware proven absent.",
        )
        for key, (title, enabled) in self._card_specs.items():
            control = self._check_row(
                f"Show {title} card",
                enabled,
                lambda checked, key=key: self._emit_card(key, checked),
            )
            self.card_controls[key] = control
        self._add_section(
            "Manual Scan",
            "Run a full system scan on demand. Scan state stays visible here and on the dashboard.",
        )
        actions = QWidget(self.content)
        action_row = QHBoxLayout(actions)
        self.scan_button = QPushButton("Scan System", actions)
        self.scan_button.setProperty("role", "primary")
        self.scan_button.setAccessibleName("Scan System")
        self.cancel_button = QPushButton("Cancel", actions)
        self.cancel_button.setProperty("role", "danger")
        self.cancel_button.setAccessibleName("Cancel scan")
        self.cancel_button.setEnabled(False)
        if button_coordinator is None:
            self.scan_button.clicked.connect(callbacks.on_scan)
            self.cancel_button.clicked.connect(callbacks.on_cancel_scan)
        action_row.addWidget(self.scan_button)
        action_row.addWidget(self.cancel_button)
        action_row.addStretch(1)
        if button_coordinator is not None:
            button_coordinator.register(
                "preferences:scan", callbacks.on_scan, replace=True
            )
            button_coordinator.bind(self.scan_button, "preferences:scan")
            button_coordinator.register(
                "preferences:cancel-scan",
                callbacks.on_cancel_scan,
                enabled=False,
                replace=True,
            )
            button_coordinator.bind(self.cancel_button, "preferences:cancel-scan")
        _layout(self.content).addWidget(actions)
        self.manual_status_label = QLabel("●  Ready", self.content)
        self.manual_status_label.setAccessibleName("Manual scan status")
        _layout(self.content).addWidget(self.manual_status_label)
        self.manual_progress_bar = QProgressBar(self.content)
        self.manual_progress_bar.setRange(0, 6)
        self.manual_progress_bar.setValue(0)
        self.manual_progress_bar.setTextVisible(False)
        self.manual_progress_bar.setAccessibleName("Manual scan progress")
        _layout(self.content).addWidget(self.manual_progress_bar)
        self._add_section(
            "Interface", "Interface behaviour and automatic layout options."
        )
        self.auto_hide_control = self._check_row(
            "Hide unavailable cards automatically",
            hide_unavailable_cards,
            callbacks.on_auto_hide_change,
        )
        appearance_row, appearance_label = self._setting_row("Accent theme")
        self.appearance_control = QComboBox(appearance_row)
        self.appearance_control.addItems(
            list(appearance_options or sorted(ui_styles.ACCENT_THEMES))
        )
        self.appearance_control.setCurrentText(appearance)
        self.appearance_control.setAccessibleName("Accent theme")
        appearance_label.setBuddy(self.appearance_control)
        _horizontal_layout(appearance_row).addWidget(self.appearance_control)
        if callbacks.on_appearance_change is not None:
            self.appearance_control.currentTextChanged.connect(
                callbacks.on_appearance_change
            )
        self.status_label = QLabel("", self)
        self.status_label.setAccessibleName("Preferences status")
        root.addWidget(self.status_label)
        self.reset_button = QPushButton("Reset Preferences to Defaults", self)
        self.reset_button.setProperty("role", "neutral")
        self.reset_button.setAccessibleName("Reset Preferences to Defaults")
        self.reset_button.clicked.connect(callbacks.on_reset)
        root.addWidget(self.reset_button, alignment=Qt.AlignmentFlag.AlignLeft)
        _vertical_layout(self.content).addStretch(1)

    def _heading(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Preferences", container)
        title.setProperty("role", "title")
        description = QLabel(
            "Configure how System Analyzer refreshes components, shows cards, and scans on demand.",
            container,
        )
        description.setWordWrap(True)
        description.setProperty("role", "description")
        layout.addWidget(title)
        layout.addWidget(description)
        return container

    def _section_heading(self, title: str) -> QLabel:
        label = QLabel(title, self.content)
        label.setProperty("role", "section")
        return label

    def _add_section(self, title: str, description: str) -> None:
        label = self._section_heading(title)
        _layout(self.content).addWidget(label)
        detail = QLabel(description, self.content)
        detail.setWordWrap(True)
        detail.setProperty("role", "description")
        _layout(self.content).addWidget(detail)

    def _setting_row(self, title: str) -> tuple[QWidget, QLabel]:
        row = QWidget(self.content)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, ui_styles.SPACING["row_gap"])
        label = QLabel(title, row)
        label.setWordWrap(True)
        layout.addWidget(label, 1)
        _layout(self.content).addWidget(row)
        return row, label

    def _check_row(
        self, title: str, value: bool, callback: Callable[[bool], None]
    ) -> QCheckBox:
        row, label = self._setting_row(title)
        check = QCheckBox("" if title.startswith("Show ") else "Enabled", row)
        check.setChecked(value)
        check.setAccessibleName(title)
        check.toggled.connect(
            lambda checked: None if self._updating else callback(checked)
        )
        label.setBuddy(check)
        _horizontal_layout(row).addWidget(check)
        return check

    def _emit_card(self, key: str, checked: bool) -> None:
        if not self._updating:
            self.callbacks.on_card_visibility_change(key, checked)

    def _commit_interval(self, key: str) -> None:
        value = self.interval_controls[key].value()
        self._interval_committed[key] = value
        if not self._updating:
            self.callbacks.on_interval_commit(key, value)

    def refresh_from(self, preferences: Any) -> None:
        self._updating = True
        try:
            for key, milliseconds in preferences.refresh_intervals.as_dict().items():
                control = self.interval_controls.get(key)
                if control is not None:
                    value = milliseconds // 1000
                    control.setValue(value)
                    self._interval_committed[key] = value
            for key, control in self.card_controls.items():
                control.setChecked(key in preferences.visible_cards)
            self.auto_hide_control.setChecked(preferences.hide_unavailable_cards)
            self.full_system_scan_control.setChecked(
                getattr(preferences, "full_system_scan_enabled", False)
            )
            self.appearance_control.setCurrentText(
                getattr(
                    preferences, "appearance", self.appearance_control.currentText()
                )
            )
        finally:
            self._updating = False

    def show_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setProperty("role", "success")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def show_error(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setProperty("role", "danger")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _set_scan_actions(self, *, scanning: bool) -> None:
        if self.button_coordinator is None:
            self.scan_button.setEnabled(not scanning)
            self.cancel_button.setEnabled(scanning)
            return
        self.button_coordinator.set_enabled("preferences:scan", not scanning)
        self.button_coordinator.set_enabled("preferences:cancel-scan", scanning)

    def set_scan_ready(self) -> None:
        apply_ready(self.manual_status_label)
        apply_reset(self.manual_progress_bar)
        self._set_scan_actions(scanning=False)

    def set_scan_busy(self) -> None:
        apply_scanning(self.manual_status_label)
        self._set_scan_actions(scanning=True)

    def set_scan_progress(self, message: str, count: int, total: int) -> None:
        apply_step(
            self.manual_status_label, self.manual_progress_bar, message, count, total
        )

    def set_scan_cancelled(self) -> None:
        apply_cancelling(self.manual_status_label)
        self._set_scan_actions(scanning=False)

    def set_scan_complete(self, value: int = 6) -> None:
        apply_complete(
            self.manual_status_label,
            self.manual_progress_bar,
            value,
            success_color=self.colors["success"],
        )
        self._set_scan_actions(scanning=False)

    def set_scan_error(self, message: str) -> None:
        apply_error(self.manual_status_label, message)
        self._set_scan_actions(scanning=False)

    def focus_back(self) -> None:
        self.back_button.setFocus()

    def scroll_to_top(self) -> None:
        self.scroll_area.verticalScrollBar().setValue(0)
