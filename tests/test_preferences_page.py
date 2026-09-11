"""Focused headless tests for the reusable Preferences page adapter."""

import tkinter as tk
import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.ui import scan_status
from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.preferences_page import (
    CardControlSpec,
    IntervalControlSpec,
    PreferencesPage,
    PreferencesPageCallbacks,
)
from tests.support.widget_recording import (
    FakeVar,
    RecordingWidget,
    WidgetRecorder,
)

SECTION_TITLES = ("Scanning", "Dashboard Cards", "Manual Scan", "Interface")


def make_callbacks() -> Any:
    return PreferencesPageCallbacks(
        on_back=Mock(),
        on_interval_commit=Mock(),
        on_card_visibility_change=Mock(),
        on_auto_hide_change=Mock(),
        on_scan=Mock(),
        on_cancel_scan=Mock(),
        on_reset=Mock(),
    )


def make_page(
    callbacks: PreferencesPageCallbacks | None = None,
    button_coordinator: ButtonCoordinator | None = None,
) -> tuple[PreferencesPage, RecordingWidget, WidgetRecorder]:
    recorder = WidgetRecorder()
    parent = recorder.parent()
    page = PreferencesPage(
        parent,
        callbacks=callbacks or make_callbacks(),
        intervals=[
            IntervalControlSpec("cpu", "CPU", 1, 1, 60, 1),
            IntervalControlSpec("storage", "Storage", 30, 15, 600, 5),
        ],
        cards=[
            CardControlSpec("cpu", "CPU", True),
            CardControlSpec("battery", "Battery", True),
        ],
        hide_unavailable_cards=False,
        **recorder.page_kwargs(),
        spinbox_cls=recorder.spinbox_cls(),
        checkbutton_cls=recorder.checkbutton_cls(),
        combobox_cls=recorder.combobox_cls(),
        progressbar_cls=recorder.progressbar_cls(),
        button_coordinator=button_coordinator,
        var_factory=lambda: FakeVar(""),
        boolean_var_factory=lambda: FakeVar(False),
    )
    return page, parent, recorder


def cpu_spinbox(recorder: WidgetRecorder, page: PreferencesPage) -> RecordingWidget:
    return next(
        widget
        for widget in recorder.widgets("spinbox")
        if widget.kwargs.get("textvariable") is page._interval_vars["cpu"]
    )


