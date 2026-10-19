"""Behavioral tests for Qt Help hub and detail pages."""

import unittest
from typing import cast
from unittest.mock import Mock

from PySide6.QtWidgets import QVBoxLayout

from maintenance.ui.help_content import HELP_TOPICS
from maintenance.ui.qt_help_page import QtHelpPage, QtHelpTopicPage
from tests.support.qt import get_qapplication


class QtHelpPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def test_hub_preserves_canonical_topic_order_and_dispatches_actions(self) -> None:
        on_back = Mock()
        on_open = Mock()
        page = QtHelpPage(on_back=on_back, on_open_topic=on_open)
        self.assertEqual(page.topic_keys, tuple(topic.key for topic in HELP_TOPICS))
        self.assertEqual(tuple(page.topic_buttons), page.topic_keys)
        page.topic_buttons["troubleshooting"].click()
        on_open.assert_called_once_with("troubleshooting")
        page.back_button.click()
        on_back.assert_called_once_with()
        self.assertTrue(page.topic_buttons["troubleshooting"].accessibleName())
        page.close()

    def test_detail_renders_canonical_content_in_order_without_rewriting(self) -> None:
        topic = next(item for item in HELP_TOPICS if item.key == "installing")
        page = QtHelpTopicPage(topic, on_back=Mock())
        rendered = [label.text() for label in page.content_labels]
        expected = []
        for section in topic.sections:
            expected.extend(section.paragraphs)
            expected.extend(f"• {bullet}" for bullet in section.bullets)
        self.assertEqual(rendered, expected)
        headings = [
            label.text()
            for label in page.content.findChildren(type(page.title_label))
            if label.property("role") == "section"
        ]
        self.assertEqual(headings, [section.heading for section in topic.sections])
        self.assertEqual(page.topic, topic)
        page.close()

    def test_detail_back_callback_and_focus_back(self) -> None:
        on_back = Mock()
        page = QtHelpTopicPage(HELP_TOPICS[0], on_back=on_back)
        page.show()
        page.activateWindow()
        page.focus_back()
        self.app.processEvents()
        self.assertEqual(self.app.focusWidget(), page.back_button)
        page.back_button.click()
        on_back.assert_called_once_with()
        self.assertEqual(page.back_button.accessibleName(), "All topics")
        page.close()

    def test_long_detail_content_scrolls_and_wraps_at_target_widths(self) -> None:
        topic = next(item for item in HELP_TOPICS if item.key == "troubleshooting")
        page = QtHelpTopicPage(topic, on_back=Mock())
        for width in (900, 1280, 1600):
            page.resize(width, 400)
            page.show()
            self.app.processEvents()
            self.assertGreaterEqual(page.width(), width - 10)
        self.assertTrue(page.scroll_area.widgetResizable())
        self.assertTrue(all(label.wordWrap() for label in page.content_labels))
        self.assertGreater(
            cast(QVBoxLayout, page.content.layout()).sizeHint().height(),
            page.scroll_area.height(),
        )
        page.close()

    def test_back_buttons_have_accessible_names(self) -> None:
        hub = QtHelpPage(on_back=Mock(), on_open_topic=Mock())
        detail = QtHelpTopicPage(HELP_TOPICS[0], on_back=Mock())
        self.assertEqual(hub.back_button.accessibleName(), "Back to Settings")
        self.assertTrue(
            all(button.accessibleName() for button in hub.topic_buttons.values())
        )
        self.assertEqual(detail.back_button.accessibleName(), "All topics")
        hub.close()
        detail.close()


if __name__ == "__main__":
    unittest.main()
