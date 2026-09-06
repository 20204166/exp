"""Guarded live-Tk helpers shared by live resize tests and dumps.

Display detection is performed once at import time; callers that need the
value use ``DISPLAY_AVAILABLE``.
"""

import tkinter as tk
from collections.abc import Iterator
from typing import Any


def _display_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except (tk.TclError, RuntimeError):
        return False


DISPLAY_AVAILABLE = _display_available()

TEST_COLORS = {
    "background": "#F4F7FB",
    "card": "#FFFFFF",
    "text": "#172033",
    "secondary": "#667085",
    "accent": "#4F46E5",
    "border": "#E4E7EC",
}


def pump(widget: Any, passes: int = 6) -> None:
    """Pump Tk events and idle callbacks until layout settles."""

    for _ in range(passes):
        widget.update()
        widget.update_idletasks()


def walk_widgets(widget: Any) -> Iterator[Any]:
    """Yield a widget and every descendant depth-first."""

    yield widget
    for child in widget.winfo_children():
        yield from walk_widgets(child)


def labels(widget: Any) -> list[Any]:
    """Return all descendant widgets whose class is ``Label``."""

    result: list[Any] = []
    for child in walk_widgets(widget):
        try:
            if child.winfo_class() == "Label":
                result.append(child)
        except (tk.TclError, AttributeError):
            continue
    return result
