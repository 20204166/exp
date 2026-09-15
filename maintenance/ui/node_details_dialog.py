"""Presentation-only node details dialog contract."""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles


@dataclass(frozen=True, slots=True)
class NodeDetailsDialogSpec:
    node_id: str
    display_name: str = ""
    hostname: str = ""
    host: str = ""
    port: int | None = None
    pairing_state: str = ""
    target_state: str = ""
    role: str = ""
    permissions: tuple[str, ...] = ()
    selectable: bool = False
    openable: bool = False
    is_manual: bool = False
    paused: bool = False
    role_editable: bool = False
    has_active_job: bool = True


@dataclass(frozen=True, slots=True)
class NodeDetailsDialogCallbacks:
    on_open: Callable[[str], None] | None = None
    on_test: Callable[[str], None] | None = None
    on_pause: Callable[[str], None] | None = None
    on_resume: Callable[[str], None] | None = None
    on_revoke: Callable[[str], None] | None = None
    on_remove_connection: Callable[[str], None] | None = None
    on_remove_job: Callable[[str], None] | None = None


class NodeDetailsDialog:
    def __init__(
        self,
        parent: Any,
        *,
        spec: NodeDetailsDialogSpec,
        callbacks: NodeDetailsDialogCallbacks | None = None,
        frame_cls: Callable[..., Any] = tk.Frame,
        label_cls: Callable[..., Any] = tk.Label,
        button_cls: Callable[..., Any] = ttk.Button,
        toplevel_cls: Callable[..., Any] = tk.Toplevel,
        colors: dict[str, str] | None = None,
    ) -> None:
        self.window = toplevel_cls(parent)
        self._closed = False
        self.spec = spec
        self.callbacks = callbacks or NodeDetailsDialogCallbacks()
        self._actions: dict[str, Any] = {}
        colors = ui_styles.COLORS if colors is None else colors
        container = ui_layout.dialog_shell(
            self.window,
            master=parent,
            title="Node Details",
            geometry="460x260",
            minsize=(360, 220),
            colors=colors,
            padx=ui_styles.SPACING["dialog_pad_x"],
            pady=ui_styles.SPACING["dialog_pad_y"],
            frame_cls=frame_cls,
            on_close=self.close,
        )
        for label, value in (
            ("Name", spec.display_name),
            ("Node ID", spec.node_id),
            ("Hostname", spec.hostname),
            ("Host", spec.host),
            ("Port", "" if spec.port is None else str(spec.port)),
            ("Pairing", spec.pairing_state),
            ("Target", spec.target_state),
            ("Role", spec.role),
            ("Permissions", ", ".join(spec.permissions)),
        ):
            label_cls(
                container, text=f"{label}: {value}", bg=colors["background"]
            ).pack(anchor="w")
        ui_layout.dialog_footer(
            container,
            frame_cls=frame_cls,
            label_cls=label_cls,
            colors=colors,
            status_text="",
        )
        action_specs = (
            ("open", "Open", spec.openable, self.callbacks.on_open),
            ("test", "Test connection", spec.selectable, self.callbacks.on_test),
            (
                "revoke",
                "Revoke",
                spec.role_editable and not spec.is_manual,
                self.callbacks.on_revoke,
            ),
            (
                "remove_connection",
                "Remove connection",
                spec.is_manual,
                self.callbacks.on_remove_connection,
            ),
            (
                "remove_job",
                "Remove job",
                spec.role_editable
                and spec.role == "worker"
                and not spec.has_active_job,
                self.callbacks.on_remove_job,
            ),
        )
        pause_callback = (
            self.callbacks.on_resume if spec.paused else self.callbacks.on_pause
        )
        action_specs += (
            (
                "pause",
                "Resume" if spec.paused else "Pause",
                spec.role_editable,
                pause_callback,
            ),
        )
        for action, text, allowed, callback in action_specs:
            if allowed and callback is not None:
                self._actions[action] = button_cls(
                    container,
                    text=text,
                    command=lambda action=action: self.invoke_action(action),
                )
                self._actions[action].pack(anchor="e")

    def invoke_action(self, action: str) -> None:
        if action not in self._actions:
            return
        callback = {
            "open": self.callbacks.on_open,
            "test": self.callbacks.on_test,
            "pause": self.callbacks.on_resume
            if self.spec.paused
            else self.callbacks.on_pause,
            "revoke": self.callbacks.on_revoke,
            "remove_connection": self.callbacks.on_remove_connection,
            "remove_job": self.callbacks.on_remove_job,
        }[action]
        if callback is not None:
            callback(self.spec.node_id)

    def action(self, action: str) -> Any:
        return self._actions.get(action)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.window.destroy()
