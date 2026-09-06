"""Focused headless tests for the reusable Settings category hub."""

import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.ui.settings_home import (
    SettingsCategorySpec,
    SettingsHome,
    SettingsHomeCallbacks,
)
from tests.support.widget_recording import RecordingWidget, WidgetRecorder


def make_callbacks() -> Any:
    return SettingsHomeCallbacks(
        on_back=Mock(),
        on_select_category=Mock(),
    )


def make_home(
    callbacks: SettingsHomeCallbacks | None = None,
    categories: list[SettingsCategorySpec] | None = None,
    version: str | None = None,
) -> tuple[SettingsHome, RecordingWidget, WidgetRecorder]:
    recorder = WidgetRecorder()
    parent = recorder.parent()
    home = SettingsHome(
        parent,
        callbacks=callbacks or make_callbacks(),
        categories=categories
        or [
            SettingsCategorySpec(
                "preferences",
                "Preferences",
                "Refresh intervals, visible cards, scan behaviour, and "
                "interface options.",
            )
        ],
        version=version,
        frame_cls=recorder.frame_cls(),
        label_cls=recorder.label_cls(),
        style_frame_cls=recorder.style_frame_cls(),
        style_label_cls=recorder.style_label_cls(),
        button_cls=recorder.button_cls(),
        canvas_cls=recorder.canvas_cls(),
        scrollbar_cls=recorder.scrollbar_cls(),
    )
    return home, parent, recorder


class SettingsHomeTests(unittest.TestCase):
    def test_page_root_is_not_packed_by_the_page(self) -> None:
        _home, parent, _recorder = make_home()

        self.assertEqual(parent.pack_calls, [])

    def test_header_renders_settings_title_and_description(self) -> None:
        _home, _parent, recorder = make_home()

        texts = recorder.label_texts()
        self.assertIn("Settings", texts)
        self.assertTrue(any("configuration and options" in text for text in texts))

    def test_category_card_renders_title_and_description(self) -> None:
        _home, _parent, recorder = make_home()

        texts = recorder.label_texts()
        self.assertIn("Preferences", texts)
        self.assertTrue(any("Refresh intervals" in text for text in texts))

    def test_category_button_invokes_select_category(self) -> None:
        callbacks = make_callbacks()
        home, _parent, _recorder = make_home(callbacks)

        home.category_button("preferences").kwargs["command"]()

        callbacks.on_select_category.assert_called_once_with("preferences")

    def test_back_button_invokes_on_back(self) -> None:
        callbacks = make_callbacks()
        home, _parent, _recorder = make_home(callbacks)

        home.back_button.kwargs["command"]()

        callbacks.on_back.assert_called_once_with()

    def test_home_constructs_no_preference_controls(self) -> None:
        _home, _parent, recorder = make_home()

        self.assertEqual(recorder.widgets("spinbox"), [])
        self.assertEqual(recorder.widgets("checkbutton"), [])
        self.assertEqual(recorder.widgets("progressbar"), [])

    def test_multiple_categories_render_in_order(self) -> None:
        home, _parent, _recorder = make_home(
            categories=[
                SettingsCategorySpec("preferences", "Preferences", "A"),
                SettingsCategorySpec("diagnostics", "Diagnostics", "B"),
            ]
        )

        self.assertEqual(home.category_keys, ("preferences", "diagnostics"))
        self.assertIn("diagnostics", home._category_buttons)

    def test_focus_back_targets_back_button(self) -> None:
        home, _parent, _recorder = make_home()
        home.back_button.focus_set = Mock()

        home.focus_back()

        home.back_button.focus_set.assert_called_once_with()

    def test_page_registers_no_toplevel(self) -> None:
        home, _parent, _recorder = make_home()

        self.assertFalse(hasattr(home, "toplevel"))

    def test_version_label_renders_when_provided(self) -> None:
        _home, _parent, recorder = make_home(version="1.2.6.0")

        self.assertIn("System Analyzer 1.2.6.0", recorder.label_texts())
        version_label = recorder.label_with_text("System Analyzer 1.2.6.0")
        self.assertEqual(version_label.pack_calls[-1].get("side"), "bottom")
        self.assertEqual(version_label.pack_calls[-1].get("anchor"), "w")

    def test_version_label_omitted_when_absent(self) -> None:
        home, _parent, _recorder = make_home()

        self.assertFalse(hasattr(home, "version_label"))
        self.assertIsNone(home.version)


if __name__ == "__main__":
    unittest.main()
