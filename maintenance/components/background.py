"""Toolkit-neutral background task execution and UI-result delivery."""

from __future__ import annotations

import threading
from collections.abc import Callable
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

from .scan_support import ProgressCallback, ProgressTask

if TYPE_CHECKING:
    import tkinter as tk


class BackgroundTaskRunner:
    """Run work off the Tkinter thread and safely deliver the result.

    Extracted from `maintenance/dialogs.py:21-74, 527-726`.

    ``run_with_delivery`` is the toolkit-neutral Qt migration entry point:
    callers inject the UI-owned queue's thread-safe delivery function. The
    legacy ``run`` entry point remains temporarily for Tk dialogs assigned to
    later migration sections.
    """

    @staticmethod
    def run_with_delivery(
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        *,
        delivery: Callable[[Callable[[], None]], None],
        on_error: Callable[[str], None],
        progress_task: ProgressTask | None = None,
        cancel_event: threading.Event | None = None,
        on_progress: ProgressCallback | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> threading.Thread:
        """Run a task in a worker and enqueue every UI hook through delivery."""
        operation_cancel_event = cancel_event or threading.Event()
        progress_callback = on_progress

        def report_progress(message: str) -> None:
            callback = progress_callback
            if callback is not None:
                delivery(lambda message=message: callback(message))

        def worker() -> None:
            try:
                result = (
                    task()
                    if progress_task is None
                    else progress_task(report_progress, operation_cancel_event)
                )
            except Exception as error:  # noqa: BLE001 - task failures reach UI hook.
                delivery(lambda message=str(error): on_error(message))
            else:
                delivery(lambda result=result: on_success(result))
            finally:
                if on_finished is not None:
                    delivery(on_finished)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread

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
        import tkinter as tk
        from tkinter import messagebox

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
