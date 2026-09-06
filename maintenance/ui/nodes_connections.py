"""Nodes & Connections settings page adapter (presentation-only).

This module owns only the Nodes & Connections page's presentation and
page-local behaviour: the discovery toggle, the discovered-peer list with
pairing, the trusted-node list with rename/colour/revoke/connect-test/open
controls, and the manual-host registration form.

It never imports the window, registry, store, or transport. The controller
supplies typed callbacks and initial values (dependency-style composition)
and maps page events to application behaviour; ``refresh_*`` methods accept
the same spec tuples so the page stays decoupled from the models.
"""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles

_DEFAULT_COLOR = "indigo"


@dataclass(frozen=True, slots=True)
class NodesConnectionsCallbacks:
    """The semantic events the Nodes & Connections page can emit."""

    on_back: Callable[[], None]
    on_discovery_toggle: Callable[[bool], None]
    on_pair: Callable[[str], None]
    on_rename: Callable[[str], None]
    on_color: Callable[[str, str], None]
    on_revoke: Callable[[str], None]
    on_test_connection: Callable[[str], None]
    on_open_node: Callable[[str], None]
    on_add_manual_host: Callable[[str, str, int | None], None]
    on_remove_manual: Callable[[str], None]


@dataclass(frozen=True, slots=True)
class DiscoveredPeerSpec:
    """Presentation data for one discovered (untrusted) peer."""

    node_id: str
    hostname: str
    app_version: str
    compatible: bool
    connectable: bool
    port: int | None


@dataclass(frozen=True, slots=True)
class TrustedNodeSpec:
    """Presentation data for one trusted/authorised node."""

    node_id: str
    display_name: str
    hostname: str
    color: str | None
    status: str
    host: str
    port: int | None
    selectable: bool
    is_manual: bool = False


