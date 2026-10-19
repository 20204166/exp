"""Behavioral tests for the standalone Qt settings migration surfaces."""

import unittest
from unittest.mock import Mock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout

from maintenance.preferences import AppPreferences
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.qt_settings import (
    QtPreferencesPage,
    QtSettingsCategorySpec,
    QtSettingsHome,
)
from tests.support.qt import get_qapplication


class QtSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def test_settings_home_is_navigation_only_and_preserves_order(self) -> None:
        selected = Mock()
        home = QtSettingsHome(
            [
                QtSettingsCategorySpec("preferences", "Preferences", "Configure"),
                QtSettingsCategorySpec("help", "Help & Guide", "Read help"),
            ],
            on_select_category=selected,
        )
        self.assertEqual(home.category_keys, ("preferences", "help"))
        self.assertEqual(home.selected_category, "preferences")
        home.category_buttons["help"].click()
        selected.assert_called_once_with("help")
        self.assertEqual(home.selected_category, "help")
        card = home.findChild(QFrame, "settings-category-card")
        self.assertIsNotNone(card)
        assert card is not None
        self.assertIn("QFrame#settings-category-card", card.styleSheet())
        self.assertFalse(
            home.findChildren(type(home.category_buttons["help"]))[0].text()
            == "Show card"
        )
        home.close()

    def test_preferences_edits_and_refresh_from_emit_semantic_callbacks(self) -> None:
        callbacks = Mock()
        page = QtPreferencesPage(
            callbacks=callbacks,
            intervals=[
                ("cpu", "CPU", 1, 1, 60, 1),
                ("storage", "Storage", 30, 15, 600, 5),
            ],
            cards=[("cpu", "CPU", True), ("battery", "Battery", False)],
            hide_unavailable_cards=True,
        )
        page.interval_controls["cpu"].setValue(60)
        page.interval_controls["cpu"].editingFinished.emit()
        callbacks.on_interval_commit.assert_called_once_with("cpu", 60)
        page.card_controls["cpu"].click()
        callbacks.on_card_visibility_change.assert_called_once_with("cpu", False)
        self.assertEqual(page.card_controls["cpu"].text(), "")
        page.auto_hide_control.click()
        callbacks.on_auto_hide_change.assert_called_once_with(False)
        callbacks.reset_mock()
        page.refresh_from(AppPreferences.defaults())
        self.assertEqual(page.interval_controls["cpu"].value(), 1)
        self.assertTrue(page.card_controls["battery"].isChecked())
        self.assertFalse(page.auto_hide_control.isChecked())
        callbacks.on_interval_commit.assert_not_called()
        callbacks.on_card_visibility_change.assert_not_called()
        callbacks.on_auto_hide_change.assert_not_called()
        page.close()

    def test_interval_bounds_are_enforced_and_controls_are_accessible(self) -> None:
        callbacks = Mock()
        page = QtPreferencesPage(
            callbacks=callbacks,
            intervals=[("storage", "Long storage refresh interval", 30, 15, 600, 5)],
            cards=[],
            hide_unavailable_cards=False,
        )
        control = page.interval_controls["storage"]
        self.assertEqual(
            (control.minimum(), control.maximum(), control.singleStep()), (15, 600, 5)
        )
        self.assertTrue(control.accessibleName())
        self.assertTrue(control.focusPolicy() & Qt.FocusPolicy.TabFocus)
        page.resize(900, 400)
        page.show()
        self.app.processEvents()
        self.assertIsNotNone(page.findChild(type(page.scroll_area)))
        page.close()

    def test_preference_apply_and_save_semantics_are_callback_owned(self) -> None:
        callbacks = Mock()
        page = QtPreferencesPage(
            callbacks=callbacks,
            intervals=[("cpu", "CPU", 1, 1, 60, 1)],
            cards=[],
            hide_unavailable_cards=False,
        )
        page.interval_controls["cpu"].setValue(2)
        page.interval_controls["cpu"].editingFinished.emit()
        callbacks.on_interval_commit.assert_called_once_with("cpu", 2)
        self.assertFalse(hasattr(page, "preferences_store"))
        page.close()

    def test_manual_scan_uses_coordinator_and_exposes_progress_state(self) -> None:
        callbacks = Mock()
        coordinator = ButtonCoordinator()
        page = QtPreferencesPage(
            callbacks=callbacks,
            intervals=[],
            cards=[],
            hide_unavailable_cards=False,
            button_coordinator=coordinator,
        )
        self.assertIn("preferences:scan", coordinator.registered_ids())
        self.assertIn("preferences:cancel-scan", coordinator.registered_ids())
        self.assertTrue(page.scan_button.isEnabled())
        self.assertFalse(page.cancel_button.isEnabled())
        page.scan_button.click()
        callbacks.on_scan.assert_called_once_with()
        callbacks.reset_mock()
        page.set_scan_busy()
        self.assertFalse(page.scan_button.isEnabled())
        self.assertTrue(page.cancel_button.isEnabled())
        page.set_scan_progress("CPU", 2, 6)
        self.assertEqual(page.manual_progress_bar.value(), 2)
        self.assertEqual(page.manual_status_label.text(), "●  CPU (2/6)")
        page.set_scan_ready()
        self.assertTrue(page.scan_button.isEnabled())
        self.assertFalse(page.cancel_button.isEnabled())
        page.close()

    def test_responsive_content_and_long_text_scroll(self) -> None:
        page = QtPreferencesPage(
            callbacks=Mock(),
            intervals=[],
            cards=[("hardware", "Hardware with a deliberately long label " * 8, True)],
            hide_unavailable_cards=False,
        )
        for width in (900, 1280, 1600):
            page.resize(width, 360)
            page.show()
            self.app.processEvents()
            self.assertGreaterEqual(page.width(), width - 10)
        self.assertTrue(page.scroll_area.widgetResizable())
        page_layout = page.layout()
        assert isinstance(page_layout, QVBoxLayout)
        self.assertGreaterEqual(page_layout.indexOf(page.scroll_area), 0)
        page.close()


if __name__ == "__main__":
    unittest.main()
