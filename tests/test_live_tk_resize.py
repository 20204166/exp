"""Guarded live-Tk resize tests, skipped automatically when no display exists.

These exercise the resize-aware layout on real widgets (adaptive card wraps,
detail-dialog subtitle wrapping, dialog descriptions that keep their default
wrap at normal sizes and narrow at minimum sizes). They are skipped cleanly
in headless environments where a Tk root cannot be created.
"""

import tkinter as tk
import unittest
from typing import Any
from unittest.mock import Mock, patch

from maintenance.dialogs import (
    InfoDialog,
    ProcessDialog,
    ResourceCard,
    StorageDialog,
)
from maintenance.models import ResourceSummary
from tests.support.live_tk import (
    DISPLAY_AVAILABLE,
    TEST_COLORS,
    labels,
    pump,
    walk_widgets,
)


@unittest.skipUnless(DISPLAY_AVAILABLE, "no display for live Tk tests")
class LiveResizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()

    def tearDown(self) -> None:
        try:
            self.root.destroy()
        except (tk.TclError, RuntimeError):
            pass

    def _pump(self) -> None:
        pump(self.root)

    def _gpu_summary(self) -> ResourceSummary:
        return ResourceSummary(
            key="gpu",
            title="GPU",
            value="AMD Radeon Vega Series / Radeon Vega Mobile Series",
            subtitle=(
                "Advanced Micro Devices, Inc. [AMD/ATI] Picasso "
                "[Radeon Vega Series / Radeon Vega Mobile Series] (rev da)"
            ),
            percent=42.0,
            details=("GPU usage: 42%",),
        )

    def test_card_wrap_tracks_width_with_hysteresis(self) -> None:
        card = ResourceCard(
            self.root,
            key="gpu",
            title="GPU",
            on_open=lambda _key: None,
            colors=TEST_COLORS,
        )
        card.update_summary(self._gpu_summary())
        card.pack(fill="x", padx=30)

        for width in (900, 700):
            self.root.geometry(f"{width}x700+0+0")
            self._pump()
            expected = card.winfo_width() - 36
            actual = card.value_label.cget("wraplength")
            self.assertLessEqual(abs(actual - expected), 12)
            self.assertEqual(len(card.metric_rows), 1)
            metric_wrap = card.metric_rows[0][2].cget("wraplength")
            self.assertLessEqual(abs(metric_wrap - (expected - 130)), 12)

        card.destroy()
        self._pump()

    def test_info_dialog_subtitle_wraps(self) -> None:
        summary = self._gpu_summary()
        dialog = InfoDialog(self.root, summary=summary, colors=TEST_COLORS)
        dialog.geometry("560x360+0+0")
        self._pump()

        subtitle = next(
            label for label in labels(dialog) if label.cget("text") == summary.subtitle
        )
        self.assertEqual(subtitle.cget("wraplength"), InfoDialog.DETAIL_WRAPLENGTH)
        dialog.destroy()
        self._pump()

    def _process_dialog(self) -> Any:
        with patch(
            "maintenance.dialogs.run_in_thread",
            side_effect=lambda *args, **kwargs: None,
        ):
            return ProcessDialog(
                self.root,
                analyzer=Mock(),
                manager=Mock(),
                resource_key="cpu",
                colors=TEST_COLORS,
                on_changed=lambda: None,
            )

    def test_process_description_keeps_default_wrap_at_normal_size(self) -> None:
        dialog = self._process_dialog()
        dialog.geometry("900x560+0+0")
        self._pump()

        description = next(
            label
            for label in labels(dialog)
            if label.cget("text").startswith("Select user processes")
        )
        self.assertEqual(description.cget("wraplength"), 800)
        dialog.destroy()
        self._pump()

    def test_process_description_narrows_at_minimum_size(self) -> None:
        dialog = self._process_dialog()
        dialog.geometry("760x560+0+0")
        self._pump()

        description = next(
            label
            for label in labels(dialog)
            if label.cget("text").startswith("Select user processes")
        )
        wrap = description.cget("wraplength")
        self.assertGreaterEqual(wrap, 700)
        self.assertLess(wrap, 800)
        dialog.destroy()
        self._pump()

    def test_storage_description_keeps_default_wrap_at_normal_size(self) -> None:
        with patch(
            "maintenance.dialogs.run_in_thread",
            side_effect=lambda *args, **kwargs: None,
        ):
            dialog = StorageDialog(
                self.root,
                analyzer=Mock(),
                manager=Mock(),
                colors=TEST_COLORS,
                on_changed=lambda: None,
            )
        dialog.geometry("980x580+0+0")
        self._pump()

        description = next(
            label
            for label in labels(dialog)
            if label.cget("text").startswith("Find large files")
        )
        self.assertEqual(description.cget("wraplength"), 860)
        dialog.destroy()
        self._pump()

    def test_dashboard_cards_adapt_at_startup(self) -> None:
        from window import AppWindow

        window = AppWindow(master=self.root)
        for identifier in tuple(window._pending_after_ids):
            window._cancel_timer(identifier)
        self._pump()

        card = window.cards["cpu"]
        expected = card.winfo_width() - 36
        actual = card.value_label.cget("wraplength")
        self.assertLessEqual(abs(actual - expected), 12)

        window._close()
        self.root = tk.Tk()

    def test_settings_home_preferences_navigation_and_state(self) -> None:
        import tempfile
        from pathlib import Path

        from maintenance.preferences import PreferencesStore
        from window import AppWindow

        with tempfile.TemporaryDirectory() as directory:
            store = PreferencesStore(Path(directory) / "preferences.json")
            window = AppWindow(master=self.root, preferences_store=store)
            for identifier in tuple(window._pending_after_ids):
                window._cancel_timer(identifier)
            self._pump()

            # Dashboard -> Settings Home
            self.assertEqual(window._page_router.active_key, "dashboard")
            window._show_settings_page()
            self._pump()
            self.assertEqual(window._page_router.active_key, "settings")
            self.assertTrue(window._page_router.is_mapped("settings"))
            self.assertFalse(window._page_router.is_mapped("dashboard"))
            self.assertFalse(window._page_router.is_mapped("preferences"))

            # Settings Home is a lightweight hub: no preference controls
            home = window.settings_home
            self.assertIsNotNone(home.canvas)
            self.assertEqual(
                len(
                    [
                        widget
                        for widget in walk_widgets(home.content)
                        if widget.winfo_class() in ("TSpinbox", "TCheckbutton")
                    ]
                ),
                0,
            )
            self.assertEqual(
                home.category_keys,
                ("preferences", "nodes", "cluster"),
            )

            # Settings Home -> Preferences page (real navigation via the card button)
            home.category_button("preferences").invoke()
            self._pump()
            self.assertEqual(window._page_router.active_key, "preferences")
            self.assertTrue(window._page_router.is_mapped("preferences"))
            self.assertFalse(window._page_router.is_mapped("settings"))

            page = window.preferences_page
            self.assertIsNotNone(page.canvas)
            spinboxes = [
                widget
                for widget in walk_widgets(page.content)
                if widget.winfo_class() == "TSpinbox"
            ]
            self.assertEqual(len(spinboxes), 6)

            # Preferences -> Back to Settings Home
            page.back_button.invoke()
            self._pump()
            self.assertEqual(window._page_router.active_key, "settings")
            self.assertTrue(window._page_router.is_mapped("settings"))
            self.assertFalse(window._page_router.is_mapped("preferences"))

            # Settings Home -> Back to System Overview
            home.back_button.invoke()
            self._pump()
            self.assertEqual(window._page_router.active_key, "dashboard")
            self.assertTrue(window._page_router.is_mapped("dashboard"))

            # Repeated navigation retains page instances and state
            first_preferences = window.preferences_page
            first_home = window.settings_home
            window._show_settings_page()
            window._show_preferences_page()
            self._pump()
            self.assertIs(window.preferences_page, first_preferences)
            self.assertIs(window.settings_home, first_home)
            self.assertEqual(
                window._page_router.registered_keys,
                ("dashboard", "settings", "preferences", "nodes", "cluster"),
            )

            # Navigation alone starts no scans. Active mDNS discovery keeps the
            # UI delivery poll alive so transport callbacks reach Tk safely.
            self.assertEqual(len(window._pending_after_ids), 0)
            self.assertIsNone(window._component_poll_id)
            if window._discovery_tick_id is None:
                self.assertIsNone(window._background_poll_id)
            else:
                self.assertIsNotNone(window._background_poll_id)
            self.assertEqual(window._background_tasks, 0)

            window._close()
        self.root = tk.Tk()

    def test_preferences_page_reachable_at_narrow_and_maximised_sizes(self) -> None:
        import tempfile
        from pathlib import Path

        from maintenance.preferences import PreferencesStore
        from window import AppWindow

        with tempfile.TemporaryDirectory() as directory:
            store = PreferencesStore(Path(directory) / "preferences.json")
            window = AppWindow(master=self.root, preferences_store=store)
            for identifier in tuple(window._pending_after_ids):
                window._cancel_timer(identifier)

            for geometry in ("900x680+0+0", "1200x900+0+0"):
                self.root.geometry(geometry)
                window._show_settings_page()
                self._pump()
                self.assertEqual(window._page_router.active_key, "settings")
                home = window.settings_home
                self.assertIsNotNone(home.canvas)
                self.assertIsNotNone(home.back_button)

                window._show_preferences_page()
                self._pump()
                self.assertEqual(window._page_router.active_key, "preferences")
                page = window.preferences_page
                self.assertIsNotNone(page.canvas)
                spinboxes = [
                    widget
                    for widget in walk_widgets(page.content)
                    if widget.winfo_class() == "TSpinbox"
                ]
                self.assertEqual(len(spinboxes), 6)
                page.back_button.invoke()
                self._pump()
                self.assertEqual(window._page_router.active_key, "settings")

            window._close()
        self.root = tk.Tk()


if __name__ == "__main__":
    unittest.main()
