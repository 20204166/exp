"""Qt presentation helpers for the shared dashboard scan states."""

from PySide6.QtWidgets import QLabel, QProgressBar

from maintenance.ui import scan_status


def progress_text(message: str, count: int, total: int) -> str:
    """Use the toolkit-neutral scan wording for one progress update."""

    return scan_status.progress_text(message, count, total)


def apply_ready(label: QLabel) -> None:
    label.setText(scan_status.READY_TEXT)
    label.setProperty("role", "success")


def apply_scanning(label: QLabel) -> None:
    label.setText(scan_status.SCANNING_TEXT)
    label.setProperty("role", "warning")
    label.style().unpolish(label)
    label.style().polish(label)


def apply_step(
    label: QLabel, bar: QProgressBar, message: str, count: int, total: int
) -> None:
    bar.setRange(0, max(total, 1))
    bar.setValue(max(0, min(count, max(total, 1))))
    label.setText(progress_text(message, count, total))


def apply_cancelling(label: QLabel) -> None:
    label.setText(scan_status.CANCELLING_TEXT)


def apply_complete(
    label: QLabel, bar: QProgressBar, value: int, *, success_color: str
) -> None:
    bar.setRange(0, max(value, 1))
    bar.setValue(max(0, value))
    bar.setProperty("role", "success")
    bar.setStyleSheet(
        "QProgressBar { border: 0; background: "
        + bar.palette().color(bar.backgroundRole()).name()
        + "; } QProgressBar::chunk { background: "
        + success_color
        + "; }"
    )
    label.setText(scan_status.COMPLETE_TEXT)
    label.setProperty("role", "success")
    for widget in (bar, label):
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def apply_error(label: QLabel, message: str) -> None:
    label.setText(f"●  {message}")
    label.setProperty("role", "danger")
    label.style().unpolish(label)
    label.style().polish(label)


def apply_reset(bar: QProgressBar) -> None:
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setProperty("role", "analysis")
    bar.setStyleSheet("")
