"""Legacy Tk callback delivery used only by the remaining Tk dialogs."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from queue import Empty, Queue
from typing import Any


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
        self._close()

    def _close(self) -> None:
        self._closed = True
        after_id = self._after_id
        self._after_id = None
        if after_id is not None:
            try:
                self._widget.after_cancel(after_id)
            except (RuntimeError, tk.TclError):
                pass
        while True:
            try:
                self._callbacks.get_nowait()
            except Empty:
                break

    def _drain(self) -> None:
        self._after_id = None
        if self._closed:
            return
        try:
            if not self._widget.winfo_exists():
                self._close()
                return
        except (RuntimeError, tk.TclError):
            self._close()
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
