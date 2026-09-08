"""Stable action registry for direct UI button and card callbacks.

This is a presentation-layer companion to ``AppCoordinator``: it owns direct
semantic UI actions (navigation, open, pair, toggle, remove) while leaving
background work, coalescing, and cancellation to the app coordinator.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class _ActionRecord:
    callback: Callable[[], None]
    enabled: bool
    widgets: list[Any] = field(default_factory=list)


class ButtonCoordinator:
    """Register stable action IDs and keep bound widgets in sync."""

    def __init__(self) -> None:
        self._actions: dict[str, _ActionRecord] = {}

    def register(
        self,
        action_id: str,
        callback: Callable[[], None],
        *,
        enabled: bool = True,
        replace: bool = False,
    ) -> None:
        if not action_id:
            raise ValueError("Action id cannot be empty")
        existing = self._actions.get(action_id)
        if existing is not None and not replace:
            raise ValueError(f"Action already registered: {action_id}")
        widgets = [
            widget
            for widget in (existing.widgets if existing is not None else [])
            if self._apply_state(widget, enabled)
        ]
        self._actions[action_id] = _ActionRecord(
            callback=callback,
            enabled=enabled,
            widgets=widgets,
        )

    def command(self, action_id: str) -> Callable[[], bool]:
        return lambda: self.dispatch(action_id)

    def bind(self, widget: Any, action_id: str) -> None:
        record = self._actions[action_id]
        if not self._widget_exists(widget):
            return
        if widget not in record.widgets:
            record.widgets.append(widget)
        config = getattr(widget, "config", None)
        if config is None:
            config = getattr(widget, "configure", None)
        if config is not None:
            try:
                config(command=self.command(action_id))
            except TypeError:
                pass
            except (RuntimeError, tk.TclError):
                record.widgets = [item for item in record.widgets if item is not widget]
                return
        if not self._apply_state(widget, record.enabled):
            record.widgets = [item for item in record.widgets if item is not widget]

    def dispatch(self, action_id: str) -> bool:
        record = self._actions.get(action_id)
        if record is None or not record.enabled:
            return False
        record.callback()
        return True

    def set_enabled(self, action_id: str, enabled: bool) -> None:
        record = self._actions[action_id]
        record.enabled = enabled
        record.widgets = [
            widget for widget in record.widgets if self._apply_state(widget, enabled)
        ]

    def is_enabled(self, action_id: str) -> bool:
        return self._actions[action_id].enabled

    def registered_ids(self) -> tuple[str, ...]:
        return tuple(self._actions)

    def unregister(self, action_id: str) -> None:
        self._actions.pop(action_id, None)

    def clear_prefix(self, prefix: str) -> None:
        for action_id in tuple(self._actions):
            if action_id.startswith(prefix):
                del self._actions[action_id]

    @staticmethod
    def _apply_state(widget: Any, enabled: bool) -> bool:
        if not ButtonCoordinator._widget_exists(widget):
            return False
        state = "normal" if enabled else "disabled"
        config = getattr(widget, "config", None)
        if config is None:
            config = getattr(widget, "configure", None)
        if config is None:
            return True
        try:
            config(state=state)
        except TypeError:
            # Non-button widgets may reject state updates; ignore them.
            return True
        except (RuntimeError, tk.TclError):
            return False
        return True

    @staticmethod
    def _widget_exists(widget: Any) -> bool:
        exists = getattr(widget, "winfo_exists", None)
        if exists is None:
            return True
        try:
            return bool(exists())
        except (RuntimeError, tk.TclError):
            return False
