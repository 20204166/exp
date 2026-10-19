"""Isolated Qt presentation for Nodes & Connections during Tk-shell migration."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import cast

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from maintenance.nodes import NodeDescriptor
from maintenance.ui import node_presentation
from maintenance.ui import qt_layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.page_specs import (
    DiscoveredPeerSpec,
    LocalClusterSpec,
    TrustedNodeSpec,
)


@dataclass(frozen=True, slots=True)
class QtNodesConnectionsCallbacks:
    """Injected semantic events; the widget never performs network or policy work."""

    on_back: Callable[[], None]
    on_discovery_toggle: Callable[[bool], None]
    on_pair: Callable[[str], None]
    on_reject: Callable[[str], None]
    on_select_node: Callable[[str], None]
    on_open_node: Callable[[str], None]
    on_test_connection: Callable[[str], None]
    on_refresh: Callable[[], None]
    on_details: Callable[[DiscoveredPeerSpec | TrustedNodeSpec], None] | None = None
    on_rename: Callable[[str], None] | None = None
    on_color: Callable[[str, str], None] | None = None
    on_permissions: Callable[[str, frozenset[str]], None] | None = None
    on_role_change: Callable[[str, frozenset[str]], None] | None = None
    on_remove_manual: Callable[[str], None] | None = None
    on_start_discovery: Callable[[], None] | None = None
    on_learn_pairing: Callable[[], None] | None = None
    on_open_connection: Callable[[TrustedNodeSpec], None] | None = None
    on_share_dashboard: Callable[[], None] | None = None
    on_revoke: Callable[[str], None] | None = None
    on_pause: Callable[[str], None] | None = None
    on_resume: Callable[[str], None] | None = None
    on_remove_connection: Callable[[str], None] | None = None
    on_remove_job: Callable[[str], None] | None = None


class QtNodesConnectionsPage(QWidget):
    """Render existing node projections without deriving trust or cluster policy."""

    def __init__(
        self,
        *,
        callbacks: QtNodesConnectionsCallbacks,
        discovery_enabled: bool,
        discovered: Iterable[DiscoveredPeerSpec],
        trusted: Iterable[TrustedNodeSpec],
        manual: Iterable[TrustedNodeSpec],
        selected_node: NodeDescriptor | None = None,
        local_cluster: LocalClusterSpec | None = None,
        colors: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.callbacks = callbacks
        self.colors = ui_styles.COLORS if colors is None else colors
        self.setAccessibleName("Nodes and connections")
        ui_styles.configure_qt_styles(self, colors=self.colors)
        discovered_items = tuple(discovered)
        trusted_items = tuple(trusted)
        manual_items = tuple(manual)
        self.section_order = ["Discovery", "Discovered peers", "Trusted nodes"]
        if local_cluster is not None:
            self.section_order.append("Cluster membership")
        if manual_items:
            self.section_order.append("Manual hosts")

        root = QVBoxLayout(self)
        root.setContentsMargins(
            *(
                ui_styles.SPACING[key]
                for key in ("page_x", "page_y", "page_x", "page_y")
            )
        )
        heading = QLabel("Nodes & Connections", self)
        heading.setProperty("role", "title")
        description = QLabel(
            "Manage discovery, trusted peers, and node connections.", self
        )
        description.setWordWrap(True)
        description.setProperty("role", "description")
        root.addWidget(heading)
        root.addWidget(description)
        self.selected_node_label = QLabel(self._selected_text(selected_node), self)
        self.selected_node_label.setWordWrap(True)
        self.selected_node_label.setAccessibleName("Selected node")
        root.addWidget(self.selected_node_label)
        nav = QHBoxLayout()
        self.back_button = self._button(
            "Back to Settings", "Back to Settings", callbacks.on_back
        )
        self.refresh_button = self._button(
            "Refresh", "Refresh nodes and connections", callbacks.on_refresh
        )
        nav.addWidget(self.back_button)
        nav.addWidget(self.refresh_button)
        nav.addStretch(1)
        root.addLayout(nav)
        self.status_label = QLabel("", self)
        self.status_label.setAccessibleName("Nodes and connections status")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.scroll_area, self.content = ui_layout.qt_scrollable_area(self)
        self.scroll_area.setAccessibleName("Nodes and connections details")
        root.addWidget(self.scroll_area, 1)

        self._rebuild_projection(
            discovery_enabled=discovery_enabled,
            discovered=discovered_items,
            trusted=trusted_items,
            manual=manual_items,
            selected_node=selected_node,
            local_cluster=local_cluster,
        )

    def refresh(
        self,
        *,
        discovery_enabled: bool,
        discovered: Iterable[DiscoveredPeerSpec],
        trusted: Iterable[TrustedNodeSpec],
        manual: Iterable[TrustedNodeSpec],
        selected_node: NodeDescriptor | None,
        local_cluster: LocalClusterSpec | None,
    ) -> None:
        """Rebuild this page from a fresh controller-owned projection."""

        self._rebuild_projection(
            discovery_enabled=discovery_enabled,
            discovered=tuple(discovered),
            trusted=tuple(trusted),
            manual=tuple(manual),
            selected_node=selected_node,
            local_cluster=local_cluster,
        )

    def _rebuild_projection(
        self,
        *,
        discovery_enabled: bool,
        discovered: Iterable[DiscoveredPeerSpec],
        trusted: Iterable[TrustedNodeSpec],
        manual: Iterable[TrustedNodeSpec],
        selected_node: NodeDescriptor | None,
        local_cluster: LocalClusterSpec | None,
    ) -> None:
        content_layout = cast(QVBoxLayout, self.content.layout())
        while content_layout.count():
            item = content_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        discovered_items = tuple(discovered)
        trusted_items = tuple(trusted)
        manual_items = tuple(manual)
        self.section_order = ["Discovery", "Discovered peers", "Trusted nodes"]
        if local_cluster is not None:
            self.section_order.append("Cluster membership")
        if manual_items:
            self.section_order.append("Manual hosts")
        self.selected_node_label.setText(self._selected_text(selected_node))

        self._section("Discovery", "Discovery presence does not establish trust.")
        self.discovery_toggle = QCheckBox("Local-network discovery", self.content)
        self.discovery_toggle.setAccessibleName("Enable local-network discovery")
        self.discovery_toggle.setChecked(discovery_enabled)
        self.discovery_toggle.toggled.connect(
            lambda checked: self.callbacks.on_discovery_toggle(checked)
        )
        content_layout.addWidget(self.discovery_toggle)
        self.start_discovery_button = None
        if self.callbacks.on_start_discovery is not None:
            self.start_discovery_button = self._button(
                "Start Discovery",
                "Start local-network discovery",
                self.callbacks.on_start_discovery,
            )
            content_layout.addWidget(self.start_discovery_button)
        self.learn_pairing_button = None
        if self.callbacks.on_learn_pairing is not None:
            self.learn_pairing_button = self._button(
                "Learn about pairing & trust",
                "Learn about pairing and trust",
                self.callbacks.on_learn_pairing,
            )
            content_layout.addWidget(self.learn_pairing_button)

        self._section(
            "Discovered peers",
            "Discovered peers remain untrusted until explicitly paired.",
        )
        self.discovered_rows: dict[str, QLabel] = {}
        self.pair_buttons: dict[str, QPushButton] = {}
        self.reject_buttons: dict[str, QPushButton] = {}
        self.paired_status_labels: dict[str, QLabel] = {}
        self.discovered_details_buttons: dict[str, QPushButton] = {}
        for spec in discovered_items:
            row = self._row()
            text = QLabel(self._discovered_text(spec), row)
            text.setWordWrap(True)
            text.setMinimumWidth(0)
            cast(QHBoxLayout, row.layout()).addWidget(text, 1)
            actions = QWidget(row)
            actions_layout = QVBoxLayout(actions)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            if spec.has_pair_relationship:
                paired = QLabel("Paired", actions)
                paired.setAccessibleName(f"{spec.hostname}: paired")
                self.paired_status_labels[spec.node_id] = paired
                actions_layout.addWidget(paired)
            else:
                pair = self._button(
                    "Pair",
                    f"Pair with {spec.hostname}",
                    lambda _checked=False, node=spec.node_id: self.callbacks.on_pair(
                        node
                    ),
                )
                pair.setEnabled(spec.compatible)
                reject = self._button(
                    "Reject",
                    f"Reject {spec.hostname}",
                    lambda _checked=False, node=spec.node_id: self.callbacks.on_reject(
                        node
                    ),
                )
                actions_layout.addWidget(pair)
                actions_layout.addWidget(reject)
                self.pair_buttons[spec.node_id] = pair
                self.reject_buttons[spec.node_id] = reject
            details_callback = self.callbacks.on_details
            if details_callback is not None:
                details = self._button(
                    "Details",
                    f"Details for {spec.hostname}",
                    lambda peer=spec, callback=details_callback: callback(peer),
                )
                actions_layout.addWidget(details)
                self.discovered_details_buttons[spec.node_id] = details
            cast(QHBoxLayout, row.layout()).addWidget(actions)
            content_layout.addWidget(row)
            self.discovered_rows[spec.node_id] = text
        if not self.discovered_rows:
            self._empty("No peers discovered yet.")

        self._section(
            "Trusted nodes",
            "Trust, cluster membership, and connection are independent states.",
        )
        self.trusted_rows: dict[str, QLabel] = {}
        self.select_buttons: dict[str, QPushButton] = {}
        self.open_buttons: dict[str, QPushButton] = {}
        self.test_buttons: dict[str, QPushButton] = {}
        self.details_buttons: dict[str, QPushButton] = {}
        self.revoke_buttons: dict[str, QPushButton] = {}
        self.pause_buttons: dict[str, QPushButton] = {}
        self.remove_connection_buttons: dict[str, QPushButton] = {}
        self.remove_job_buttons: dict[str, QPushButton] = {}
        self.rename_buttons: dict[str, QPushButton] = {}
        self.color_controls: dict[str, QComboBox] = {}
        self.permission_controls: dict[str, dict[str, QCheckBox]] = {}
        self.role_controls: dict[str, dict[str, QCheckBox]] = {}
        self.remove_manual_buttons: dict[str, QPushButton] = {}
        for spec in trusted_items:
            self._trusted_row(spec, manual=False)
        if not self.trusted_rows:
            self._empty("No trusted nodes yet.")

        if local_cluster is not None:
            self._section(
                "Cluster membership",
                "Cluster state is shown separately from trust and connectivity.",
            )
            self.cluster_summary = QLabel(
                self._cluster_text(local_cluster), self.content
            )
            self.cluster_summary.setWordWrap(True)
            self.cluster_summary.setAccessibleName("Cluster membership status")
            content_layout.addWidget(self.cluster_summary)
            self.dashboard_share_label = QLabel(
                self._share_text(local_cluster), self.content
            )
            self.dashboard_share_label.setWordWrap(True)
            self.dashboard_share_label.setAccessibleName("Dashboard sharing status")
            content_layout.addWidget(self.dashboard_share_label)
            self.share_dashboard_button = None
            if self.callbacks.on_share_dashboard is not None:
                share_text = (
                    "Stop Sharing"
                    if local_cluster.dashboard_share_active
                    else "Share My Dashboard"
                )
                self.share_dashboard_button = self._button(
                    share_text, share_text, self.callbacks.on_share_dashboard
                )
                content_layout.addWidget(self.share_dashboard_button)
        else:
            self.cluster_summary = None
            self.dashboard_share_label = None
            self.share_dashboard_button = None

        self.manual_rows: dict[str, QLabel] = {}
        if manual_items:
            self._section(
                "Manual hosts", "Manually configured hosts are listed separately."
            )
            for spec in manual_items:
                self._trusted_row(spec, manual=True)
        content_layout.addStretch(1)

    def _button(
        self, text: str, accessible_name: str, callback: Callable[[], None]
    ) -> QPushButton:
        button = QPushButton(text, self)
        button.setAccessibleName(accessible_name)
        button.clicked.connect(lambda _checked=False: callback())
        return button

    def _section(self, title: str, description: str) -> None:
        heading = QLabel(title, self.content)
        heading.setProperty("role", "section")
        detail = QLabel(description, self.content)
        detail.setWordWrap(True)
        detail.setProperty("role", "description")
        content_layout = cast(QVBoxLayout, self.content.layout())
        content_layout.addWidget(heading)
        content_layout.addWidget(detail)

    def _row(self) -> QWidget:
        row = QWidget(self.content)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, ui_styles.SPACING["row_gap"])
        cast(QVBoxLayout, self.content.layout()).addWidget(row)
        return row

    def _empty(self, text: str) -> None:
        label = QLabel(text, self.content)
        label.setWordWrap(True)
        cast(QVBoxLayout, self.content.layout()).addWidget(label)

    @staticmethod
    def _discovered_text(spec: DiscoveredPeerSpec) -> str:
        state = "Untrusted · Discovered"
        if not spec.compatible:
            state += " · Incompatible version"
        if spec.has_pair_relationship:
            state = "Discovered · Pair relationship exists"
        return f"{spec.hostname}\n{state} · Node ID: {node_presentation.technical_id(spec.node_id)}"

    @staticmethod
    def _trusted_text(spec: TrustedNodeSpec) -> str:
        trust = "Trusted"
        connection = node_presentation.connection_status_label(
            spec.connection_status,
            manual_disconnected=spec.manual_disconnected,
            retry_automatic=spec.retry_automatic,
        )
        membership = (
            f"{spec.role.title()} · Cluster member"
            if spec.is_cluster_member
            else "Not in cluster"
        )
        return (
            f"{spec.display_name}\n{trust} · {membership} · {connection}"
            f"\nHost: {spec.host or spec.hostname} · Node ID: {node_presentation.technical_id(spec.node_id)}"
        )

    def _trusted_row(self, spec: TrustedNodeSpec, *, manual: bool) -> None:
        row = self._row()
        label = QLabel(self._trusted_text(spec), row)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        cast(QHBoxLayout, row.layout()).addWidget(label, 1)
        actions = QWidget(row)
        buttons = QVBoxLayout(actions)
        buttons.setContentsMargins(0, 0, 0, 0)
        if not manual:
            select = self._button(
                "Select",
                f"Select {spec.display_name}",
                lambda _checked=False, node=spec.node_id: self.callbacks.on_select_node(
                    node
                ),
            )
            select.setEnabled(spec.selectable)
            open_button = self._button(
                "Open",
                f"Open {spec.display_name}",
                lambda _checked=False, node=spec.node_id: self.callbacks.on_open_node(
                    node
                ),
            )
            open_button.setEnabled(spec.openable)
            test_callback = lambda: (
                self.callbacks.on_open_connection(spec)
                if self.callbacks.on_open_connection is not None
                else self.callbacks.on_test_connection(spec.node_id)
            )
            test = self._button(
                "Test connection",
                f"Test connection to {spec.display_name}",
                test_callback,
            )
            buttons.addWidget(select)
            buttons.addWidget(open_button)
            buttons.addWidget(test)
            self.select_buttons[spec.node_id] = select
            self.open_buttons[spec.node_id] = open_button
            self.test_buttons[spec.node_id] = test
            self.trusted_rows[spec.node_id] = label
            details_callback = self.callbacks.on_details
            if details_callback is not None:
                details = self._details_button(spec, details_callback)
                buttons.addWidget(details)
                self.details_buttons[spec.node_id] = details
            revoke_callback = self.callbacks.on_revoke
            if revoke_callback is not None:
                revoke = self._button(
                    "Revoke",
                    f"Revoke trust for {spec.display_name}",
                    lambda _checked=False, node=spec.node_id: revoke_callback(node),
                )
                buttons.addWidget(revoke)
                self.revoke_buttons[spec.node_id] = revoke
            if spec.role_editable and self.callbacks.on_pause is not None:
                pause_callback = (
                    self.callbacks.on_resume
                    if spec.paused and self.callbacks.on_resume is not None
                    else self.callbacks.on_pause
                )
                pause_text = "Re-enable" if spec.paused else "Pause"
                pause = self._button(
                    pause_text,
                    f"{pause_text} {spec.display_name}",
                    lambda node=spec.node_id, callback=pause_callback: callback(node),
                )
                buttons.addWidget(pause)
                self.pause_buttons[spec.node_id] = pause
            remove_connection_callback = self.callbacks.on_remove_connection
            if not spec.is_manual and remove_connection_callback is not None:
                remove_connection = self._button(
                    "Remove connection",
                    f"Remove connection to {spec.display_name}",
                    lambda node=spec.node_id: remove_connection_callback(node),
                )
                buttons.addWidget(remove_connection)
                self.remove_connection_buttons[spec.node_id] = remove_connection
            if (
                spec.role_editable
                and not spec.is_manual
                and spec.has_active_job
                and self.callbacks.on_remove_job is not None
            ):
                remove_job_callback = self.callbacks.on_remove_job
                assert remove_job_callback is not None
                remove_job = self._button(
                    "Remove job",
                    f"Remove job from {spec.display_name}",
                    lambda node=spec.node_id: remove_job_callback(node),
                )
                buttons.addWidget(remove_job)
                self.remove_job_buttons[spec.node_id] = remove_job
        else:
            self.manual_rows[spec.node_id] = label
            details_callback = self.callbacks.on_details
            if details_callback is not None:
                details = self._details_button(spec, details_callback)
                buttons.addWidget(details)
                self.details_buttons[spec.node_id] = details
            remove_manual_callback = self.callbacks.on_remove_manual
            if remove_manual_callback is not None:
                remove = self._button(
                    "Remove",
                    f"Remove manual host {spec.display_name}",
                    lambda _checked=False, node=spec.node_id: remove_manual_callback(
                        node
                    ),
                )
                remove.setProperty("role", "danger")
                buttons.addWidget(remove)
                self.remove_manual_buttons[spec.node_id] = remove
        cast(QHBoxLayout, row.layout()).addWidget(actions)

        if not manual:
            rename_callback = self.callbacks.on_rename
            if rename_callback is not None:
                rename = self._button(
                    "Rename",
                    f"Rename {spec.display_name}",
                    lambda _checked=False, node=spec.node_id: rename_callback(node),
                )
                buttons.addWidget(rename)
                self.rename_buttons[spec.node_id] = rename
            color_callback = self.callbacks.on_color
            if color_callback is not None:
                color = QComboBox(row)
                color.setAccessibleName(f"Color for {spec.display_name}")
                color.addItems(tuple(ui_styles.NODE_COLORS))
                if spec.color in ui_styles.NODE_COLORS:
                    color.setCurrentText(spec.color)
                color.currentTextChanged.connect(
                    lambda value, node=spec.node_id: color_callback(node, value)
                )
                buttons.addWidget(color)
                self.color_controls[spec.node_id] = color
            permissions_callback = self.callbacks.on_permissions
            if permissions_callback is not None:
                controls: dict[str, QCheckBox] = {}
                for key, title in (
                    ("dashboard_read", "View dashboard"),
                    ("component_read", "View components"),
                    ("storage_review", "Review storage"),
                    ("process_review", "Review processes"),
                    ("process_termination", "Terminate processes"),
                    ("process_force_termination", "Force terminate"),
                ):
                    checkbox = QCheckBox(title, row)
                    checkbox.setAccessibleName(f"{title} for {spec.display_name}")
                    checkbox.setChecked(key in spec.permissions)
                    controls[key] = checkbox

                def emit_permissions(
                    _checked: bool,
                    *,
                    node: str = spec.node_id,
                    items: dict[str, QCheckBox] = controls,
                ) -> None:
                    permissions_callback(
                        node,
                        frozenset(
                            key for key, control in items.items() if control.isChecked()
                        ),
                    )

                for checkbox in controls.values():
                    checkbox.toggled.connect(emit_permissions)
                    buttons.addWidget(checkbox)
                self.permission_controls[spec.node_id] = controls
            role_callback = self.callbacks.on_role_change
            if role_callback is not None and (
                spec.roles or spec.role_editable or spec.role != "worker"
            ):
                controls = {}
                selected = set(spec.roles) or {spec.role}
                for key, title in (
                    ("worker", "Worker"),
                    ("subcoordinator", "Subcoordinator"),
                ):
                    checkbox = QCheckBox(title, row)
                    checkbox.setAccessibleName(f"{title} role for {spec.display_name}")
                    checkbox.setChecked(key in selected)
                    checkbox.setEnabled(spec.role_editable and not spec.paused)
                    controls[key] = checkbox

                def emit_roles(
                    _checked: bool,
                    *,
                    node: str = spec.node_id,
                    items: dict[str, QCheckBox] = controls,
                ) -> None:
                    role_callback(
                        node,
                        frozenset(
                            key for key, control in items.items() if control.isChecked()
                        ),
                    )

                for checkbox in controls.values():
                    checkbox.toggled.connect(emit_roles)
                    buttons.addWidget(checkbox)
                coordinator = QCheckBox("Coordinator (assigned by coordinator)", row)
                coordinator.setAccessibleName(
                    f"Coordinator role for {spec.display_name}"
                )
                coordinator.setChecked("coordinator" in selected)
                coordinator.setEnabled(False)
                buttons.addWidget(coordinator)
                self.role_controls[spec.node_id] = controls

    def _details_button(
        self,
        spec: TrustedNodeSpec,
        callback: Callable[[TrustedNodeSpec], None],
    ) -> QPushButton:
        return self._button(
            "Details",
            f"Details for {spec.display_name}",
            lambda: callback(spec),
        )

    @staticmethod
    def _share_text(spec: LocalClusterSpec) -> str:
        if spec.dashboard_share_active:
            coordinator = (
                spec.coordinator_display_name
                or spec.coordinator_node_id
                or "coordinator"
            )
            return f"Dashboard sharing: Shared with {coordinator}"
        if spec.joined and not spec.has_peer_grants:
            return "Dashboard sharing: Off · Coordinator cannot view yet (pair in the other direction first)"
        return "Dashboard sharing: Off"

    @staticmethod
    def _cluster_text(spec: LocalClusterSpec) -> str:
        if not spec.joined:
            return f"Not joined · Local role: {spec.local_role.title()}"
        coordinator = (
            spec.coordinator_display_name or spec.coordinator_node_id or "Unknown"
        )
        return f"Joined · Local role: {spec.local_role.title()} · Coordinator: {coordinator} · {node_presentation.status_label(spec.coordinator_status)}"

    @staticmethod
    def _selected_text(spec: NodeDescriptor | None) -> str:
        if spec is None:
            return "Selected node: none"
        trust = node_presentation.trust_label(spec.trust.value, is_local=spec.is_local)
        connection = node_presentation.status_label(spec.status.value)
        return f"Selected node: {spec.display_name} · {trust} · {connection}"

    def focus_back(self) -> None:
        self.back_button.setFocus()

    def scroll_to_top(self) -> None:
        self.scroll_area.verticalScrollBar().setValue(0)
