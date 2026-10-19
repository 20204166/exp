"""Standalone Qt Help hub and topic detail pages using canonical HelpTopic data."""

from collections.abc import Callable, Iterable
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from maintenance.ui import qt_layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.help_content import HELP_TOPICS, HelpTopic


class QtHelpPage(QWidget):
    """Scrollable topic hub; navigation is emitted through injected callbacks."""

    def __init__(
        self,
        *,
        on_back: Callable[[], None],
        on_open_topic: Callable[[str], None],
        topics: Iterable[HelpTopic] = HELP_TOPICS,
        colors: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.colors = ui_styles.COLORS if colors is None else colors
        self.topics = tuple(topics)
        if len({topic.key for topic in self.topics}) != len(self.topics):
            raise ValueError("Help topic keys must be unique")
        ui_styles.configure_qt_styles(self, colors=self.colors)
        root = QVBoxLayout(self)
        root.setContentsMargins(
            *(
                ui_styles.SPACING[key]
                for key in ("page_x", "page_y", "page_x", "page_y")
            )
        )
        self.title_label = QLabel("Help & Guide", self)
        self.title_label.setProperty("role", "title")
        description = QLabel(
            "How System Analyzer works, feature by feature. Choose a topic.", self
        )
        description.setWordWrap(True)
        description.setProperty("role", "description")
        root.addWidget(self.title_label)
        root.addWidget(description)
        self.back_button = QPushButton("Back to Settings", self)
        self.back_button.setAccessibleName("Back to Settings")
        self.back_button.clicked.connect(on_back)
        root.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.scroll_area, self.content = ui_layout.qt_scrollable_area(self)
        self.scroll_area.setAccessibleName("Help topics")
        root.addWidget(self.scroll_area, 1)
        self.topic_buttons: dict[str, QPushButton] = {}
        content_layout = cast(QVBoxLayout, self.content.layout())
        for topic in self.topics:
            title = QLabel(topic.title, self.content)
            title.setProperty("role", "section")
            summary = QLabel(topic.summary, self.content)
            summary.setWordWrap(True)
            summary.setMinimumWidth(0)
            summary.setProperty("role", "description")
            button = QPushButton("Open", self.content)
            button.setProperty("role", "neutral")
            button.setAccessibleName(f"Open {topic.title}")
            button.clicked.connect(
                lambda _checked=False, key=topic.key: on_open_topic(key)
            )
            content_layout.addWidget(title)
            content_layout.addWidget(summary)
            content_layout.addWidget(button, Qt.AlignmentFlag.AlignRight)
            self.topic_buttons[topic.key] = button
        content_layout.addStretch(1)

    @property
    def topic_keys(self) -> tuple[str, ...]:
        return tuple(topic.key for topic in self.topics)

    def focus_back(self) -> None:
        self.back_button.setFocus()


class QtHelpTopicPage(QWidget):
    """Render a canonical HelpTopic without changing its content or ordering."""

    def __init__(
        self,
        topic: HelpTopic,
        *,
        on_back: Callable[[], None],
        colors: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.topic = topic
        self.colors = ui_styles.COLORS if colors is None else colors
        ui_styles.configure_qt_styles(self, colors=self.colors)
        root = QVBoxLayout(self)
        root.setContentsMargins(
            *(
                ui_styles.SPACING[key]
                for key in ("page_x", "page_y", "page_x", "page_y")
            )
        )
        self.title_label = QLabel(topic.title, self)
        self.title_label.setProperty("role", "title")
        description = QLabel(topic.summary, self)
        description.setWordWrap(True)
        description.setProperty("role", "description")
        root.addWidget(self.title_label)
        root.addWidget(description)
        self.back_button = QPushButton("All topics", self)
        self.back_button.setAccessibleName("All topics")
        self.back_button.clicked.connect(on_back)
        root.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.scroll_area, self.content = ui_layout.qt_scrollable_area(self)
        self.scroll_area.setAccessibleName(f"{topic.title} help content")
        root.addWidget(self.scroll_area, 1)
        self.content_labels: list[QLabel] = []
        for section in topic.sections:
            heading = QLabel(section.heading, self.content)
            heading.setProperty("role", "section")
            cast(QVBoxLayout, self.content.layout()).addWidget(heading)
            for paragraph in section.paragraphs:
                self._add_text(paragraph)
            for bullet in section.bullets:
                self._add_text(f"• {bullet}")
        cast(QVBoxLayout, self.content.layout()).addStretch(1)

    def _add_text(self, text: str) -> None:
        label = QLabel(text, self.content)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setProperty("role", "description")
        cast(QVBoxLayout, self.content.layout()).addWidget(label)
        self.content_labels.append(label)

    def focus_back(self) -> None:
        self.back_button.setFocus()
