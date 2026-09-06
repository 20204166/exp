"""Background Tk task delivery shared by the dialogs."""

import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox
from typing import Any

from .scan_support import ProgressCallback, ProgressTask


class BackgroundTaskRunner:
    """Run work off the Tkinter thread and safely deliver the result.

    Extracted from `maintenance/dialogs.py:21-74, 527-726`.
    """

    @staticmethod
    def run_in_thread(
        widget: tk.Misc,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
        *,
        progress_task: ProgressTask | None = None,
        cancel_event: threading.Event | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        operation_cancel_event = cancel_event or threading.Event()

        def deliver(callback: Callable, value: Any) -> None:
            try:
                if widget.winfo_exists():
                    callback(value)
            except (RuntimeError, tk.TclError):
                pass

        def report_progress(message: str) -> None:
            if on_progress is None:
                return
            try:
                widget.after(0, deliver, on_progress, message)
            except (RuntimeError, tk.TclError):
                pass

        def worker() -> None:
            try:
                if progress_task is None:
                    result = task()
                else:
                    result = progress_task(report_progress, operation_cancel_event)
            except Exception as error:  # noqa: BLE001 - dialog tasks must surface errors.
                callback = on_error or (
                    lambda message: messagebox.showerror(
                        "Operation Error",
                        message,
                        parent=widget,
                    )
                )
                try:
                    widget.after(0, deliver, callback, str(error))
                except (RuntimeError, tk.TclError):
                    pass
            else:
                try:
                    widget.after(0, deliver, on_success, result)
                except (RuntimeError, tk.TclError):
                    pass

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def run(
        widget: tk.Misc,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
        *,
        progress_task: ProgressTask | None = None,
        cancel_event: threading.Event | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        BackgroundTaskRunner.run_in_thread(
            widget,
            task,
            on_success,
            on_error,
            progress_task=progress_task,
            cancel_event=cancel_event,
            on_progress=on_progress,
        )
