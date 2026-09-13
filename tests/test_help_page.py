"""Focused headless tests for the Help & Guide hub and topic detail pages.

Both pages are built exactly like every other page in this app: once, with
no internal rebuild-on-navigation mechanism -- navigation between topics
goes through the real page router (see window.py/window_pages.py), not
page-local state. These tests cover only what each page builds and emits.
"""

import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.help_content import HelpSection, HelpTopic
from maintenance.ui.help_page import (
    HelpPage,
    HelpPageCallbacks,
    HelpTopicPage,
    HelpTopicPageCallbacks,
)
from tests.support.widget_recording import RecordingWidget, WidgetRecorder

_TOPICS = (
    HelpTopic(
        key="alpha",
        title="Alpha",
        summary="First topic.",
        sections=(
            HelpSection(
                heading="Details",
                paragraphs=("Alpha paragraph.",),
                bullets=("Alpha bullet.",),
            ),
        ),
    ),
    HelpTopic(
        key="beta",
        title="Beta",
        summary="Second topic.",
        sections=(HelpSection(heading="More", paragraphs=("Beta paragraph.",)),),
    ),
)


def make_hub_callbacks() -> Any:
    return HelpPageCallbacks(on_back=Mock(), on_open_topic=Mock())


def make_hub_page(
    callbacks: HelpPageCallbacks | None = None,
    topics: tuple[HelpTopic, ...] = _TOPICS,
    button_coordinator: ButtonCoordinator | None = None,
) -> tuple[HelpPage, RecordingWidget, WidgetRecorder]:
    recorder = WidgetRecorder()
    parent = recorder.parent()
    page = HelpPage(
        parent,
        callbacks=callbacks or make_hub_callbacks(),
        topics=topics,
        **recorder.page_kwargs(),
        button_coordinator=button_coordinator,
    )
    return page, parent, recorder


class HelpPageHubTests(unittest.TestCase):
    def test_page_root_is_not_packed_by_the_page(self) -> None:
        _page, parent, _recorder = make_hub_page()

        self.assertEqual(parent.pack_calls, [])

    def test_hub_shows_the_title(self) -> None:
        _page, _parent, recorder = make_hub_page()

        self.assertIn("Help & Guide", recorder.label_texts())

    def test_hub_renders_one_card_per_topic(self) -> None:
        _page, _parent, recorder = make_hub_page()

        texts = recorder.label_texts()
        self.assertIn("Alpha", texts)
        self.assertIn("Beta", texts)
        self.assertIn("First topic.", texts)
        self.assertIn("Second topic.", texts)

    def test_topic_keys_reflects_supplied_topics(self) -> None:
        page, _parent, _recorder = make_hub_page()

        self.assertEqual(page.topic_keys, ("alpha", "beta"))

    def test_back_button_invokes_on_back(self) -> None:
        callbacks = make_hub_callbacks()
        page, _parent, _recorder = make_hub_page(callbacks)

        page.back_button.kwargs["command"]()

        callbacks.on_back.assert_called_once_with()

    def test_focus_back_targets_back_button(self) -> None:
        page, _parent, _recorder = make_hub_page()
        page.back_button.focus_set = Mock()

        page.focus_back()

        page.back_button.focus_set.assert_called_once_with()

    def test_topic_card_invokes_on_open_topic_with_its_key(self) -> None:
        callbacks = make_hub_callbacks()
        page, _parent, _recorder = make_hub_page(callbacks)

        page.topic_button("beta").kwargs["command"]()

        callbacks.on_open_topic.assert_called_once_with("beta")

    def test_topic_button_registers_stable_action_id_when_coordinator_present(
        self,
    ) -> None:
        coordinator = ButtonCoordinator()
        callbacks = make_hub_callbacks()
        page, _parent, _recorder = make_hub_page(
            callbacks, button_coordinator=coordinator
        )

        self.assertIn("help:topic:alpha", coordinator.registered_ids())
        page.topic_button("alpha").config_options["command"]()

        callbacks.on_open_topic.assert_called_with("alpha")


def make_topic_callbacks() -> Any:
    return HelpTopicPageCallbacks(on_back=Mock())


def make_topic_page(
    topic: HelpTopic = _TOPICS[0],
    callbacks: HelpTopicPageCallbacks | None = None,
) -> tuple[HelpTopicPage, RecordingWidget, WidgetRecorder]:
    recorder = WidgetRecorder()
    parent = recorder.parent()
    page = HelpTopicPage(
        parent,
        topic=topic,
        callbacks=callbacks or make_topic_callbacks(),
        **recorder.page_kwargs(),
    )
    return page, parent, recorder


class HelpTopicPageTests(unittest.TestCase):
    def test_page_root_is_not_packed_by_the_page(self) -> None:
        _page, parent, _recorder = make_topic_page()

        self.assertEqual(parent.pack_calls, [])

    def test_shows_title_summary_and_content(self) -> None:
        _page, _parent, recorder = make_topic_page(_TOPICS[0])

        texts = recorder.label_texts()
        self.assertIn("Alpha", texts)
        self.assertIn("First topic.", texts)
        self.assertIn("Alpha paragraph.", texts)
        self.assertIn("• Alpha bullet.", texts)

    def test_back_button_is_labelled_all_topics_and_invokes_on_back(self) -> None:
        callbacks = make_topic_callbacks()
        page, _parent, _recorder = make_topic_page(_TOPICS[1], callbacks)

        self.assertEqual(page.back_button.kwargs.get("text"), "All topics")
        page.back_button.kwargs["command"]()

        callbacks.on_back.assert_called_once_with()

    def test_focus_back_targets_back_button(self) -> None:
        page, _parent, _recorder = make_topic_page()
        page.back_button.focus_set = Mock()

        page.focus_back()

        page.back_button.focus_set.assert_called_once_with()

    def test_different_topics_render_their_own_content(self) -> None:
        _page, _parent, recorder = make_topic_page(_TOPICS[1])

        texts = recorder.label_texts()
        self.assertIn("Beta", texts)
        self.assertIn("Beta paragraph.", texts)
        self.assertNotIn("Alpha paragraph.", texts)


if __name__ == "__main__":
    unittest.main()
