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
from maintenance.ui.action_coordinator import ButtonCoordinator

_DEFAULT_COLOR = "indigo"


@dataclass(frozen=True, slots=True)
class NodesConnectionsCallbacks:
    """The semantic events the Nodes & Connections page can emit."""

    on_back: Callable[[], None]
    on_discovery_toggle: Callable[[bool], None]
    on_pair: Callable[[str], None]
    on_reject: Callable[[str], None]
    on_rename: Callable[[str], None]
    on_color: Callable[[str, str], None]
    on_revoke: Callable[[str], None]
    on_test_connection: Callable[[str], None]
    on_open_node: Callable[[str], None]
    on_add_manual_host: Callable[[str, str, int | None], None]
    on_remove_manual: Callable[[str], None]
    on_permissions: Callable[[str, frozenset[str]], None] | None = None
    on_start_discovery: Callable[[], None] = lambda: None


@dataclass(frozen=True, slots=True)
class DiscoveredPeerSpec:
    """Presentation data for one discovered (untrusted) peer."""

    node_id: str
    hostname: str
    app_version: str
    compatible: bool
    connectable: bool
    port: int | None
    identity_fingerprint: str | None = None


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
    openable: bool = False
    is_manual: bool = False
    identity_fingerprint: str | None = None
    identity_status: str = "unverified"
    permissions: tuple[str, ...] = ()


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
        button_coordinator: ButtonCoordinator | None = None,
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
        self._button_coordinator = button_coordinator

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

        self.status_label = ui_layout.page_status(
            parent,
            "",
            label_cls=self.label_cls,
            colors=self.colors,
            fonts=self.fonts,
        )

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
        self._discovery_toggle = self._boolean_row(
            body,
            "Local-network discovery",
            variable=var,
            control_text="Enabled",
            on_change=lambda: self.callbacks.on_discovery_toggle(var.get()),
            action_id="nodes:discovery:toggle",
        )
        self.start_discovery_button = self.button_cls(
            body,
            text="Start Discovery",
            command=self.callbacks.on_start_discovery,
            style=ui_styles.STYLE_NEUTRAL_BUTTON,
            cursor="hand2",
        )
        self.start_discovery_button.pack(anchor="w", pady=(8, 0))
        self._register_button(
            "nodes:discovery:start",
            self.callbacks.on_start_discovery,
            self.start_discovery_button,
            True,
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
                "as trusted. Review the stable node ID before pairing or "
                "rejecting it; pairing only grants read access and never "
                "happens automatically."
            ),
        )
        self._discovered_body = body
        self.refresh_discovered(list(self._discovered.values()))

    def refresh_discovered(self, specs: list[DiscoveredPeerSpec]) -> None:
        self._discovered = {spec.node_id: spec for spec in specs}
        self._clear_actions("nodes:peer:")
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
        text += f"  ·  ID {spec.node_id}"
        if spec.identity_fingerprint:
            text += f"  ·  fingerprint {spec.identity_fingerprint}"
        self.label_cls(
            row,
            text=text,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.fonts["body"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        pair_id = f"nodes:peer:{spec.node_id}:pair"
        reject_id = f"nodes:peer:{spec.node_id}:reject"
        pair_command = lambda: self.callbacks.on_pair(spec.node_id)
        reject_command = lambda: self.callbacks.on_reject(spec.node_id)
        pair_button = self.button_cls(
            row,
            text="Pair",
            command=pair_command,
            style="Neutral.TButton",
            state=tk.NORMAL if spec.compatible else tk.DISABLED,
        )
        pair_button.pack(side="right")
        self._register_button(pair_id, pair_command, pair_button, spec.compatible)
        reject_button = self.button_cls(
            row,
            text="Reject",
            command=reject_command,
            style="Neutral.TButton",
        )
        reject_button.pack(side="right", padx=(0, 8))
        self._register_button(reject_id, reject_command, reject_button, True)
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
                "The stable node ID is the trust identity. Trusted nodes stay "
                "read-only; destructive capabilities are never granted here."
            ),
        )
        self._trusted_body = body
        self.refresh_trusted(list(self._trusted.values()))

    def refresh_trusted(self, specs: list[TrustedNodeSpec]) -> None:
        self._trusted = {spec.node_id: spec for spec in specs}
        self._clear_actions("nodes:trusted:")
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
        text += f"  ·  ID {spec.node_id}"
        text += f"  ·  {spec.status}"
        if spec.identity_status == "mismatch":
            text += "  ·  IDENTITY MISMATCH"
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
            action_id = f"nodes:trusted:{spec.node_id}:{text_.lower()}"
            button = self.button_cls(
                actions,
                text=text_,
                command=command,
                style=style,
                state=(
                    tk.NORMAL
                    if text_ != "Open" or spec.selectable or spec.openable
                    else tk.DISABLED
                ),
            )
            button.pack(side="left", padx=(6, 0))
            self._register_button(
                action_id,
                command,
                button,
                text_ != "Open" or spec.selectable or spec.openable,
            )
        if self.callbacks.on_permissions is not None:
            on_permissions = self.callbacks.on_permissions
            permission_frame = self.frame_cls(row, bg=self.colors["card"])
            permission_frame.pack(side="bottom", anchor="w", fill="x", pady=(6, 0))
            permission_values: dict[str, Any] = {}
            for permission, label in (
                ("process_review", "Review processes"),
                ("process_termination", "Terminate processes"),
                ("process_force_termination", "Force terminate"),
            ):
                variable = self._boolean_var_factory()
                variable.set(permission in spec.permissions)
                permission_values[permission] = variable
                control = self.checkbutton_cls(
                    permission_frame,
                    text=label,
                    variable=variable,
                    command=lambda: on_permissions(
                        spec.node_id,
                        frozenset(
                            key
                            for key, value in permission_values.items()
                            if value.get()
                        ),
                    ),
                )
                control.pack(side="left", padx=(0, 8))
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
        self._register_button(
            "nodes:manual:add-host",
            self._add_manual_host,
            self.add_host_button,
            True,
        )
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
        self._clear_actions("nodes:manual:")
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
            text += f"  ·  ID {spec.node_id}"
            self.label_cls(
                row,
                text=text,
                bg=self.colors["card"],
                fg=self.colors["text"],
                font=self.fonts["body"],
                anchor="w",
            ).pack(side="left", fill="x", expand=True)

            def remove_manual(node_id: str = spec.node_id) -> None:
                self.callbacks.on_remove_manual(node_id)

            remove_button = self.button_cls(
                row,
                text="Remove",
                command=remove_manual,
                style="Danger.TButton",
            )
            remove_button.pack(side="right")

            self._register_button(
                f"nodes:manual:{spec.node_id}:remove",
                remove_manual,
                remove_button,
                True,
            )

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
            if not 0 <= port <= 65535:
                self.show_error("Port must be between 0 and 65535")
                return
        if not name or not host:
            self.show_error("Name and host are required for a manual host")
            return
        self.callbacks.on_add_manual_host(name, host, port)

    @staticmethod
    def _clear(body: Any) -> None:
        for child in tuple(body.winfo_children()):
            child.destroy()

    def _clear_actions(self, prefix: str) -> None:
        coordinator = self._button_coordinator
        if coordinator is not None:
            coordinator.clear_prefix(prefix)

    def _register_button(
        self,
        action_id: str,
        callback: Callable[[], None],
        widget: Any,
        enabled: bool,
    ) -> None:
        coordinator = self._button_coordinator
        if coordinator is None:
            return
        coordinator.register(action_id, callback, enabled=enabled, replace=True)
        coordinator.bind(widget, action_id)

    def _boolean_row(
        self,
        parent: Any,
        label_text: str,
        *,
        variable: Any,
        control_text: str,
        on_change: Callable[[], None],
        action_id: str | None = None,
        help_text: str | None = None,
    ) -> Any:
        _, _label, control = ui_layout.boolean_setting_row(
            parent,
            label_text,
            variable=variable,
            control_text=control_text,
            on_change=on_change,
            action_id=action_id,
            button_coordinator=self._button_coordinator,
            frame_cls=self.frame_cls,
            label_cls=self.label_cls,
            checkbutton_cls=self.checkbutton_cls,
            colors=self.colors,
            fonts=self.fonts,
            help_text=help_text,
        )
        return control

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
