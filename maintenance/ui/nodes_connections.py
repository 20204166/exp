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
from maintenance.ui import node_presentation
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
    on_role_change: Callable[[str, frozenset[str]], None] | None = None
    on_pause: Callable[[str], None] | None = None
    on_resume: Callable[[str], None] | None = None
    on_remove_connection: Callable[[str], None] | None = None
    on_remove_job: Callable[[str], None] | None = None
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
    pairing_state: str = "discovered"


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
    pairing_state: str = "trusted"
    target_state: str = "Unknown"
    role: str = "worker"
    roles: tuple[str, ...] = ()
    role_editable: bool = False
    paused: bool = False
    has_active_job: bool = True


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
            description="Find System Analyzer peers on the local network; pairing is always explicit.",
        )
        self.discovery_state_label = self.label_cls(
            body,
            text="",
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["status"],
            anchor="w",
        )
        self.discovery_state_label.pack(anchor="w", pady=(0, 8))
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
        self._set_discovery_state(discovery_enabled, has_peers=False)
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
                "Peers seen on the local network. Pair only after checking the "
                "identity in the confirmation step."
            ),
        )
        self._discovered_body = body
        self.refresh_discovered(list(self._discovered.values()))

    def refresh_discovered(self, specs: list[DiscoveredPeerSpec]) -> None:
        self._discovered = {spec.node_id: spec for spec in specs}
        self._clear_actions("nodes:peer:")
        ui_layout.clear_children(self._discovered_body)
        if not specs:
            self._empty_hint(self._discovered_body, "No peers discovered yet.")
            self._set_discovery_state(self._discovery_var.get(), has_peers=False)
            return
        for spec in specs:
            self._peer_row(self._discovered_body, spec)
        self._set_discovery_state(self._discovery_var.get(), has_peers=True)

    def _peer_row(self, body: Any, spec: DiscoveredPeerSpec) -> Any:
        row = self.frame_cls(body, bg=self.colors["card"])
        row.pack(fill="x", pady=(0, 8))
        identity = self.frame_cls(row, bg=self.colors["card"])
        identity.pack(fill="x")
        self.label_cls(
            identity,
            text=spec.hostname,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.fonts["section"],
            anchor="w",
        ).pack(anchor="w")
        address = f"Discovered · {spec.hostname}"
        if spec.port is not None:
            address += f" · port {spec.port}"
        if not spec.compatible:
            address += " · Incompatible version"
        self.label_cls(
            identity,
            text=address,
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        details = f"Node ID: {node_presentation.technical_id(spec.node_id)}"
        if spec.identity_fingerprint:
            details += " · fingerprint available for pairing"
        self.label_cls(
            row,
            text=details,
            bg=self.colors["card"],
            fg=self.colors["muted_text"],
            font=self.fonts["node"],
            anchor="w",
        ).pack(fill="x", pady=(4, 0))
        actions = self.frame_cls(row, bg=self.colors["card"])
        actions.pack(fill="x", pady=(6, 0))
        pair_id = f"nodes:peer:{spec.node_id}:pair"
        reject_id = f"nodes:peer:{spec.node_id}:reject"
        pair_command = lambda: self.callbacks.on_pair(spec.node_id)
        reject_command = lambda: self.callbacks.on_reject(spec.node_id)
        pair_button = self.button_cls(
            actions,
            text="Pair",
            command=pair_command,
            style=ui_styles.STYLE_PRIMARY_BUTTON,
            state=tk.NORMAL if spec.compatible else tk.DISABLED,
        )
        pair_button.pack(side="right")
        self._register_button(pair_id, pair_command, pair_button, spec.compatible)
        reject_button = self.button_cls(
            actions,
            text="Reject",
            command=reject_command,
            style=ui_styles.STYLE_NEUTRAL_BUTTON,
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
                "Paired or manually configured machines. Trust and permissions "
                "are separate controls."
            ),
        )
        self._trusted_body = body
        self.refresh_trusted(list(self._trusted.values()))

    def refresh_trusted(self, specs: list[TrustedNodeSpec]) -> None:
        self._trusted = {spec.node_id: spec for spec in specs}
        self._clear_actions("nodes:trusted:")
        ui_layout.clear_children(self._trusted_body)
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

        identity = self.frame_cls(row, bg=self.colors["card"])
        identity.pack(fill="x")
        self.label_cls(
            identity,
            text=spec.display_name,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.fonts["section"],
            anchor="w",
        ).pack(anchor="w")
        role_status = (
            f"{node_presentation.trust_label('trusted')} · "
            f"{node_presentation.status_label(spec.status)}"
        )
        if spec.target_state != "Unknown":
            role_status += f" · {spec.target_state}"
        if spec.identity_status == "mismatch":
            role_status += " · Identity mismatch"
        status_role = node_presentation.status_color_role(spec.status)
        if (
            spec.identity_status == "mismatch"
            or spec.target_state == "Permission denied"
        ):
            status_role = "danger"
        self.label_cls(
            identity,
            text=role_status,
            bg=self.colors["card"],
            fg=self.colors[status_role],
            font=self.fonts["status"],
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        endpoint = f"Host: {spec.host or spec.hostname}"
        if spec.port is not None:
            endpoint += f" · port {spec.port}"
        technical = (
            f"{endpoint} · Node ID: {node_presentation.technical_id(spec.node_id)}"
        )
        self.label_cls(
            row,
            text=technical,
            bg=self.colors["card"],
            fg=self.colors["muted_text"],
            font=self.fonts["node"],
            anchor="w",
        ).pack(fill="x", pady=(4, 0))
        if spec.identity_fingerprint:
            self.label_cls(
                row,
                text="Identity fingerprint (verified):",
                bg=self.colors["card"],
                fg=self.colors["secondary"],
                font=self.fonts["node"],
                anchor="w",
            ).pack(fill="x", pady=(4, 0))
            for line in node_presentation.fingerprint_lines(spec.identity_fingerprint):
                self.label_cls(
                    row,
                    text=line,
                    bg=self.colors["card"],
                    fg=self.colors["muted_text"],
                    font=self.fonts["node"],
                    anchor="w",
                ).pack(fill="x")

        colour_var = self._var_factory()
        colour_var.set(colour)
        appearance = self.frame_cls(row, bg=self.colors["card"])
        appearance.pack(fill="x", pady=(8, 0))
        self.label_cls(
            appearance,
            text="Appearance",
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
        ).pack(side="left")
        combo = self.combobox_cls(
            appearance,
            textvariable=colour_var,
            state="readonly",
            values=list(ui_styles.NODE_COLORS),
            width=7,
        )
        combo.pack(side="left", padx=(8, 0))
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self.callbacks.on_color(spec.node_id, colour_var.get()),
        )

        permission_frame = self.frame_cls(row, bg=self.colors["card"])
        permission_frame.pack(fill="x", pady=(8, 0))
        self.label_cls(
            permission_frame,
            text="Permissions",
            bg=self.colors["card"],
            fg=self.colors["secondary"],
            font=self.fonts["body"],
        ).pack(anchor="w")
        permission_controls = self.frame_cls(permission_frame, bg=self.colors["card"])
        permission_controls.pack(fill="x", pady=(3, 0))
        if self.callbacks.on_permissions is not None:
            on_permissions = self.callbacks.on_permissions
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
                    permission_controls,
                    text=label,
                    variable=variable,
                    style=(
                        ui_styles.STYLE_DANGER_CHECKBUTTON
                        if permission != "process_review"
                        else ui_styles.STYLE_CHECKBUTTON
                    ),
                    command=lambda: on_permissions(
                        spec.node_id,
                        frozenset(
                            key
                            for key, value in permission_values.items()
                            if value.get()
                        ),
                    ),
                )
                control.pack(anchor="w", pady=(0, 2))

        if spec.roles or spec.role_editable or spec.role != "worker":
            role_frame = self.frame_cls(row, bg=self.colors["card"])
            role_frame.pack(fill="x", pady=(8, 0))
            self.label_cls(
                role_frame,
                text="Cluster role",
                bg=self.colors["card"],
                fg=self.colors["secondary"],
                font=self.fonts["body"],
            ).pack(anchor="w")
            role_controls = self.frame_cls(role_frame, bg=self.colors["card"])
            role_controls.pack(fill="x", pady=(3, 0))
            role_values: dict[str, Any] = {}
            selected = set(spec.roles) or {spec.role}
            self.worker_role_control = None
            self.subcoordinator_role_control = None
            self.coordinator_role_control = None
            for role, label in (("worker", "Worker"), ("subcoordinator", "Subcoordinator")):
                variable = self._boolean_var_factory()
                variable.set(role in selected)
                role_values[role] = variable
                control = self.checkbutton_cls(
                    role_controls,
                    text=label,
                    variable=variable,
                    state=(tk.NORMAL if spec.role_editable and not spec.paused else tk.DISABLED),
                    command=lambda: self.callbacks.on_role_change
                    and self.callbacks.on_role_change(
                        spec.node_id,
                        frozenset(
                            key for key, value in role_values.items() if value.get()
                        ),
                    ),
                )
                control.pack(anchor="w", pady=(0, 2))
                if role == "worker":
                    self.worker_role_control = control
                else:
                    self.subcoordinator_role_control = control
            coordinator_var = self._boolean_var_factory()
            coordinator_var.set("coordinator" in selected)
            self.coordinator_role_control = self.checkbutton_cls(
                role_controls,
                text="Coordinator",
                variable=coordinator_var,
                state=tk.DISABLED,
            )
            self.coordinator_role_control.pack(anchor="w", pady=(0, 2))
            self.label_cls(
                role_frame,
                text="Coordinator is assigned by the active Coordinator",
                bg=self.colors["card"],
                fg=self.colors["muted_text"],
                font=self.fonts["node"],
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        actions = self.frame_cls(row, bg=self.colors["card"])
        actions.pack(fill="x", pady=(8, 0))
        primary_actions = self.frame_cls(actions, bg=self.colors["card"])
        primary_actions.pack(fill="x")
        secondary_actions = self.frame_cls(actions, bg=self.colors["card"])
        secondary_actions.pack(fill="x", pady=(4, 0))
        for text_, command, style, parent in (
            (
                "Open",
                lambda: self.callbacks.on_open_node(spec.node_id),
                ui_styles.STYLE_PRIMARY_BUTTON,
                primary_actions,
            ),
            (
                "Test",
                lambda: self.callbacks.on_test_connection(spec.node_id),
                ui_styles.STYLE_NEUTRAL_BUTTON,
                secondary_actions,
            ),
            (
                "Rename",
                lambda: self.callbacks.on_rename(spec.node_id),
                ui_styles.STYLE_NEUTRAL_BUTTON,
                secondary_actions,
            ),
            (
                "Revoke",
                lambda: self.callbacks.on_revoke(spec.node_id),
                ui_styles.STYLE_DANGER_BUTTON,
                secondary_actions,
            ),
        ):
            enabled = text_ != "Open" or (spec.selectable and spec.status != "offline")
            action_id = f"nodes:trusted:{spec.node_id}:{text_.lower()}"
            button = self.button_cls(
                parent,
                text=text_,
                command=command,
                style=style,
                state=(tk.NORMAL if enabled else tk.DISABLED),
            )
            button.pack(side="left", padx=(0, 8))
            self._register_button(
                action_id,
                command,
                button,
                enabled,
            )
        if spec.role_editable and self.callbacks.on_pause is not None:
            pause_text = "Re-enable" if spec.paused else "Pause"
            if spec.paused and self.callbacks.on_resume is not None:
                pause_command = lambda: self.callbacks.on_resume(spec.node_id)
            else:
                pause_command = lambda: self.callbacks.on_pause(spec.node_id)
            pause_button = self.button_cls(
                secondary_actions,
                text=pause_text,
                command=pause_command,
                style=ui_styles.STYLE_NEUTRAL_BUTTON,
            )
            pause_button.pack(side="left", padx=(0, 8))
        if not spec.is_manual and self.callbacks.on_remove_connection is not None:
            remove_connection = self.button_cls(
                secondary_actions,
                text="Remove connection",
                command=lambda: self.callbacks.on_remove_connection(spec.node_id),
                style=ui_styles.STYLE_NEUTRAL_BUTTON,
            )
            remove_connection.pack(side="left", padx=(0, 8))
        if (
            spec.role_editable
            and not spec.is_manual
            and self.callbacks.on_remove_job is not None
        ):
            remove_job = self.button_cls(
                secondary_actions,
                text="Remove job",
                command=lambda: self.callbacks.on_remove_job(spec.node_id),
                style=ui_styles.STYLE_NEUTRAL_BUTTON,
            )
            remove_job.pack(side="left", padx=(0, 8))
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
                "Add a node by hostname or IP when local discovery is unavailable."
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
        form_actions = self.frame_cls(form, bg=self.colors["card"])
        form_actions.pack(fill="x", pady=(0, 2))
        self.add_host_button = self.button_cls(
            form_actions,
            text="Add host",
            command=self._add_manual_host,
            style=ui_styles.STYLE_NEUTRAL_BUTTON,
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
        holder.pack(fill="x", pady=(0, 6))
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
        ui_layout.clear_children(self._manual_hosts_body)
        if not specs:
            self._empty_hint(self._manual_hosts_body, "No manual hosts configured.")
            return
        for spec in specs:
            row = self.frame_cls(self._manual_hosts_body, bg=self.colors["card"])
            row.pack(fill="x", pady=(0, 8))
            identity = self.frame_cls(row, bg=self.colors["card"])
            identity.pack(fill="x")
            self.label_cls(
                identity,
                text=spec.display_name,
                bg=self.colors["card"],
                fg=self.colors["text"],
                font=self.fonts["section"],
                anchor="w",
            ).pack(anchor="w")
            text = f"Manual host · {spec.host or spec.hostname}"
            if spec.port is not None:
                text += f" · port {spec.port}"
            self.label_cls(
                identity,
                text=text,
                bg=self.colors["card"],
                fg=self.colors["secondary"],
                font=self.fonts["body"],
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))
            self.label_cls(
                row,
                text=f"Node ID: {node_presentation.technical_id(spec.node_id)}",
                bg=self.colors["card"],
                fg=self.colors["muted_text"],
                font=self.fonts["node"],
                anchor="w",
            ).pack(fill="x", pady=(4, 0))

            actions = self.frame_cls(row, bg=self.colors["card"])
            actions.pack(fill="x", pady=(6, 0))

            def remove_manual(node_id: str = spec.node_id) -> None:
                self.callbacks.on_remove_manual(node_id)

            remove_button = self.button_cls(
                actions,
                text="Remove",
                command=remove_manual,
                style=ui_styles.STYLE_DANGER_BUTTON,
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
            self._set_discovery_state(enabled, has_peers=bool(self._discovered))
        finally:
            self._updating = False

    def show_status(self, message: str) -> None:
        self.status_label.config(text=message, fg=self.colors["secondary"])
        if message.lower().startswith("discovery"):
            self._set_discovery_state_from_message(message, error=False)

    def show_error(self, message: str) -> None:
        self.status_label.config(text=message, fg=self.colors["danger"])
        if message.lower().startswith("discovery"):
            self._set_discovery_state_from_message(message, error=True)

    def _set_discovery_state(self, enabled: bool, *, has_peers: bool) -> None:
        if not enabled:
            value = "Disabled"
            role = "secondary"
        elif has_peers:
            value = "Running"
            role = "success"
        else:
            value = "Running - no peers found"
            role = "success"
        self.discovery_state_label.config(text=f"Status: {value}", fg=self.colors[role])

    def _set_discovery_state_from_message(self, message: str, *, error: bool) -> None:
        lowered = message.lower()
        if "disabled" in lowered:
            state, role = "Disabled", "secondary"
        elif error and "unavailable" in lowered:
            state, role = "Unavailable", "warning"
        elif error:
            state, role = "Error", "danger"
        elif "no peers" in lowered:
            state, role = "Running - no peers found", "success"
        else:
            state, role = "Running", "success"
        self.discovery_state_label.config(text=f"Status: {state}", fg=self.colors[role])

    def focus_back(self) -> None:
        self.back_button.focus_set()
