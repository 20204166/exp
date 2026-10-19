"""Behavioral tests for the isolated Qt dashboard migration surface."""

import unittest
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from maintenance.components.catalog import ResourceFeatureCatalog
from maintenance.models import (
    CapabilityState,
    ResourceSummary,
    unavailable_summary,
)
from maintenance.ui.qt_dashboard import QtDashboard
from maintenance.ui.styles import ACCENT_THEMES, accent_theme_colors
from tests.support.qt import get_qapplication


class QtDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def make_dashboard(self, **kwargs: Any) -> QtDashboard:
        dashboard = QtDashboard(ResourceFeatureCatalog().all(), **kwargs)
        dashboard.resize(900, 700)
        dashboard.show()
        self.app.processEvents()
        return dashboard

    def test_initial_empty_state_and_catalog_order(self) -> None:
        dashboard = self.make_dashboard()
        self.assertEqual(
            tuple(dashboard.cards),
            ("cpu", "memory", "storage", "gpu", "network", "battery"),
        )
        self.assertEqual(dashboard.status_label.text(), "●  Ready")
        self.assertFalse(dashboard.scan_progress.isVisible())
        self.assertEqual(
            [
                self._column_for(dashboard, dashboard.cards[key])
                for key in dashboard.cards
            ],
            [0, 1, 0, 1, 0, 1],
        )
        self.assertEqual(dashboard.cards["cpu"].value_label.text(), "—")
        self.assertEqual(dashboard.cards["cpu"].subtitle_label.text(), "No data yet")
        dashboard.close()

    def test_populated_summary_metrics_usage_and_status(self) -> None:
        dashboard = self.make_dashboard()
        dashboard.set_summaries(
            (
                ResourceSummary(
                    "cpu",
                    "CPU",
                    "45%",
                    "Processor load",
                    45,
                    ("Load: 45%", "Cores: 8"),
                    True,
                    capability=CapabilityState.SUPPORTED,
                ),
                unavailable_summary("gpu", "GPU"),
                ResourceSummary(
                    "battery",
                    "Battery",
                    "—",
                    "No battery",
                    None,
                    (),
                    capability=CapabilityState.UNSUPPORTED,
                ),
                ResourceSummary(
                    "network",
                    "Network",
                    "Unavailable",
                    "No read",
                    None,
                    (),
                    capability=CapabilityState.TEMPORARILY_UNAVAILABLE,
                ),
            )
        )
        cpu = dashboard.cards["cpu"]
        assert cpu.progress is not None
        self.assertEqual(cpu.value_label.text(), "45%")
        self.assertEqual(cpu.progress.value(), 45)
        self.assertEqual(cpu.details_button.text(), "Review and clean  →")
        self.assertEqual(cpu.metric_rows[0][0].text(), "Load")
        self.assertIn("Failed", dashboard.cards["gpu"].subtitle_label.text())
        self.assertIn("Unsupported", dashboard.cards["battery"].subtitle_label.text())
        self.assertIn(
            "Temporarily unavailable", dashboard.cards["network"].subtitle_label.text()
        )
        self.assertIsNone(dashboard.cards["gpu"].progress)
        dashboard.close()

    def test_card_visibility_and_action_dispatch(self) -> None:
        opened = []
        dashboard = self.make_dashboard(on_open=opened.append)
        dashboard.set_card_visible("network", False)
        self.assertFalse(dashboard.cards["network"].isVisible())
        dashboard.cards["cpu"].details_button.click()
        self.assertEqual(opened, ["cpu"])
        dashboard.close()

    def test_scan_states_include_progress_cancel_complete_and_error(self) -> None:
        dashboard = self.make_dashboard(on_scan=lambda: None, on_cancel=lambda: None)
        assert dashboard.scan_button is not None
        assert dashboard.cancel_button is not None
        dashboard.set_scan_ready()
        self.assertEqual(dashboard.status_label.text(), "●  Ready")
        self.assertTrue(dashboard.scan_button.isEnabled())
        self.assertFalse(dashboard.cancel_button.isEnabled())
        dashboard.set_scan_busy()
        self.assertEqual(dashboard.status_label.text(), "●  Scanning...")
        self.assertFalse(dashboard.scan_button.isEnabled())
        self.assertTrue(dashboard.cancel_button.isEnabled())
        self.assertTrue(dashboard.scan_progress.isVisible())
        dashboard.set_scan_progress("Memory", 2, 6)
        self.assertEqual(dashboard.status_label.text(), "●  Memory (2/6)")
        self.assertEqual(dashboard.scan_progress.value(), 2)
        dashboard.set_scan_cancelled()
        self.assertEqual(dashboard.status_label.text(), "●  Cancelling...")
        self.assertTrue(dashboard.scan_button.isEnabled())
        self.assertFalse(dashboard.cancel_button.isEnabled())
        dashboard.set_scan_complete(6)
        self.assertEqual(dashboard.status_label.text(), "● Scan complete")
        self.assertEqual(dashboard.scan_progress.value(), 6)
        dashboard.set_scan_error("Scan failed")
        self.assertEqual(dashboard.status_label.text(), "●  Scan failed")
        dashboard.close()

    def test_responsive_columns_at_supported_widths(self) -> None:
        dashboard = self.make_dashboard()
        for width, expected in ((390, 1), (900, 2), (1280, 3), (1600, 3)):
            dashboard.resize(width, 700)
            self.app.processEvents()
            positions = [
                self._column_for(dashboard, card) for card in dashboard.cards.values()
            ]
            self.assertEqual(positions, [index % expected for index in range(6)])
        dashboard.close()

    @staticmethod
    def _column_for(dashboard: QtDashboard, card: QWidget) -> int:
        position = dashboard.cards_layout.getItemPosition(
            dashboard.cards_layout.indexOf(card)
        )
        assert isinstance(position, tuple)
        column = position[1]
        assert isinstance(column, int)
        return column

    def test_dashboard_cards_remain_in_a_scrollable_area(self) -> None:
        from PySide6.QtWidgets import QScrollArea

        dashboard = self.make_dashboard()
        self.assertIsInstance(dashboard.cards_scroll, QScrollArea)
        self.assertTrue(dashboard.cards_scroll.widgetResizable())
        self.assertIs(dashboard.cards_scroll.widget(), dashboard.cards_host)
        dashboard.close()

    def test_wide_dashboard_cards_use_equal_width_columns(self) -> None:
        dashboard = self.make_dashboard()
        dashboard.set_summaries(
            (
                ResourceSummary(
                    "cpu",
                    "CPU",
                    "38%",
                    "Processor load",
                    38,
                    ("Load: 38%", "Cores: 8"),
                    True,
                ),
                ResourceSummary(
                    "memory",
                    "Memory",
                    "62%",
                    "In use",
                    62,
                    ("Used: 9.2 GB", "Total: 16 GB"),
                    True,
                ),
                unavailable_summary("gpu", "GPU"),
            )
        )
        dashboard.resize(1600, 700)
        self.app.processEvents()
        widths = [dashboard.cards[key].width() for key in ("cpu", "memory", "storage")]
        self.assertLessEqual(max(widths) - min(widths), 2)
        dashboard.close()

    def test_short_viewport_scrolls_instead_of_compressing_card_content(self) -> None:
        dashboard = self.make_dashboard()
        dashboard.set_summaries(
            (
                ResourceSummary(
                    "cpu",
                    "CPU",
                    "38%",
                    "Processor load",
                    38,
                    ("Load: 38%", "Cores: 8"),
                    True,
                ),
            )
        )
        self.app.processEvents()
        card = dashboard.cards["cpu"]
        self.assertGreaterEqual(card.height(), card.minimumSizeHint().height())
        self.assertGreater(dashboard.cards_scroll.verticalScrollBar().maximum(), 0)
        dashboard.close()

    def test_accessible_names_keyboard_focus_and_status_independent_of_accent(self):
        for theme in ACCENT_THEMES:
            colors = accent_theme_colors(theme)
            dashboard = self.make_dashboard(colors=colors)
            button = dashboard.cards["cpu"].details_button
            self.assertTrue(button.accessibleName())
            self.assertTrue(button.focusPolicy() & Qt.FocusPolicy.TabFocus)
            self.assertEqual(dashboard.status_label.text(), "●  Ready")
            dashboard.close()


if __name__ == "__main__":
    unittest.main()
