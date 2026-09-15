"""Presentation-only manual connection dialog contract."""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles


@dataclass(frozen=True, slots=True)
class ConnectionDialogCallbacks:
    on_add: Callable[[str, str, int | None], None]
    on_test: Callable[[str], None] | None = None


@dataclass(frozen=True, slots=True)
class ConnectionDialogSpec:
    node_id: str | None = None


class ConnectionDialog:
    def __init__(
        self,
        parent: Any,
        *,
        on_add: Callable[[str, str, int | None], None],
        node_id: str | None = None,
        on_test: Callable[[str], None] | None = None,
        frame_cls: Callable[..., Any] = tk.Frame,
        label_cls: Callable[..., Any] = tk.Label,
        entry_cls: Callable[..., Any] = tk.Entry,
        button_cls: Callable[..., Any] = ttk.Button,
        toplevel_cls: Callable[..., Any] = tk.Toplevel,
        var_factory: Callable[[], Any] = tk.StringVar,
        colors: dict[str, str] | None = None,
    ) -> None:
        self.window = toplevel_cls(parent)
        self._closed = False
        self._on_add = on_add
        self._node_id = node_id
        self._on_test = on_test
        self._status_text = ""
        colors = ui_styles.COLORS if colors is None else colors
        container = ui_layout.dialog_shell(
            self.window,
            master=parent,
            title="Add Connection",
            geometry="460x260",
            minsize=(360, 220),
            colors=colors,
            padx=ui_styles.SPACING["dialog_pad_x"],
            pady=ui_styles.SPACING["dialog_pad_y"],
            frame_cls=frame_cls,
            on_close=self.close,
        )
        self.name_var = var_factory()
        self.host_var = var_factory()
        self.port_var = var_factory()
        for text in ("Display name", "Host", "Port"):
            label_cls(container, text=text, bg=colors["background"]).pack(anchor="w")
        for variable in (self.name_var, self.host_var, self.port_var):
            entry_cls(container, textvariable=variable).pack(fill="x")
        _footer, self._status = ui_layout.dialog_footer(
            container,
            frame_cls=frame_cls,
            label_cls=label_cls,
            colors=colors,
            status_text="",
        )
        button_cls(container, text="Add", command=self.submit).pack(side="right")

    def submit(self) -> None:
        name = str(self.name_var.get()).strip()
        host = str(self.host_var.get()).strip()
        port_text = str(self.port_var.get()).strip()
        if not host:
            self._set_status("Host is required.")
            return
        if port_text:
            try:
                port = int(port_text)
            except ValueError:
                self._set_status("Port must be a number.")
                return
            if not 1 <= port <= 65535:
                self._set_status("Port must be between 1 and 65535.")
                return
        else:
            port = None
        self._set_status("")
        self._on_add(name, host, port)

    def status_text(self) -> str:
        return self._status_text

    def _set_status(self, text: str) -> None:
        self._status_text = text
        self._status.configure(text=text)

    def test_connection(self) -> None:
        if self._on_test is not None and self._node_id is not None:
            self._on_test(self._node_id)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.window.destroy()
