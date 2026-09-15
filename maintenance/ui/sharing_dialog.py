"""Presentation-only dashboard sharing dialog contract."""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles


@dataclass(frozen=True, slots=True)
class SharingDialogSpec:
    active: bool


@dataclass(frozen=True, slots=True)
class SharingDialogCallbacks:
    on_share: Callable[[], None]
    on_stop: Callable[[], None]


class SharingDialog:
    def __init__(
        self,
        parent: Any,
        *,
        active: bool,
        on_share: Callable[[], None],
        on_stop: Callable[[], None],
        frame_cls: Callable[..., Any] = tk.Frame,
        label_cls: Callable[..., Any] = tk.Label,
        button_cls: Callable[..., Any] = ttk.Button,
        toplevel_cls: Callable[..., Any] = tk.Toplevel,
        colors: dict[str, str] | None = None,
    ) -> None:
        self.window = toplevel_cls(parent)
        self._closed = False
        self.active = active
        self._on_share = on_share
        self._on_stop = on_stop
        colors = ui_styles.COLORS if colors is None else colors
        container = ui_layout.dialog_shell(
            self.window,
            master=parent,
            title="Share Dashboard",
            geometry="420x220",
            minsize=(340, 180),
            colors=colors,
            padx=ui_styles.SPACING["dialog_pad_x"],
            pady=ui_styles.SPACING["dialog_pad_y"],
            frame_cls=frame_cls,
            on_close=self.close,
        )
        label_cls(container, text="Dashboard sharing", bg=colors["background"]).pack(
            anchor="w"
        )
        label_cls(
            container,
            text="Active" if active else "Inactive",
            bg=colors["background"],
        ).pack(anchor="w")
        label_cls(
            container,
            text="Sharing duration: 5 minutes",
            bg=colors["background"],
        ).pack(anchor="w")
        ui_layout.dialog_footer(
            container,
            frame_cls=frame_cls,
            label_cls=label_cls,
            colors=colors,
            status_text="",
        )
        button_cls(
            container,
            text="Stop sharing" if active else "Share for 5 minutes",
            command=self.confirm,
        ).pack(anchor="e")

    def confirm(self) -> None:
        if self.active:
            self._on_stop()
        else:
            self._on_share()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.window.destroy()