class NodesConnectionsPage:
    """Build and own the Nodes & Connections page inside the given page root.

    The page root is provided by the caller (an ``AppWindow`` page frame) and
    is never packed by this class; the page router controls page visibility.
    All widget classes are injectable so tests can run headlessly.
    """

    def __init__(
        self,
        parent: Any,
        *,
        callbacks: NodesConnectionsCallbacks,
        discovery_enabled: bool,
        discovered: list[DiscoveredPeerSpec],
        trusted: list[TrustedNodeSpec],
        manual: list[TrustedNodeSpec],
        frame_cls: Callable[..., Any] = tk.Frame,
        label_cls: Callable[..., Any] = tk.Label,
        style_frame_cls: Callable[..., Any] = ttk.Frame,
        style_label_cls: Callable[..., Any] = ttk.Label,
        button_cls: Callable[..., Any] = ttk.Button,
        canvas_cls: Callable[..., Any] = tk.Canvas,
        scrollbar_cls: Callable[..., Any] = ttk.Scrollbar,
        checkbutton_cls: Callable[..., Any] = ttk.Checkbutton,
        combobox_cls: Callable[..., Any] = ttk.Combobox,
        entry_cls: Callable[..., Any] = tk.Entry,
        var_factory: Callable[[], Any] | None = None,
        boolean_var_factory: Callable[[], Any] | None = None,
        colors: dict[str, str] | None = None,
        fonts: dict[str, Any] | None = None,
    ) -> None:
        self.callbacks = callbacks
        self.colors = ui_styles.COLORS if colors is None else colors
        self.fonts = ui_styles.FONTS if fonts is None else fonts
        self._var_factory = var_factory or (lambda: tk.StringVar())
        self._boolean_var_factory = boolean_var_factory or (lambda: tk.BooleanVar())

        self.frame_cls = frame_cls
        self.label_cls = label_cls
        self.style_frame_cls = style_frame_cls
        self.style_label_cls = style_label_cls
        self.button_cls = button_cls
        self.canvas_cls = canvas_cls
        self.scrollbar_cls = scrollbar_cls
        self.checkbutton_cls = checkbutton_cls
        self.combobox_cls = combobox_cls
        self.entry_cls = entry_cls

        self._discovered = {spec.node_id: spec for spec in discovered}
        self._trusted = {spec.node_id: spec for spec in trusted}
        self._manual = {spec.node_id: spec for spec in manual}
        self._updating = False

        self._build(parent, discovery_enabled)

    def _build(self, parent: Any, discovery_enabled: bool) -> None:
        (
            self.back_button,
            self.canvas,
            self.content,
            self._refresh_scrollbar,
        ) = ui_layout.page_shell(
            parent,
            title="Nodes & Connections",
            description=(
                "Manage how System Analyzer finds, pairs and connects to "
                "other machines on your network."
            ),
            back_text="Back to Settings",
            on_back=self.callbacks.on_back,
            style_frame_cls=self.style_frame_cls,
            style_label_cls=self.style_label_cls,
            button_cls=self.button_cls,
            canvas_cls=self.canvas_cls,
            scrollbar_cls=self.scrollbar_cls,
            colors=self.colors,
        )
        self._build_discovery_section(discovery_enabled)
        self._build_discovered_section()
        self._build_trusted_section()
        self._build_manual_hosts_section()

        self.status_label = self.label_cls(
            parent,
            text="",
            bg=self.colors["background"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
        )
        self.status_label.pack(anchor="w", pady=(6, 0))

    def _build_discovery_section(self, discovery_enabled: bool) -> None:
        _, body = ui_layout.section_card(
            self.content,
            "Discovery",
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            description=(
                "Advertise this machine and find other System Analyzer "
                "instances on the local network. Discovery is presence only: "
                "a discovered peer is never trusted or selectable until you "
                "pair it explicitly."
            ),
        )
        var = self._boolean_var_factory()
        var.set(discovery_enabled)
        self._discovery_var = var

        def control_factory(row: Any) -> Any:
            check = self.checkbutton_cls(
                row,
                text="Enabled",
                variable=var,
                style="App.TCheckbutton",
                command=lambda: self.callbacks.on_discovery_toggle(var.get()),
            )
            check.pack(side="right")
            return check

        ui_layout.setting_row(
            body,
            "Local-network discovery",
            control_factory,
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
        )

    def _build_discovered_section(self) -> None:
        _, body = ui_layout.section_card(
            self.content,
            "Discovered peers",
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            description=(
                "Machines seen on the local network. Pair a peer to record it "
                "as trusted; pairing only grants read access and never happens "
                "automatically."
            ),
        )
        self._discovered_body = body
        self.refresh_discovered(list(self._discovered.values()))

    def refresh_discovered(self, specs: list[DiscoveredPeerSpec]) -> None:
        self._discovered = {spec.node_id: spec for spec in specs}
        self._clear(self._discovered_body)
        if not specs:
            self._empty_hint(self._discovered_body, "No peers discovered yet.")
            return
        for spec in specs:
            self._peer_row(self._discovered_body, spec)

    def _peer_row(self, body: Any, spec: DiscoveredPeerSpec) -> Any:
        row = self.frame_cls(body, bg=self.colors["card"])
        row.pack(fill="x", pady=(0, 8))
        text = spec.hostname
        if spec.port is not None:
            text += f"  ·  port {spec.port}"
        if not spec.compatible:
            text += "  ·  incompatible"
        self.label_cls(
            row,
            text=text,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.fonts["body"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        button = self.button_cls(
            row,
            text="Pair",
            command=lambda: self.callbacks.on_pair(spec.node_id),
            style="Neutral.TButton",
            state=tk.NORMAL if spec.compatible else tk.DISABLED,
        )
        button.pack(side="right")
        return row

    def _build_trusted_section(self) -> None:
        _, body = ui_layout.section_card(
            self.content,
            "Trusted nodes",
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            description=(
                "Machines you have explicitly paired or configured manually. "
                "Trusted nodes stay read-only; destructive capabilities are "
                "never granted here."
            ),
        )
        self._trusted_body = body
        self.refresh_trusted(list(self._trusted.values()))

    def refresh_trusted(self, specs: list[TrustedNodeSpec]) -> None:
        self._trusted = {spec.node_id: spec for spec in specs}
        self._clear(self._trusted_body)
        if not specs:
            self._empty_hint(self._trusted_body, "No trusted nodes yet.")
            return
        for spec in specs:
            self._trusted_row(self._trusted_body, spec)

    def _trusted_row(self, body: Any, spec: TrustedNodeSpec) -> Any:
        row = self.frame_cls(body, bg=self.colors["card"])
        row.pack(fill="x", pady=(0, 10))

        colour = spec.color or _DEFAULT_COLOR
        hex_colour = ui_styles.NODE_COLORS.get(
            colour, ui_styles.NODE_COLORS[_DEFAULT_COLOR]
        )
        chip = self.label_cls(
            row,
            text=" ",
            bg=hex_colour,
            fg=hex_colour,
            font=self.fonts["body"],
            width=2,
        )
        chip.pack(side="left", padx=(0, 8), pady=(2, 0))

        text = spec.display_name
        if spec.hostname and spec.hostname != spec.display_name:
            text += f"  ·  {spec.hostname}"
        text += f"  ·  {spec.status}"
        self.label_cls(
            row,
            text=text,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.fonts["body"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        actions = self.frame_cls(row, bg=self.colors["card"])
        actions.pack(side="right")

        colour_var = self._var_factory()
        colour_var.set(colour)
        combo = self.combobox_cls(
            actions,
            textvariable=colour_var,
            state="readonly",
            values=list(ui_styles.NODE_COLORS),
            width=7,
        )
        combo.pack(side="left", padx=(6, 0))
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self.callbacks.on_color(spec.node_id, colour_var.get()),
        )

        for text_, command, style in (
            (
                "Test",
                lambda: self.callbacks.on_test_connection(spec.node_id),
                "Neutral.TButton",
            ),
            (
                "Rename",
                lambda: self.callbacks.on_rename(spec.node_id),
                "Neutral.TButton",
            ),
            (
                "Open",
                lambda: self.callbacks.on_open_node(spec.node_id),
                "Neutral.TButton",
            ),
            (
                "Revoke",
                lambda: self.callbacks.on_revoke(spec.node_id),
                "Danger.TButton",
            ),
        ):
            button = self.button_cls(
                actions,
                text=text_,
                command=command,
                style=style,
                state=tk.NORMAL if text_ != "Open" or spec.selectable else tk.DISABLED,
            )
            button.pack(side="left", padx=(6, 0))
        return row

    def _build_manual_hosts_section(self) -> None:
        _, body = ui_layout.section_card(
            self.content,
            "Manual hosts",
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
            description=(
                "Register a machine that does not advertise itself, so you "
                "can pair it by host and authenticated remote port."
            ),
        )
        self._manual_body = body
        form = self.frame_cls(body, bg=self.colors["card"])
        form.pack(fill="x", pady=(0, 10))
        self._manual_name_var = self._var_factory()
        self._manual_host_var = self._var_factory()
        self._manual_port_var = self._var_factory()
        self._build_entry(form, "Name", self._manual_name_var)
        self._build_entry(form, "Host", self._manual_host_var)
        self._build_entry(form, "Port", self._manual_port_var)
        self.add_host_button = self.button_cls(
            form,
            text="Add host",
            command=self._add_manual_host,
            style="Neutral.TButton",
        )
        self.add_host_button.pack(side="right", padx=(8, 0), pady=(4, 0))
        self._manual_hosts_body = body
        self.refresh_manual(list(self._manual.values()))

    def _build_entry(self, form: Any, label_text: str, var: Any) -> None:
        holder = self.frame_cls(form, bg=self.colors["card"])
        holder.pack(side="left", padx=(0, 8))
        self.label_cls(
            holder,
            text=label_text,
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
        ).pack(anchor="w")
        entry = self.entry_cls(
            holder,
            textvariable=var,
            width=16,
            bg=self.colors["card"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            relief=tk.FLAT,
            font=self.fonts["body"],
        )
        entry.pack(fill="x", pady=(2, 0))

    def refresh_manual(self, specs: list[TrustedNodeSpec]) -> None:
        self._manual = {spec.node_id: spec for spec in specs}
        self._clear(self._manual_hosts_body)
        if not specs:
            self._empty_hint(self._manual_hosts_body, "No manual hosts configured.")
            return
        for spec in specs:
            row = self.frame_cls(self._manual_hosts_body, bg=self.colors["card"])
            row.pack(fill="x", pady=(0, 8))
            text = spec.display_name
            if spec.host:
                text += f"  ·  {spec.host}"
            if spec.port is not None:
                text += f"  ·  port {spec.port}"
            self.label_cls(
                row,
                text=text,
                bg=self.colors["card"],
                fg=self.colors["text"],
                font=self.fonts["body"],
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            self.button_cls(
                row,
                text="Remove",
                command=lambda node_id=spec.node_id: self.callbacks.on_remove_manual(
                    node_id
                ),
                style="Danger.TButton",
            ).pack(side="right")

    def _add_manual_host(self) -> None:
        name = self._manual_name_var.get().strip()
        host = self._manual_host_var.get().strip()
        raw_port = self._manual_port_var.get().strip()
        port: int | None = None
        if raw_port:
            try:
                port = int(raw_port)
            except ValueError:
                self.show_error("Port must be a whole number or empty")
                return
        if not name or not host:
            self.show_error("Name and host are required for a manual host")
            return
        self.callbacks.on_add_manual_host(name, host, port)

    @staticmethod
    def _clear(body: Any) -> None:
        for child in tuple(body.winfo_children()):
            child.destroy()

    def _empty_hint(self, body: Any, text: str) -> None:
        self.label_cls(
            body,
            text=text,
            bg=self.colors["card"],
            fg=self.colors["muted_text"],
            font=self.fonts["body"],
            anchor="w",
        ).pack(anchor="w", pady=(0, 4))

    def set_discovery_enabled(self, enabled: bool) -> None:
        self._updating = True
        try:
            self._discovery_var.set(enabled)
        finally:
            self._updating = False

    def show_status(self, message: str) -> None:
        self.status_label.config(text=message, fg=self.colors["secondary"])

    def show_error(self, message: str) -> None:
        self.status_label.config(text=message, fg=self.colors["danger"])

    def focus_back(self) -> None:
        self.back_button.focus_set()