class PreferencesPageTests(unittest.TestCase):
    def test_page_root_is_not_packed_by_the_page(self) -> None:
        _page, parent, _recorder = make_page()

        self.assertEqual(parent.pack_calls, [])

    def test_all_four_sections_are_rendered(self) -> None:
        _page, _parent, recorder = make_page()

        rendered = {
            widget.kwargs.get("text")
            for widget in recorder.widgets("label")
            if widget.kwargs.get("text") in SECTION_TITLES
        }
        self.assertEqual(rendered, set(SECTION_TITLES))

    def test_back_button_invokes_on_back(self) -> None:
        callbacks = make_callbacks()
        page, _parent, _recorder = make_page(callbacks)

        page.back_button.kwargs["command"]()

        callbacks.on_back.assert_called_once_with()

    def test_back_button_is_labelled_back_to_settings(self) -> None:
        page, _parent, _recorder = make_page()

        self.assertEqual(page.back_button.kwargs["text"], "Back to Settings")

    def test_header_is_preferences(self) -> None:
        _page, _parent, recorder = make_page()

        texts = {
            widget.kwargs.get("text")
            for widget in recorder.widgets("style_label")
            if widget.kwargs.get("text") is not None
        }
        self.assertIn("Preferences", texts)

    def test_interval_spinbox_uses_spec_range_and_unit(self) -> None:
        page, _parent, recorder = make_page()
        spin = cpu_spinbox(recorder, page)

        self.assertEqual(spin.kwargs["from_"], 1)
        self.assertEqual(spin.kwargs["to"], 60)
        self.assertEqual(spin.kwargs["increment"], 1)
        self.assertEqual(spin.kwargs["style"], "App.TSpinbox")
        self.assertEqual(page._interval_vars["cpu"].get(), "1")
        self.assertEqual(
            recorder.label_with_text("seconds").kwargs.get("text"),
            "seconds",
        )

    def test_interval_commit_emits_key_and_seconds(self) -> None:
        callbacks = make_callbacks()
        page, _parent, recorder = make_page(callbacks)
        page._interval_vars["cpu"].set("5")

        cpu_spinbox(recorder, page).kwargs["command"]()

        callbacks.on_interval_commit.assert_called_once_with("cpu", 5)

    def test_interval_commit_on_return_binding(self) -> None:
        callbacks = make_callbacks()
        page, _parent, recorder = make_page(callbacks)
        page._interval_vars["cpu"].set("7")

        cpu_spinbox(recorder, page).bindings["<Return>"](None)

        callbacks.on_interval_commit.assert_called_once_with("cpu", 7)

    def test_invalid_interval_restores_value_and_shows_error(self) -> None:
        callbacks = make_callbacks()
        page, _parent, recorder = make_page(callbacks)
        page._interval_vars["cpu"].set("not-a-number")

        cpu_spinbox(recorder, page).kwargs["command"]()

        callbacks.on_interval_commit.assert_not_called()
        self.assertEqual(page._interval_vars["cpu"].get(), "1")
        self.assertIn("whole number", page.status_label.config_options["text"])
        self.assertEqual(
            page.status_label.config_options["fg"],
            page.colors["danger"],
        )

    def test_out_of_range_interval_restores_value(self) -> None:
        callbacks = make_callbacks()
        page, _parent, recorder = make_page(callbacks)
        page._interval_vars["storage"].set("999")

        storage_spin = next(
            widget
            for widget in recorder.widgets("spinbox")
            if widget.kwargs.get("textvariable") is page._interval_vars["storage"]
        )
        storage_spin.kwargs["command"]()

        callbacks.on_interval_commit.assert_not_called()
        self.assertEqual(page._interval_vars["storage"].get(), "30")

    def test_card_toggle_emits_semantic_visibility(self) -> None:
        callbacks = make_callbacks()
        page, _parent, recorder = make_page(callbacks)
        page._card_vars["battery"].set(False)

        battery_check = next(
            widget
            for widget in recorder.widgets("checkbutton")
            if widget.kwargs.get("variable") is page._card_vars["battery"]
        )
        battery_check.kwargs["command"]()

        callbacks.on_card_visibility_change.assert_called_once_with("battery", False)

    def test_auto_hide_toggle_emits_semantic(self) -> None:
        callbacks = make_callbacks()
        page, _parent, recorder = make_page(callbacks)
        page._auto_hide_var.set(True)

        auto_check = next(
            widget
            for widget in recorder.widgets("checkbutton")
            if widget.kwargs.get("variable") is page._auto_hide_var
        )
        auto_check.kwargs["command"]()

        callbacks.on_auto_hide_change.assert_called_once_with(True)

    def test_manual_scan_buttons_invoke_scan_callbacks(self) -> None:
        callbacks = make_callbacks()
        page, _parent, _recorder = make_page(callbacks)

        page.analyze_button.kwargs["command"]()
        page.cancel_button.kwargs["command"]()

        callbacks.on_scan.assert_called_once_with()
        callbacks.on_cancel_scan.assert_called_once_with()

    def test_cancel_button_starts_disabled(self) -> None:
        page, _parent, _recorder = make_page()

        self.assertEqual(page.cancel_button.kwargs["state"], tk.DISABLED)
        self.assertEqual(page.analyze_button.kwargs["style"], "Primary.TButton")
        self.assertEqual(page.cancel_button.kwargs["style"], "Danger.TButton")

    def test_manual_scan_status_and_progress_use_shared_styles(self) -> None:
        page, _parent, _recorder = make_page()

        self.assertEqual(
            page.manual_status_label.kwargs["text"],
            scan_status.READY_TEXT,
        )
        self.assertEqual(
            page.manual_status_label.kwargs["style"],
            scan_status.READY_STYLE,
        )
        self.assertEqual(page.manual_progress_bar.kwargs["maximum"], 6)
        self.assertEqual(
            page.manual_progress_bar.kwargs["style"],
            scan_status.ANALYSIS_BAR_STYLE,
        )

    def test_reset_button_invokes_on_reset(self) -> None:
        callbacks = make_callbacks()
        page, _parent, _recorder = make_page(callbacks)

        page.reset_button.kwargs["command"]()

        callbacks.on_reset.assert_called_once_with()

    def test_page_registers_stable_action_ids_when_coordinator_present(self) -> None:
        coordinator = ButtonCoordinator()
        page, _parent, _recorder = make_page(button_coordinator=coordinator)

        self.assertTrue(
            {
                "preferences:scan",
                "preferences:cancel-scan",
                "preferences:reset",
                "preferences:auto-hide",
                "preferences:card:cpu:visibility",
                "preferences:card:battery:visibility",
            }.issubset(set(coordinator.registered_ids()))
        )
        self.assertEqual(page.cancel_button.config_options["state"], tk.DISABLED)

    def test_page_scan_button_dispatch_is_gated_by_coordinator(self) -> None:
        callbacks = make_callbacks()
        coordinator = ButtonCoordinator()
        page, _parent, _recorder = make_page(callbacks, button_coordinator=coordinator)

        page.analyze_button.config_options["command"]()
        callbacks.on_scan.assert_called_once_with()

        coordinator.set_enabled("preferences:scan", False)
        page.analyze_button.config_options["command"]()
        callbacks.on_scan.assert_called_once_with()
        self.assertEqual(page.analyze_button.config_options["state"], tk.DISABLED)

    def test_category_rail_is_removed(self) -> None:
        page, _parent, _recorder = make_page()

        self.assertFalse(hasattr(page, "preferences_button"))
        self.assertFalse(hasattr(page.callbacks, "on_select_section"))

    def test_refresh_from_updates_controls_without_callbacks(self) -> None:
        callbacks = make_callbacks()
        page, _parent, _recorder = make_page(callbacks)

        class FakePreferences:
            @property
            def refresh_intervals(self):
                return self

            def as_dict(self) -> dict[str, int]:
                return {"cpu": 5000, "storage": 30000}

            visible_cards = frozenset({"cpu"})
            hide_unavailable_cards = True

        page.refresh_from(FakePreferences())

        self.assertEqual(page._interval_vars["cpu"].get(), "5")
        self.assertEqual(page._interval_vars["storage"].get(), "30")
        self.assertTrue(page._card_vars["cpu"].get())
        self.assertFalse(page._card_vars["battery"].get())
        self.assertTrue(page._auto_hide_var.get())
        callbacks.on_interval_commit.assert_not_called()
        callbacks.on_card_visibility_change.assert_not_called()

    def test_show_status_and_error_use_semantic_colours(self) -> None:
        page, _parent, _recorder = make_page()

        page.show_status("Preferences saved")
        self.assertEqual(page.status_label.config_options["text"], "Preferences saved")
        self.assertEqual(
            page.status_label.config_options["fg"],
            page.colors["secondary"],
        )

        page.show_error("Could not save")
        self.assertEqual(page.status_label.config_options["text"], "Could not save")
        self.assertEqual(page.status_label.config_options["fg"], page.colors["danger"])

    def test_focus_back_targets_back_button(self) -> None:
        page, _parent, _recorder = make_page()
        page.back_button.focus_set = Mock()

        page.focus_back()

        page.back_button.focus_set.assert_called_once_with()

    def test_page_registers_no_toplevel(self) -> None:
        page, _parent, _recorder = make_page()

        self.assertFalse(hasattr(page, "frame"))
        self.assertFalse(hasattr(page, "toplevel"))


if __name__ == "__main__":
    unittest.main()
