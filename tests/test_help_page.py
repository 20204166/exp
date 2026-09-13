"""Focused headless tests for the Help & Guide hub and topic detail views."""

import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.help_content import HelpSection, HelpTopic
from maintenance.ui.help_page import HelpPage, HelpPageCallbacks
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


def make_callbacks() -> Any:
    return HelpPageCallbacks(on_back=Mock())


def make_page(
    callbacks: HelpPageCallbacks | None = None,
    topics: tuple[HelpTopic, ...] = _TOPICS,
    initial_topic: str | None = None,
    button_coordinator: ButtonCoordinator | None = None,
) -> tuple[HelpPage, RecordingWidget, WidgetRecorder]:
    recorder = WidgetRecorder()
    parent = recorder.parent()
    page = HelpPage(
        parent,
        callbacks=callbacks or make_callbacks(),
        topics=topics,
        initial_topic=initial_topic,
        **recorder.page_kwargs(),
        button_coordinator=button_coordinator,
    )
    return page, parent, recorder


class HelpPageTopicListTests(unittest.TestCase):
    def test_page_root_is_not_packed_by_the_page(self) -> None:
        _page, parent, _recorder = make_page()

        self.assertEqual(parent.pack_calls, [])

    def test_topic_list_shows_the_hub_title(self) -> None:
        _page, _parent, recorder = make_page()

        self.assertIn("Help & Guide", recorder.label_texts())

    def test_topic_list_renders_one_card_per_topic(self) -> None:
        _page, _parent, recorder = make_page()

        texts = recorder.label_texts()
        self.assertIn("Alpha", texts)
        self.assertIn("Beta", texts)
        self.assertIn("First topic.", texts)
        self.assertIn("Second topic.", texts)

    def test_topic_keys_reflects_supplied_topics(self) -> None:
        page, _parent, _recorder = make_page()

        self.assertEqual(page.topic_keys, ("alpha", "beta"))

    def test_back_button_invokes_on_back(self) -> None:
        callbacks = make_callbacks()
        page, _parent, _recorder = make_page(callbacks)

        page.back_button.kwargs["command"]()

        callbacks.on_back.assert_called_once_with()

    def test_focus_back_targets_back_button(self) -> None:
        page, _parent, _recorder = make_page()
        page.back_button.focus_set = Mock()

        page.focus_back()

        page.back_button.focus_set.assert_called_once_with()

    def test_topic_button_registers_stable_action_id_when_coordinator_present(
        self,
    ) -> None:
        coordinator = ButtonCoordinator()
        page, _parent, _recorder = make_page(button_coordinator=coordinator)

        self.assertIn("help:topic:alpha", coordinator.registered_ids())
        page.topic_button("alpha").config_options["command"]()

        self.assertEqual(page.selected_topic, "alpha")


class HelpPageTopicDetailTests(unittest.TestCase):
    def test_opening_a_topic_shows_its_title_and_content(self) -> None:
        page, _parent, recorder = make_page()

        page.open_topic("alpha")

        texts = recorder.label_texts()
        self.assertIn("Alpha", texts)
        self.assertIn("Alpha paragraph.", texts)
        self.assertIn("• Alpha bullet.", texts)

    def test_topic_button_command_opens_that_topic(self) -> None:
        page, _parent, _recorder = make_page()

        page.topic_button("beta").kwargs["command"]()

        self.assertEqual(page.selected_topic, "beta")

    def test_unknown_topic_key_falls_back_to_the_topic_list(self) -> None:
        page, _parent, recorder = make_page()

        page.open_topic("does-not-exist")

        self.assertIsNone(page.selected_topic)
        self.assertIn("Help & Guide", recorder.label_texts())

    def test_all_topics_back_button_returns_to_the_list(self) -> None:
        page, _parent, recorder = make_page()
        page.open_topic("alpha")

        page.back_button.kwargs["command"]()

        self.assertIsNone(page.selected_topic)
        self.assertIn("Beta", recorder.label_texts())

    def test_show_topics_resets_from_a_topic(self) -> None:
        page, _parent, recorder = make_page()
        page.open_topic("alpha")

        page.show_topics()

        self.assertIsNone(page.selected_topic)
        self.assertIn("Beta", recorder.label_texts())

    def test_initial_topic_opens_directly_to_that_topic(self) -> None:
        page, _parent, recorder = make_page(initial_topic="beta")

        self.assertEqual(page.selected_topic, "beta")
        self.assertIn("Beta paragraph.", recorder.label_texts())

    def test_invalid_initial_topic_falls_back_to_the_topic_list(self) -> None:
        page, _parent, _recorder = make_page(initial_topic="nope")

        self.assertIsNone(page.selected_topic)


if __name__ == "__main__":
    unittest.main()
