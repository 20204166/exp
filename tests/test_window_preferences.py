"""Tests for toolkit-independent preference event handling."""

from __future__ import annotations

import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from maintenance.preferences import AppPreferences, PreferencesSaveError
from maintenance.ui.window_preferences import apply_preferences, on_interval_commit


class WindowPreferencesTests(unittest.TestCase):
    def make_controller(self, *, save: Mock | None = None) -> SimpleNamespace:
        preferences = AppPreferences.defaults()
        page = SimpleNamespace(
            refresh_from=Mock(), show_error=Mock(), show_status=Mock()
        )
        return SimpleNamespace(
            _preferences=preferences,
            _preferences_store=SimpleNamespace(save=save or Mock()),
            _reconcile_intervals=Mock(),
            _reconcile_cards_and_polling=Mock(),
            _apply_appearance=Mock(),
            _request_component_refresh=Mock(),
            preferences_page=page,
        )

    def test_commit_saves_before_publishing_and_reconciling(self) -> None:
        controller = self.make_controller()
        candidate = controller._preferences.with_interval("cpu", 5000)

        apply_preferences(controller, candidate)

        controller._preferences_store.save.assert_called_once_with(candidate)
        self.assertIs(controller._preferences, candidate)
        controller._reconcile_intervals.assert_called_once_with()
        controller._reconcile_cards_and_polling.assert_called_once_with()
        controller._apply_appearance.assert_called_once_with()
        controller.preferences_page.show_status.assert_called_once_with(
            "Preferences saved"
        )

    def test_save_failure_keeps_previous_preferences_and_reports_error(self) -> None:
        save = Mock(side_effect=PreferencesSaveError("disk full"))
        controller = self.make_controller(save=save)
        previous = controller._preferences
        candidate = previous.with_interval("cpu", 5000)

        apply_preferences(controller, candidate)

        self.assertIs(controller._preferences, previous)
        controller._reconcile_intervals.assert_not_called()
        controller._reconcile_cards_and_polling.assert_not_called()
        controller._apply_appearance.assert_not_called()
        controller.preferences_page.refresh_from.assert_called_once_with(previous)
        controller.preferences_page.show_error.assert_called_once_with(
            "Preferences could not be saved"
        )

    def test_invalid_interval_is_rejected_without_persisting(self) -> None:
        controller = self.make_controller()

        on_interval_commit(controller, "cpu", 0)

        controller._preferences_store.save.assert_not_called()
        controller._reconcile_intervals.assert_not_called()
        controller.preferences_page.show_error.assert_called_once()
        controller.preferences_page.refresh_from.assert_called_once_with(
            controller._preferences
        )

    def test_fresh_process_commit_does_not_import_tk_or_legacy_window(self) -> None:
        script = """
import sys
n = len(sys.path)
from types import SimpleNamespace
from maintenance.preferences import AppPreferences
from maintenance.ui.window_preferences import apply_preferences
controller = SimpleNamespace(
    _preferences=AppPreferences.defaults(),
    _preferences_store=SimpleNamespace(save=lambda value: None),
    _reconcile_intervals=lambda: None,
    _reconcile_cards_and_polling=lambda: None,
    _apply_appearance=lambda: None,
    preferences_page=SimpleNamespace(refresh_from=lambda value: None, show_status=lambda value: None, show_error=lambda value: None),
)
apply_preferences(controller, controller._preferences.with_interval('cpu', 5000))
assert 'window' not in sys.modules
assert 'tkinter' not in sys.modules
"""
        completed = subprocess.run(
            [sys.executable, "-c", script], check=False, capture_output=True, text=True
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
