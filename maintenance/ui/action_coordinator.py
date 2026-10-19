"""Stable action registry for direct UI button and card callbacks.

This is a presentation-layer companion to ``AppCoordinator``: it owns direct
semantic UI actions (navigation, open, pair, toggle, remove) while leaving
background work, coalescing, and cancellation to the app coordinator.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtWidgets import QAbstractButton

from maintenance.observability import ObservabilityWatcher


@dataclass(slots=True)
class _ActionRecord:
    callback: Callable[[], None]
    enabled: bool
    widgets: list[Any] = field(default_factory=list)


class ButtonCoordinator:
    """Register stable action IDs and keep bound widgets in sync."""

    def __init__(
        self,
        *,
        observer: ObservabilityWatcher | None = None,
        tk_error_type: type[Exception] | None = None,
    ) -> None:
        self._actions: dict[str, _ActionRecord] = {}
        self._observer = observer
        self._widget_errors = (
            (RuntimeError, tk_error_type)
            if tk_error_type is not None and tk_error_type is not RuntimeError
            else (RuntimeError,)
        )

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
        clicked = widget.clicked if isinstance(widget, QAbstractButton) else None
        if clicked is not None:
            bound_id = getattr(widget, "_button_coordinator_action_id", None)
            if bound_id != action_id:
                clicked.connect(self.command(action_id))
                widget._button_coordinator_action_id = action_id  # type: ignore[attr-defined]
            if not widget.accessibleName():
                accessible_name = widget.text().strip() or action_id.replace(":", " ")
                widget.setAccessibleName(accessible_name)
            self._apply_state(widget, record.enabled)
            return
        config = self._widget_config(widget)
        if config is not None:
            try:
                config(command=self.command(action_id))
            except TypeError:
                pass
            except self._widget_errors:
                record.widgets = [item for item in record.widgets if item is not widget]
                return
        if not self._apply_state(widget, record.enabled):
            record.widgets = [item for item in record.widgets if item is not widget]

    def dispatch(self, action_id: str) -> bool:
        record = self._actions.get(action_id)
        if record is None or not record.enabled:
            if self._observer is not None:
                self._observer.record_event(
                    f"ui:action:{action_id}",
                    "rejected",  # type: ignore[arg-type]
                )
            return False
        observer = self._observer
        token = (
            observer.begin(f"ui:action:{action_id}") if observer is not None else None
        )
        try:
            record.callback()
        except Exception as error:
            if observer is not None and token is not None:
                observer.finish(token, outcome="failure", detail=type(error).__name__)
            raise
        else:
            if observer is not None and token is not None:
                observer.finish(token)
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
    def _widget_config(widget: Any) -> Any:
        """Return the tkinter config callable for *widget*, trying both names.

        Tkinter exposes both ``.config`` and ``.configure``; test doubles may
        provide only one.  Returns ``None`` when neither is present.
        """
        config = getattr(widget, "config", None)
        if config is None:
            config = getattr(widget, "configure", None)
        return config

    def _apply_state(self, widget: Any, enabled: bool) -> bool:
        if not self._widget_exists(widget):
            return False
        set_enabled = widget.setEnabled if isinstance(widget, QAbstractButton) else None
        if set_enabled is not None:
            try:
                set_enabled(enabled)
            except RuntimeError:
                return False
            return True
        state = "normal" if enabled else "disabled"
        config = ButtonCoordinator._widget_config(widget)
        if config is None:
            return True
        try:
            config(state=state)
        except TypeError:
            # Non-button widgets may reject state updates; ignore them.
            return True
        except self._widget_errors:
            return False
        return True

    def _widget_exists(self, widget: Any) -> bool:
        if isinstance(widget, QAbstractButton):
            try:
                widget.objectName()
                return True
            except RuntimeError:
                return False
        exists = getattr(widget, "winfo_exists", None)
        if exists is None:
            return True
        try:
            return bool(exists())
        except self._widget_errors:
            return False
