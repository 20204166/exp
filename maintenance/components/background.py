"""Background Tk task delivery shared by the dialogs."""

import threading
import tkinter as tk
from collections.abc import Callable
from queue import Empty, Queue
from tkinter import messagebox
from typing import Any

from .scan_support import ProgressCallback, ProgressTask


class TkDeliveryQueue:
    """Queue callbacks from workers and drain them from Tk's main thread."""

    def __init__(self, widget: tk.Misc) -> None:
        self._widget = widget
        self._callbacks: Queue[Callable[[], None]] = Queue()
        self._closed = False
        self._after_id: str | None = None
        try:
            widget.bind("<Destroy>", self._on_destroy, add="+")
            self._after_id = widget.after(0, self._drain)
        except (RuntimeError, tk.TclError):
            pass

    def __call__(self, callback: Callable[[], None]) -> None:
        if not self._closed:
            self._callbacks.put(callback)

    def _on_destroy(self, event: Any = None) -> None:
        if (
            event is not None
            and getattr(event, "widget", self._widget) is not self._widget
        ):
            return
        self._closed = True
        after_id = self._after_id
        self._after_id = None
        if after_id is not None:
            try:
                self._widget.after_cancel(after_id)
            except (RuntimeError, tk.TclError):
                pass

    def _drain(self) -> None:
        self._after_id = None
        if self._closed:
            return
        try:
            if not self._widget.winfo_exists():
                self._closed = True
                return
        except (RuntimeError, tk.TclError):
            return
        while True:
            try:
                callback = self._callbacks.get_nowait()
            except Empty:
                break
            try:
                callback()
            except (RuntimeError, tk.TclError):
                pass
        try:
            self._after_id = self._widget.after(25, self._drain)
        except (RuntimeError, tk.TclError):
            self._closed = True


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

        if isinstance(widget, tk.Misc):
            deliveries: Queue[tuple[Callable, Any]] = Queue()
            finished = threading.Event()

            def drain() -> None:
                try:
                    if not widget.winfo_exists():
                        return
                except (RuntimeError, tk.TclError):
                    return
                while True:
                    try:
                        callback, value = deliveries.get_nowait()
                    except Empty:
                        break
                    try:
                        callback(value)
                    except (RuntimeError, tk.TclError):
                        pass
                if not finished.is_set() or not deliveries.empty():
                    try:
                        widget.after(25, drain)
                    except (RuntimeError, tk.TclError):
                        pass

            try:
                widget.after(0, drain)
            except (RuntimeError, tk.TclError):
                return

            def enqueue(callback: Callable, value: Any) -> None:
                deliveries.put((callback, value))

            def finish() -> None:
                finished.set()

        else:

            def enqueue(callback: Callable, value: Any) -> None:
                try:
                    widget.after(0, callback, value)
                except (RuntimeError, tk.TclError):
                    pass

            def finish() -> None:
                pass

        def report_progress(message: str) -> None:
            if on_progress is None:
                return
            enqueue(on_progress, message)

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
                enqueue(callback, str(error))
            else:
                enqueue(on_success, result)
            finally:
                finish()

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
