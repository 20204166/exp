"""Presentation-only pairing confirmation dialog contract."""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles


@dataclass(frozen=True, slots=True)
class PairingDialogSpec:
    node_id: str
    display_name: str = ""
    identity_fingerprint: str | None = None
    transport_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class PairingDialogCallbacks:
    on_pair: Callable[[str], None]


class PairingDialog:
    def __init__(
        self,
        parent: Any,
        *,
        spec: PairingDialogSpec,
        on_pair: Callable[[str], None],
        frame_cls: Callable[..., Any] = tk.Frame,
        label_cls: Callable[..., Any] = tk.Label,
        button_cls: Callable[..., Any] = ttk.Button,
        toplevel_cls: Callable[..., Any] = tk.Toplevel,
        colors: dict[str, str] | None = None,
    ) -> None:
        self.window = toplevel_cls(parent)
        self._closed = False
        self.spec = spec
        self._on_pair = on_pair
        colors = ui_styles.COLORS if colors is None else colors
        container = ui_layout.dialog_shell(
            self.window,
            master=parent,
            title="Pair Node",
            geometry="460x240",
            minsize=(360, 200),
            colors=colors,
            padx=ui_styles.SPACING["dialog_pad_x"],
            pady=ui_styles.SPACING["dialog_pad_y"],
            frame_cls=frame_cls,
            on_close=self.close,
        )
        label_cls(container, text=spec.display_name, bg=colors["background"]).pack(
            anchor="w"
        )
        label_cls(
            container,
            text=f"Identity fingerprint: {spec.identity_fingerprint or 'Unavailable'}",
            bg=colors["background"],
        ).pack(anchor="w")
        label_cls(
            container,
            text=f"TLS fingerprint: {spec.transport_fingerprint or 'Unavailable'}",
            bg=colors["background"],
        ).pack(anchor="w")
        ui_layout.dialog_footer(
            container,
            frame_cls=frame_cls,
            label_cls=label_cls,
            colors=colors,
            status_text="Review this node before pairing.",
        )
        button_cls(container, text="Pair", command=self.confirm).pack(side="right")

    def confirm(self) -> None:
        self._on_pair(self.spec.node_id)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.window.destroy()
