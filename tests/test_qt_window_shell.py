"""Qt main-window shell and retained page navigation contracts."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from PySide6.QtWidgets import QLabel, QWidget

from maintenance.ui.qt_window import QtWindowShell
from tests.support.qt import get_qapplication


class QtWindowShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def test_pages_are_retained_and_navigation_changes_active_page(self) -> None:
        shell = QtWindowShell(title="System Analyzer")
        dashboard = QLabel("Dashboard")
        settings = QLabel("Settings")
        shell.register_page("dashboard", dashboard)
        shell.register_page("settings", settings)
        shell.show()

        self.assertIs(shell.show_page("dashboard"), dashboard)
        shell.show_page("settings")

        self.assertEqual(shell.active_page, "settings")
        self.assertTrue(settings.isVisible())
        self.assertFalse(dashboard.isVisible())
        self.assertIs(shell.page("settings"), settings)
        shell.close()

    def test_close_callback_runs_once_even_after_repeated_close(self) -> None:
        on_close = Mock()
        shell = QtWindowShell(title="System Analyzer", on_close=on_close)

        shell.close()
        shell.close()

        on_close.assert_called_once_with()

    def test_unknown_page_does_not_change_active_page(self) -> None:
        shell = QtWindowShell(title="System Analyzer")
        dashboard = QWidget()
        shell.register_page("dashboard", dashboard)
        shell.show()
        shell.show_page("dashboard")

        with self.assertRaises(KeyError):
            shell.show_page("missing")

        self.assertEqual(shell.active_page, "dashboard")
        self.assertTrue(dashboard.isVisible())
        shell.close()


if __name__ == "__main__":
    unittest.main()
