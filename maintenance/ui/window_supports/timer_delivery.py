"""Tk timer lifecycle support specific to the application window."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from typing import Any


class TimerDelivery:
    """Track, schedule, cancel, and safely deliver window timers."""

    def __init__(
        self,
        *,
        master: Any,
        is_closing: Callable[[], bool],
        pending_ids: set[str],
        logger: logging.Logger,
    ) -> None:
        self._master = master
        self._is_closing = is_closing
        self._pending_ids = pending_ids
        self._logger = logger

    def schedule(
        self,
        delay: int,
        callback: Callable[..., None],
        *args: object,
    ) -> str | None:
        if self._is_closing():
            return None

        identifier: str | None = None

        def run_callback() -> None:
            if identifier is not None:
                self._pending_ids.discard(identifier)
            if not self._is_closing():
                callback(*args)

        try:
            identifier = self._master.after(delay, run_callback)
        except (RuntimeError, tk.TclError):
            if not self._is_closing():
                self._logger.exception("Failed to schedule Tkinter work")
            return None

        assert identifier is not None
        self._pending_ids.add(identifier)
        return identifier

    def cancel(self, identifier: str | None) -> bool:
        if identifier is None:
            return True

        try:
            self._master.after_cancel(identifier)
        except (RuntimeError, tk.TclError):
            if not self._is_closing():
                self._logger.exception("Failed to cancel Tkinter work")
            else:
                self._pending_ids.discard(identifier)
            return False

        self._pending_ids.discard(identifier)
        return True

    def cancel_all(self) -> None:
        for identifier in tuple(self._pending_ids):
            self.cancel(identifier)

    @staticmethod
    def invoke(callback: Callable[[], None], logger: logging.Logger) -> None:
        try:
            callback()
        except Exception as error:  # noqa: BLE001 - a dead widget must not kill the drain.
            logger.warning("Dropped UI delivery callback: %s", error)
