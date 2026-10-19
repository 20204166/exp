"""Layout helpers owned by the Qt presentation layer."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from maintenance.ui import styles as ui_styles


def qt_scrollable_area(parent: QWidget) -> tuple[QScrollArea, QWidget]:
    """Create the Qt equivalent of a vertically scrolling content body."""
    area = QScrollArea(parent)
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget(area)
    content.setAccessibleName("Scrollable content")
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(ui_styles.SPACING["section_gap"])
    content.setLayout(layout)
    area.setWidget(content)
    return area, content


def qt_wrap_label(
    label: QLabel,
    *,
    max_wrap: int,
    margin: int = 36,
    hysteresis: int = 12,
    min_width: int = 40,
) -> Callable[[int], int | None]:
    """Return a width updater with exact-fit shrinking and growth hysteresis."""
    label.setWordWrap(True)
    last = max_wrap

    def update(width: int) -> int | None:
        nonlocal last
        proposed = min(max_wrap, max(0, width - margin))
        if proposed > last and proposed - last < hysteresis:
            return None
        if width <= min_width:
            return None
        if proposed == last:
            return None
        last = proposed
        label.setMaximumWidth(proposed)
        return proposed

    return update
