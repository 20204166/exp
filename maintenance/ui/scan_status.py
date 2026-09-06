"""Shared global scan-presentation state: wording, styles and bar values.

The dashboard scan header (status label + global progress bar) uses this
module as its single source of truth for the standard status wording and
the style names behind each state, so conceptually identical states never
drift into slightly different strings or colours. The controller
(``window.AppWindow``) still owns *when* a state applies; these helpers
only apply the shared presentation to the given widgets.
"""

from typing import Any

READY_TEXT = "●  Ready"
SCANNING_TEXT = "●  Scanning..."
CANCELLING_TEXT = "●  Cancelling..."
COMPLETE_TEXT = "● Scan complete"

READY_STYLE = "Ready.Status.TLabel"
BUSY_STYLE = "Busy.Status.TLabel"

ANALYSIS_BAR_STYLE = "Analysis.Horizontal.TProgressbar"
COMPLETE_BAR_STYLE = "Complete.Horizontal.TProgressbar"


def progress_text(message: str, count: int, total: int) -> str:
    """Return the per-step status wording for one scan progress message."""

    return f"●  {message} ({count}/{total})"


def apply_scanning(status_label: Any) -> None:
    """Present the scanning state on the given status label."""

    status_label.config(text=SCANNING_TEXT, style=BUSY_STYLE)


def apply_step(
    status_label: Any,
    progress_bar: Any,
    message: str,
    count: int,
    total: int,
) -> None:
    """Advance the global bar to ``count`` and show the step's status text."""

    progress_bar.config(value=count)
    status_label.config(text=progress_text(message, count, total))


def apply_cancelling(status_label: Any) -> None:
    """Present the cancellation-requested state."""

    status_label.config(text=CANCELLING_TEXT)


def apply_complete(status_label: Any, progress_bar: Any, value: int) -> None:
    """Present a finished scan: full green bar and the complete status."""

    progress_bar.config(value=value, style=COMPLETE_BAR_STYLE)
    status_label.config(text=COMPLETE_TEXT, style=READY_STYLE)


def apply_ready(status_label: Any) -> None:
    """Present the idle Ready state."""

    status_label.config(text=READY_TEXT, style=READY_STYLE)


def apply_reset(progress_bar: Any) -> None:
    """Return the bar to its empty idle state (no false completion)."""

    progress_bar.config(value=0, style=ANALYSIS_BAR_STYLE)
