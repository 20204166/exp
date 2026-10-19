"""Qt composition root for the application during the shell cutover."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from maintenance.application_controller import (
    ApplicationController,
    default_application_dependencies,
)
from maintenance.components import local_scan_anchor
from maintenance.components.scan_support import call_legacy_compatible
from maintenance.diagnostics import (
    ClusterDiagnostic,
    DiagnosticsSnapshot,
    build_diagnostics_snapshot,
    serialize_diagnostics,
)
from maintenance.nodes import NodeCapability, NodeId, NodePermission
from maintenance.persistence import atomic_write_text
from maintenance.ui import scan_status
from maintenance.ui import styles as ui_styles
from maintenance.ui import window_components as ui_window_components
from maintenance.ui import window_node_actions as ui_node_actions
from maintenance.ui.help_content import HELP_TOPICS
from maintenance.ui.node_dialog_contracts import (
    ConnectionDialogCallbacks,
    NodeDetailsDialogCallbacks,
    NodeDetailsDialogSpec,
    PairingDialogSpec,
    SharingDialogCallbacks,
)
from maintenance.ui.qt_cluster import (
    QtClusterActionSpec,
    QtClusterCallbacks,
    QtClusterNodeSpec,
    QtClusterPage,
    QtClusterSummary,
)
from maintenance.ui.qt_dashboard import QtDashboard
from maintenance.ui.qt_diagnostics_page import QtDiagnosticsPage
from maintenance.ui.qt_help_page import QtHelpPage, QtHelpTopicPage
from maintenance.ui.qt_node_dialogs import (
    QtConnectionDialog,
    QtNodeDetailsDialog,
    QtPairingDialog,
    QtSharingDialog,
)
from maintenance.ui.qt_nodes_connections import (
    QtNodesConnectionsCallbacks,
    QtNodesConnectionsPage,
)
from maintenance.ui.qt_resource_dialogs import (
    QtInfoDialog,
    QtProcessDialog,
    QtStorageDialog,
)
from maintenance.ui.qt_settings import (
    QtPreferencesPage,
    QtSettingsCategorySpec,
    QtSettingsHome,
)
from maintenance.ui.qt_thermals_page import QtThermalsPage
from maintenance.ui.qt_window import QtWindowShell
from maintenance.ui.target_state import render_target_state
from maintenance.ui.window_discovery import DiscoveryRuntime
from maintenance.ui.window_supports.qt_timer_delivery import (
    QtDeliveryQueue,
    QtTimerDelivery,
)

LOGGER = logging.getLogger(__name__)
PERFORMANCE_CAPTURE_DIRECTORY = (
    Path(__file__).resolve().parents[2] / "docs" / "performance" / "observability"
)


class QtAppController(ApplicationController):
    """Compose shared application services with the Qt presentation shell."""

    dashboard_page: QtDashboard
    settings_home: QtSettingsHome
    preferences_page: QtPreferencesPage
    nodes_page: QtNodesConnectionsPage
    cluster_page: QtClusterPage
    thermals_page: QtThermalsPage
    help_page: QtHelpPage
    help_topic_pages: dict[str, QtHelpTopicPage]
    diagnostics_page: QtDiagnosticsPage
    qt_window: QtWindowShell
    status_label: Any
    analyze_button: Any
    cancel_button: Any
    _diagnostics_refresh_id: str | None

    def __init__(
        self,
        window: QtWindowShell,
        delivery: QtDeliveryQueue,
        timers: QtTimerDelivery,
        *,
        preferences_store: Any = None,
        cluster_store: Any = None,
        provision_target_grant: Callable[[Any], bool] | None = None,
    ) -> None:
        self.master = window
        self.qt_window = window
        self._qt_delivery_queue = delivery
        self._qt_timer_delivery = timers
        self._page_router = window._page_router
        super().__init__(
            master=window,
            dependencies=default_application_dependencies(
                preferences_store=preferences_store,
                cluster_store=cluster_store,
                provision_target_grant=provision_target_grant,
            ),
        )
        self._discovery_runtime = DiscoveryRuntime(
            approve_pairing=lambda title, message: self._confirm_pairing_fingerprints(
                title, message, parent=self.qt_window
            ),
            approve_elevation=lambda title, message: self._confirm_pairing_fingerprints(
                title, message, parent=self.qt_window
            ),
        )

    def _timer_delivery_for_window(self) -> Any:
        return self._qt_timer_delivery

    def _apply_appearance(self) -> None:
        colors = self.colors
        widgets = [
            self.qt_window,
            getattr(self, "dashboard_page", None),
            getattr(self, "settings_home", None),
            getattr(self, "preferences_page", None),
            getattr(self, "nodes_page", None),
            getattr(self, "cluster_page", None),
            getattr(self, "thermals_page", None),
            getattr(self, "help_page", None),
            *getattr(self, "help_topic_pages", {}).values(),
            getattr(self, "diagnostics_page", None),
        ]
        for widget in widgets:
            if widget is not None:
                ui_styles.configure_qt_styles(widget, colors=colors)

    def _navigate(self, key: str) -> None:
        self.qt_window.show_page(key)
        self._sync_render_visibility(key)
        self._set_diagnostics_visibility(key == "diagnostics")

    def _show_dashboard_page(self) -> None:
        self._navigate("dashboard")

    def _show_settings_page(self) -> None:
        self._navigate("settings")

    def _show_preferences_page(self) -> None:
        self._navigate("preferences")

    def _show_nodes_page(self) -> None:
        self._refresh_nodes_page()
        self._navigate("nodes")

    def _refresh_nodes_page(self) -> None:
        if not hasattr(self, "nodes_page"):
            return
        context = self._selected_context()
        self.nodes_page.refresh(
            discovery_enabled=self._cluster_state.discovery_enabled,
            discovered=self._nodes_peer_specs(),
            trusted=self._nodes_trusted_specs(),
            manual=self._nodes_manual_specs(),
            selected_node=context.descriptor if context is not None else None,
            local_cluster=self._nodes_cluster_spec(),
        )

    def _queue_discovery_presentation(self, trusted_involved: bool) -> None:
        del trusted_involved
        self._refresh_nodes_page()
        self._refresh_cluster_page()

    def _pair_discovered_node(self, node_id: str) -> None:
        """Open fingerprint review; only explicit confirmation starts pairing."""
        peers = {peer.node_id: peer for peer in self._nodes_peer_specs()}
        peer = peers.get(node_id)
        if peer is None:
            self._nodes_error("That peer is no longer visible on the network")
            QMessageBox.warning(
                self.qt_window,
                "Peer unavailable",
                "That peer is no longer visible on the network.",
            )
            return
        key = f"pairing:{node_id}"
        dialogs = self.__dict__.setdefault("_qt_dialogs", {})
        existing = dialogs.get(key)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return

        def confirm_pairing(confirmed_node_id: str) -> None:
            current = {item.node_id: item for item in self._nodes_peer_specs()}
            candidate = current.get(confirmed_node_id)
            if candidate is None:
                self._nodes_error("That peer is no longer visible on the network")
                dialog.show_error("That peer is no longer visible on the network")
                return
            if (
                candidate.identity_fingerprint != dialog.spec.identity_fingerprint
                or candidate.transport_fingerprint != dialog.spec.transport_fingerprint
            ):
                self._nodes_error("Peer fingerprints changed; review the node again")
                dialog.show_error("Peer fingerprints changed; review the node again")
                return
            ui_node_actions.pair_discovered_node_async(
                self,
                confirmed_node_id,
                messagebox_module=SimpleNamespace(
                    askyesno=self._confirm_pairing_fingerprints
                ),
                provision_target_grant=getattr(self, "_provision_target_grant", None),
                dialog=dialog,
            )

        def cancel_pairing(cancelled_node_id: str) -> None:
            if dialogs.get(key) is dialog:
                dialogs.pop(key, None)
            ui_node_actions.cancel_pairing(self, cancelled_node_id)

        def complete_pairing(completed_node_id: str) -> None:
            if completed_node_id == node_id and dialogs.get(key) is dialog:
                dialogs.pop(key, None)

        dialog = QtPairingDialog(
            self.qt_window,
            spec=PairingDialogSpec(
                node_id=peer.node_id,
                display_name=peer.hostname,
                identity_fingerprint=peer.identity_fingerprint,
                transport_fingerprint=peer.transport_fingerprint,
            ),
            on_pair=confirm_pairing,
            on_cancel=cancel_pairing,
            on_complete=complete_pairing,
            colors=self.colors,
        )
        dialogs[key] = dialog
        dialog.open()

    def _confirm_pairing_fingerprints(
        self, title: str, message: str, *, parent: Any
    ) -> bool:
        return (
            QMessageBox.question(
                parent,
                title,
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _nodes_status(self, message: str) -> None:
        if hasattr(self, "nodes_page"):
            self.nodes_page.status_label.setText(message)
            self.nodes_page.status_label.setProperty("role", "success")

    def _nodes_error(self, message: str) -> None:
        if hasattr(self, "nodes_page"):
            self.nodes_page.status_label.setText(message)
            self.nodes_page.status_label.setProperty("role", "danger")

    def _open_qt_node_details(self, node: Any) -> None:
        node_id = getattr(node, "node_id", node)
        specs = {item.node_id: item for item in self._nodes_trusted_specs()}
        specs.update({item.node_id: item for item in self._nodes_manual_specs()})
        spec = specs.get(node_id)
        discovered = None
        if spec is None:
            discovered = next(
                (item for item in self._nodes_peer_specs() if item.node_id == node_id),
                None,
            )
            if discovered is None:
                self._nodes_error("That node is no longer available")
                return
        key = f"node-details:{node_id}"
        dialogs = self.__dict__.setdefault("_qt_dialogs", {})
        existing = dialogs.get(key)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return
        if discovered is not None:
            details = NodeDetailsDialogSpec(
                node_id=discovered.node_id,
                display_name=discovered.hostname,
                hostname=discovered.hostname,
                host=discovered.hostname,
                port=discovered.port,
                pairing_state=discovered.pairing_state,
                target_state=(
                    "Compatible" if discovered.compatible else "Incompatible"
                ),
                identity_status="unverified",
                identity_fingerprint=discovered.identity_fingerprint,
                transport_fingerprint=discovered.transport_fingerprint,
            )
        else:
            assert spec is not None
            details = NodeDetailsDialogSpec(
                node_id=spec.node_id,
                display_name=spec.display_name,
                hostname=spec.hostname,
                host=spec.host,
                port=spec.port,
                pairing_state=spec.pairing_state,
                target_state=spec.target_state,
                role=spec.role,
                permissions=spec.permissions,
                selectable=spec.selectable,
                openable=spec.openable,
                is_manual=spec.is_manual,
                paused=spec.paused,
                role_editable=spec.role_editable,
                has_active_job=spec.has_active_job,
                identity_status=spec.identity_status,
                identity_fingerprint=spec.identity_fingerprint,
                transport_fingerprint=getattr(spec, "transport_fingerprint", None),
            )

        def dispatch(action: str, target: str) -> None:
            current = {item.node_id: item for item in self._nodes_trusted_specs()}
            current.update({item.node_id: item for item in self._nodes_manual_specs()})
            fresh = current.get(target)
            if fresh is None:
                return
            allowed = {
                "open": fresh.openable,
                "test": fresh.selectable,
                "pause": fresh.role_editable,
                "revoke": fresh.role_editable and not fresh.is_manual,
                "remove_connection": fresh.is_manual,
                "remove_job": fresh.role_editable
                and not fresh.is_manual
                and fresh.has_active_job,
            }.get(action, False)
            if not allowed:
                return
            if action == "open":
                self._open_cluster_node(target)
            elif action == "test":
                self._test_connection(target)
            elif action == "pause":
                self._apply_cluster_pause(target)
            else:
                confirm = SimpleNamespace(askyesno=self._confirm_cluster_action)
                handlers = {
                    "revoke": ui_node_actions.revoke_node,
                    "remove_connection": ui_node_actions.remove_connection_node,
                    "remove_job": ui_node_actions.remove_job_node,
                }
                handler = handlers.get(action)
                if handler is not None:
                    handler(self, target, messagebox_module=confirm)

        dialog: QtNodeDetailsDialog
        dialog = QtNodeDetailsDialog(
            self.qt_window,
            spec=details,
            callbacks=NodeDetailsDialogCallbacks(
                on_open=lambda target: dispatch("open", target),
                on_test=lambda target: dispatch("test", target),
                on_pause=lambda target: dispatch("pause", target),
                on_resume=lambda target: dispatch("pause", target),
                on_revoke=lambda target: dispatch("revoke", target),
                on_remove_connection=lambda target: dispatch(
                    "remove_connection", target
                ),
                on_remove_job=lambda target: dispatch("remove_job", target),
            ),
            colors=self.colors,
        )
        dialog.finished.connect(
            lambda _result: (
                dialogs.pop(key, None) if dialogs.get(key) is dialog else None
            )
        )
        if self._own_qt_dialog(key, dialog):
            dialog.setModal(False)

    def _rename_qt_node(self, node_id: str) -> None:
        spec = next(
            (item for item in self._nodes_trusted_specs() if item.node_id == node_id),
            None,
        )
        if spec is None:
            self._nodes_error("That trusted node is no longer available")
            return
        name, accepted = QInputDialog.getText(
            self.qt_window,
            "Rename Node",
            "Display name:",
            text=spec.display_name,
        )
        if accepted and name.strip():
            ui_node_actions.rename_node(
                self,
                node_id,
                simpledialog_module=SimpleNamespace(
                    askstring=lambda *_args, **_kwargs: name
                ),
            )

    def _set_qt_node_color(self, node_id: str, color: str) -> None:
        ui_node_actions.set_node_color(self, node_id, color)

    def _revoke_trusted_node(self, node_id: str) -> None:
        node = NodeId(node_id)
        generations = self.__dict__.setdefault("_activation_generations", {})
        generations[node] = generations.get(node, 0) + 1
        ui_node_actions.revoke_trusted_node(self, node_id)

    def _remove_qt_manual_host(self, node_id: str) -> None:
        if not any(spec.node_id == node_id for spec in self._nodes_manual_specs()):
            self._nodes_error("That manual host is no longer available")
            return
        ui_node_actions.remove_manual_host(
            self,
            node_id,
            messagebox_module=SimpleNamespace(askyesno=self._confirm_cluster_action),
        )

    def _dispatch_nodes_action(self, action: str, node_id: str) -> None:
        specs = {item.node_id: item for item in self._nodes_trusted_specs()}
        specs.update({item.node_id: item for item in self._nodes_manual_specs()})
        spec = specs.get(node_id)
        if spec is None:
            return
        allowed = {
            "revoke": not spec.is_manual,
            "pause": spec.role_editable and not spec.paused,
            "resume": spec.role_editable and spec.paused,
            "remove_connection": not spec.is_manual,
            "remove_job": spec.role_editable
            and not spec.is_manual
            and spec.has_active_job,
        }.get(action, False)
        if not allowed:
            return
        if action == "pause":
            self._pause_node(node_id)
        elif action == "resume":
            self._resume_node(node_id)
        else:
            handlers = {
                "revoke": ui_node_actions.revoke_node,
                "remove_connection": ui_node_actions.remove_connection_node,
                "remove_job": ui_node_actions.remove_job_node,
            }
            handler = handlers.get(action)
            if handler is not None:
                handler(
                    self,
                    node_id,
                    messagebox_module=SimpleNamespace(
                        askyesno=self._confirm_cluster_action
                    ),
                )

    def _open_qt_connection_dialog(self, node_spec: Any) -> None:
        current = next(
            (
                spec
                for spec in self._nodes_trusted_specs()
                if spec.node_id == node_spec.node_id
            ),
            None,
        )
        if current is None:
            self._nodes_error("That trusted node is no longer available")
            return
        dialog = QtConnectionDialog(
            self.qt_window,
            node_id=current.node_id,
            callbacks=ConnectionDialogCallbacks(on_test=self._test_connection),
            colors=self.colors,
        )
        dialog.name_input.setText(current.display_name)
        dialog.host_input.setText(current.host)
        if current.port is not None:
            dialog.port_input.setText(str(current.port))
        self._own_qt_dialog(f"connection:{current.node_id}", dialog)

    def _open_qt_sharing_dialog(self, node_id: str) -> None:
        spec = next(
            (
                item
                for item in self._cluster_specs()
                if item.node_id == node_id and item.is_local
            ),
            None,
        )
        policy = next(
            (item for item in self._qt_cluster_nodes() if item.node_id == node_id),
            None,
        )
        if (
            spec is None
            or policy is None
            or not any(
                action.key == "share_dashboard" and action.visible and action.enabled
                for action in policy.actions
            )
        ):
            return
        key = "dashboard-sharing"

        def confirm_share(expected_active: bool) -> bool:
            current_spec = next(
                (
                    item
                    for item in self._cluster_specs()
                    if item.node_id == node_id and item.is_local
                ),
                None,
            )
            current_policy = next(
                (item for item in self._qt_cluster_nodes() if item.node_id == node_id),
                None,
            )
            if (
                current_spec is None
                or current_policy is None
                or not any(
                    action.key == "share_dashboard"
                    and action.visible
                    and action.enabled
                    for action in current_policy.actions
                )
            ):
                return False
            if current_spec.share_active != expected_active:
                current_dialog = self.__dict__.get("_qt_dialogs", {}).get(key)
                if isinstance(current_dialog, QtSharingDialog):
                    current_dialog.set_active(current_spec.share_active)
                return False
            self._share_dashboard()
            return True

        dialog = QtSharingDialog(
            self.qt_window,
            active=spec.share_active,
            callbacks=SharingDialogCallbacks(
                on_share=lambda: confirm_share(False),
                on_stop=lambda: confirm_share(True),
            ),
            colors=self.colors,
        )
        dialog.finished.connect(
            lambda _result: (
                self.__dict__.get("_qt_dialogs", {}).pop(key, None)
                if self.__dict__.get("_qt_dialogs", {}).get(key) is dialog
                else None
            )
        )
        self._own_qt_dialog(key, dialog)

    def _show_cluster_page(self) -> None:
        self._refresh_cluster_page()
        self._navigate("cluster")

    def _show_thermals_page(self) -> None:
        self._navigate("thermals")

    def _show_help_page(self) -> None:
        self._navigate("help")

    def _show_help_topic_page(self, topic_key: str) -> None:
        key = f"help:{topic_key}"
        if key not in self.qt_window._page_router.registered_keys:
            self._show_help_page()
            return
        self._navigate(key)

    def _show_diagnostics_page(self) -> None:
        if self._developer_mode:
            self._navigate("diagnostics")

    def _set_busy(self, is_busy: bool) -> None:
        self.dashboard_page.set_scan_busy() if is_busy else self.dashboard_page.set_scan_ready()
        self.preferences_page.set_scan_busy() if is_busy else self.preferences_page.set_scan_ready()

    def _reset_progress_bar(self) -> None:
        self.dashboard_page.set_scan_ready()
        self.preferences_page.set_scan_ready()

    def _show_scan_cancelled_notice(self, message: str) -> None:
        self.dashboard_page.status_label.setText(message)
        self.preferences_page.status_label.setText(message)

    def _diagnostics_snapshot(self) -> DiagnosticsSnapshot:
        context = self._selected_context()
        scheduler = (
            context.scheduler if context is not None else self._component_scheduler
        )
        return build_diagnostics_snapshot(
            scheduler=scheduler,
            coordinator=self._coordinator,
            registry=self._node_registry,
            ui_coordinator=self._ui_coordinator,
            capabilities=getattr(context, "capabilities", self._capabilities),
            discovery_reason=getattr(
                self._coordinator.discovery, "unavailable_reason", None
            ),
            placement=self.__dict__.get("_last_placement_decision"),
            cluster=self._cluster_diagnostic(),
            observer=self._observer,
        )

    def _cluster_diagnostic(self) -> ClusterDiagnostic:
        assignment = self._cluster_state.local_assignment
        epoch = self._cluster_state.coordinator_epoch
        timeline = self._cluster_timeline
        standby = self._standby_buffer
        status = timeline.status() if timeline is not None else None
        standby_status = standby.status() if standby is not None else None
        return ClusterDiagnostic(
            role=", ".join(sorted(role.value for role in assignment.roles)),
            coordinator_id=epoch.coordinator_id.value
            if epoch is not None
            else "unknown",
            epoch=epoch.epoch if epoch is not None else 0,
            heartbeat_age_seconds=(
                max(0.0, time.time() - epoch.issued_at) if epoch is not None else None
            ),
            database_bytes=status.bytes_used if status is not None else 0,
            database_cap_bytes=status.max_bytes if status is not None else 2 * 1024**3,
            standby_bytes=standby_status.bytes_used
            if standby_status is not None
            else 0,
            standby_cap_bytes=standby_status.max_bytes
            if standby_status is not None
            else 0,
            retention_pressure=(
                "limit reached"
                if status is not None and status.history_writes_paused
                else "normal"
            ),
            last_snapshot_at=status.newest_at if status is not None else None,
            history_writes_paused=(
                status.history_writes_paused if status is not None else False
            ),
            failure=status.warning if status is not None else None,
        )

    def _copy_diagnostics(self, text: str) -> None:
        QApplication.clipboard().setText(text)

    def _save_performance_capture(self) -> str | None:
        if not self._developer_mode:
            return None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = PERFORMANCE_CAPTURE_DIRECTORY / f"observability-{stamp}.json"
        try:
            atomic_write_text(
                path,
                serialize_diagnostics(self._diagnostics_snapshot()),
                temp_prefix=".observability-",
                create_directory_message="Could not create capture directory",
                save_message="Could not write performance capture",
                save_error_factory=OSError,
                fsync_warning_template="Could not sync performance capture directory: %s",
                logger=LOGGER,
            )
        except OSError as error:
            LOGGER.warning("Could not save performance capture: %s", error)
            return None
        return str(path)

    def _refresh_diagnostics_page(self) -> None:
        if self._is_closing or self.qt_window.active_page != "diagnostics":
            return
        self.diagnostics_page.render(self._diagnostics_snapshot())
        self._diagnostics_refresh_id = self._schedule_timer(
            1000, self._refresh_diagnostics_page
        )

    def _show_progress(self, message: str) -> None:
        if self._is_closing:
            return
        self.__dict__["_scan_progress_count"] = (
            self.__dict__.get("_scan_progress_count", 0) + 1
        )
        count = self.__dict__["_scan_progress_count"]
        total = self._progress_total()
        self.dashboard_page.set_scan_progress(message, count, total)
        self.preferences_page.set_scan_progress(message, count, total)
        self.preferences_page.status_label.setText(
            scan_status.progress_text(message, count, total)
        )

    def _cancel_analysis(self) -> None:
        if self._analysis_cancel_event is None:
            return
        self._analysis_cancel_event.set()
        if self.dashboard_page.cancel_button is not None:
            self.dashboard_page.cancel_button.setEnabled(False)
        self.preferences_page.set_scan_cancelled()

    def _show_snapshot(self, snapshot: Any, *, node_snapshot: Any = None) -> None:
        if self._is_closing:
            return
        merged = self._merge_snapshot(snapshot)
        self.snapshot = merged
        context = self._selected_context()
        if context is not None:
            context.snapshot = merged
            if node_snapshot is not None:
                context.node_snapshot = node_snapshot
        if self._coordinator is not None:
            self._coordinator.store(self._operation_key("snapshot:dashboard"), merged)
        for resource in snapshot.resources:
            self._observe_capability(resource.key, resource)
            self._record_thermal_summary(resource.key, resource)
        self.dashboard_page.set_summaries(merged.resources)
        self._full_snapshot_applied_at = time.monotonic()
        self._set_busy(False)
        self.dashboard_page.set_scan_complete(self._progress_total())
        self.preferences_page.set_scan_complete(self._progress_total())
        self._refresh_thermals_page(
            self._thermal_render_state(context) if context is not None else None
        )
        self._component_scheduler.mark_all_refreshed(time.monotonic())
        self._schedule_component_poll(force=True)

    def _apply_component(self, key: str, resource: Any) -> None:
        self.dashboard_page.cards[key].update_summary(resource)

    def _qt_cluster_summary(self) -> QtClusterSummary:
        epoch = self._cluster_state.coordinator_epoch
        return QtClusterSummary(
            self._cluster_state.cluster_id,
            epoch.coordinator_id.value if epoch is not None else None,
            epoch.epoch if epoch is not None else None,
        )

    def _qt_cluster_nodes(self) -> tuple[QtClusterNodeSpec, ...]:
        nodes: list[QtClusterNodeSpec] = []
        coordinator_id = self._qt_cluster_summary().coordinator_id
        for spec in self._cluster_specs():
            actions: list[QtClusterActionSpec] = []
            if spec.selectable:
                actions.append(
                    QtClusterActionSpec("open", "Open", True, spec.status != "offline")
                )
            if spec.role_editable and not spec.is_local:
                actions.append(
                    QtClusterActionSpec(
                        "pause",
                        "Re-enable" if spec.paused else "Pause",
                        True,
                        True,
                    )
                )
                actions.extend(
                    (
                        QtClusterActionSpec("revoke", "Revoke", True, True, "revoke"),
                        QtClusterActionSpec(
                            "remove_connection",
                            "Remove connection",
                            True,
                            True,
                            "remove_connection",
                        ),
                    )
                )
                if spec.has_active_job:
                    actions.append(
                        QtClusterActionSpec(
                            "remove_job", "Remove job", True, True, "remove_job"
                        )
                    )
            if spec.is_local and spec.role_editable and spec.role == "coordinator":
                actions.append(
                    QtClusterActionSpec("create_invite", "Create invite", True, True)
                )
            if spec.is_local:
                actions.append(
                    QtClusterActionSpec(
                        "share_dashboard",
                        "Stop sharing" if spec.share_active else "Share dashboard",
                        True,
                        True,
                    )
                )
            if (
                not spec.is_local
                and spec.trust in ("trusted", "authorised")
                and not spec.is_cluster_member
            ):
                actions.append(
                    QtClusterActionSpec("join_cluster", "Join cluster", True, True)
                )
            nodes.append(
                QtClusterNodeSpec(
                    node_id=spec.node_id,
                    display_name=spec.display_name,
                    hostname=spec.hostname,
                    trust_state=spec.trust,
                    connection_state=spec.status,
                    cluster_member=spec.is_cluster_member,
                    roles=(spec.role,) if spec.is_cluster_member else (),
                    coordinator_id=coordinator_id,
                    paused=spec.paused,
                    actions=tuple(actions),
                )
            )
        return tuple(nodes)

    def _apply_cluster_pause(self, node_id: str) -> None:
        spec = next(
            (item for item in self._cluster_specs() if item.node_id == node_id), None
        )
        if spec is None:
            return
        if spec.paused:
            self._resume_node(node_id)
        else:
            self._pause_node(node_id)

    def _confirm_cluster_action(self, title: str, message: str, *, parent: Any) -> bool:
        return (
            QMessageBox.question(
                parent,
                title,
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _dispatch_cluster_action(self, action: str, node_id: str) -> None:
        spec = next(
            (item for item in self._cluster_specs() if item.node_id == node_id), None
        )
        if spec is None:
            return
        policy = next(
            (item for item in self._qt_cluster_nodes() if item.node_id == node_id), None
        )
        if policy is None or not any(
            item.key == action and item.visible and item.enabled
            for item in policy.actions
        ):
            return
        if action == "open":
            self._open_cluster_node(node_id)
        elif action == "pause":
            self._apply_cluster_pause(node_id)
        elif action == "create_invite":
            blob = ui_node_actions.create_cluster_invite(self)
            if blob is not None:
                QMessageBox.information(
                    self.qt_window,
                    "Cluster invite",
                    f"Give this invite to the other machine; it expires soon:\n\n{blob}",
                )
        elif action == "join_cluster":
            blob, accepted = QInputDialog.getText(
                self.qt_window,
                "Join cluster",
                "Paste the invite from the other machine:",
            )
            if accepted and blob.strip():
                ui_node_actions.join_cluster_via_invite(self, node_id, blob.strip())
        elif action == "share_dashboard":
            self._open_qt_sharing_dialog(node_id)
        else:
            confirm = SimpleNamespace(askyesno=self._confirm_cluster_action)
            handlers = {
                "revoke": lambda: ui_node_actions.revoke_node(
                    self, node_id, messagebox_module=confirm
                ),
                "remove_connection": lambda: ui_node_actions.remove_connection_node(
                    self, node_id, messagebox_module=confirm
                ),
                "remove_job": lambda: ui_node_actions.remove_job_node(
                    self, node_id, messagebox_module=confirm
                ),
            }
            handler = handlers.get(action)
            if handler is not None:
                handler()

    def _refresh_cluster_page(self) -> None:
        if not hasattr(self, "cluster_page"):
            return
        self.cluster_page.refresh(self._qt_cluster_summary(), self._qt_cluster_nodes())

    def _show_error(self, message: str) -> None:
        self.dashboard_page.set_scan_error(message)
        self.preferences_page.set_scan_error(message)

    def _show_ready_after_completion_hold(self) -> None:
        if not self._is_closing and not self._scan_coordinator_state().active:
            self.dashboard_page.set_scan_ready()
            self.preferences_page.set_scan_ready()

    def _submit_ui(self, callback: Callable[[], None]) -> None:
        self._qt_delivery_queue.submit(callback)

    def _reconcile_cards_and_polling(self) -> None:
        scheduler = self.__dict__.get("_component_scheduler")
        if scheduler is None:
            return
        features = self._feature_catalog.all()
        for feature in features:
            self.dashboard_page.set_card_visible(
                feature.key, self._is_card_visible(feature.key)
            )
            if ui_window_components.polling_policy(self, feature.key):
                scheduler.pause(feature.key)
                continue
            was_paused = scheduler.is_paused(feature.key)
            scheduler.resume(feature.key)
            if was_paused:
                self._request_component_refresh(feature.key)

    def _layout_dashboard_cards(self) -> None:
        for feature in self._feature_catalog.all():
            self.dashboard_page.set_card_visible(
                feature.key, self._is_card_visible(feature.key)
            )

    @staticmethod
    def _invoke_delivered(callback: Callable[[], None]) -> None:
        callback()

    def _close(self) -> None:
        if self._is_closing:
            return
        self._is_closing = True
        self._finalize_shutdown()
        if self._analysis_cancel_event is not None:
            self._analysis_cancel_event.set()
        self._analysis_cancel_event = None
        self._stop_all_node_workers()
        for dialog in tuple(self.__dict__.get("_qt_dialogs", {}).values()):
            dialog.close()
        self._qt_delivery_queue.close()
        self._qt_timer_delivery.close()

    def open_resource(self, resource_key: str) -> None:
        if self.snapshot is None:
            QMessageBox.information(
                self.qt_window,
                "Scan Required",
                "Run the system scan before opening resource details.",
            )
            return
        summary = self.snapshot.get(resource_key)
        feature = self._feature_catalog.get(resource_key)
        context = self._selected_context()
        if (
            context is not None
            and not render_target_state(
                context.descriptor, context.snapshot, resource_key
            ).can_review
        ):
            self._nodes_error(
                f"{context.descriptor.display_name} is not available for {resource_key} review"
            )
            return
        if feature.action_kind == "process":
            self._open_process_dialog(resource_key, context)
            return
        if feature.action_kind == "storage":
            self._open_storage_dialog(context)
            return
        if feature.action_kind != "informational":
            self._nodes_error(f"No Qt review surface is registered for {feature.title}")
            return
        dialog_key = f"resource:{resource_key}"
        dialogs = self.__dict__.setdefault("_qt_dialogs", {})
        existing = dialogs.get(dialog_key)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return
        dialog = QtInfoDialog(
            summary,
            on_close=lambda: dialogs.pop(dialog_key, None),
            colors=self.colors,
        )
        dialogs[dialog_key] = dialog
        dialog.open()

    def _own_qt_dialog(self, key: str, dialog: Any) -> bool:
        dialogs = self.__dict__.setdefault("_qt_dialogs", {})
        existing = dialogs.get(key)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return False
        dialogs[key] = dialog
        dialog.open()
        return True

    def _open_process_dialog(self, resource_key: str, context: Any) -> None:
        if context is not None and not (
            context.descriptor.has(NodeCapability.PROCESS_REVIEW)
            and NodePermission.PROCESS_REVIEW in context.descriptor.permissions
        ):
            self._nodes_error("This node is not authorised for process review")
            return
        read_only = context is not None and not (
            context.descriptor.has(NodeCapability.PROCESS_TERMINATION)
            and NodePermission.PROCESS_TERMINATION in context.descriptor.permissions
        )
        provider = context.provider if context is not None else self.analyzer
        manager = (
            context.process_manager if context is not None else self.process_manager
        )
        node_id = context.node_id if context is not None else None
        node_title = (
            context.descriptor.display_name
            if context is not None and self._multi_node_selectable()
            else "This System"
        )
        key = f"resource:{resource_key}"
        dialog: QtProcessDialog
        cancel_events = self.__dict__.setdefault("_qt_dialog_cancel_events", {})

        def is_open() -> bool:
            return self.__dict__.get("_qt_dialogs", {}).get(key) is dialog

        def refresh() -> None:
            cancel_event = threading.Event()
            cancel_events[key] = cancel_event
            dialog.set_action_state(busy=True, message="Analyzing processes…")

            def task() -> Any:
                return call_legacy_compatible(
                    lambda: provider.process_candidates(cancel_event=cancel_event),
                    lambda: provider.process_candidates(),
                )

            def complete(candidates: Any) -> None:
                cancel_events.pop(key, None)
                if is_open():
                    dialog.update_candidates(candidates)

            def failed(error: Exception) -> None:
                cancel_events.pop(key, None)
                if is_open():
                    dialog.set_action_result(str(error))

            self._run_daemon(
                task,
                complete,
                failed,
            )

        def process_action(
            action: Callable[[list[int], dict[int, float]], Any],
            pids: list[int],
            create_times: dict[int, float],
            action_name: str,
        ) -> None:
            dialog.set_action_state(busy=True, message=f"{action_name} in progress…")

            def task() -> Any:
                return action(pids, create_times)

            def complete(result: Any) -> None:
                if not is_open():
                    return
                message = (
                    f"Stopped {len(result.stopped)} process(es)."
                    if not result.errors
                    else " ".join(result.errors)
                )
                dialog.set_action_result(message)
                self._rescan_node_after_change(node_id)

            self._run_daemon(
                task,
                complete,
                lambda error: (
                    dialog.set_action_result(str(error)) if is_open() else None
                ),
            )

        def close_process_dialog() -> None:
            pending = cancel_events.pop(key, None)
            if pending is not None:
                pending.set()
            self.__dict__.get("_qt_dialogs", {}).pop(key, None)

        dialog = QtProcessDialog(
            resource_key=resource_key,
            node_title=node_title,
            read_only=read_only,
            on_refresh=refresh,
            on_quit=lambda pids, times: process_action(
                manager.request_quit, pids, times, "Normal quit"
            ),
            on_force_quit=lambda pids, times: process_action(
                manager.force_quit, pids, times, "Force quit"
            ),
            on_close=close_process_dialog,
            colors=self.colors,
        )
        if self._own_qt_dialog(key, dialog):
            refresh()

    def _open_storage_dialog(self, context: Any) -> None:
        if context is not None and not (
            context.descriptor.has(NodeCapability.STORAGE_REVIEW)
            and NodePermission.STORAGE_REVIEW in context.descriptor.permissions
        ):
            self._nodes_error("This node is not authorised for storage review")
            return
        provider = context.provider if context is not None else self.analyzer
        manager = context.file_manager if context is not None else self.file_manager
        node_id = context.node_id if context is not None else None
        local_target = context is None or context.descriptor.is_local
        node_title = (
            context.descriptor.display_name
            if context is not None and self._multi_node_selectable()
            else "This System"
        )
        scan_root = (
            None
            if not local_target or not self._preferences.full_system_scan_enabled
            else local_scan_anchor()
        )
        key = "resource:storage"
        dialog: QtStorageDialog
        cancel_event: threading.Event | None = None

        def is_open() -> bool:
            return self.__dict__.get("_qt_dialogs", {}).get(key) is dialog

        def scan() -> None:
            nonlocal cancel_event
            cancel_event = threading.Event()
            dialog.set_scan_state("Scanning storage candidates…", busy=True)

            def progress(message: str) -> None:
                self._submit_ui(
                    lambda: (
                        dialog.set_scan_state(message, busy=True) if is_open() else None
                    )
                )

            def task() -> Any:
                return call_legacy_compatible(
                    lambda: provider.storage_candidates(
                        progress_callback=progress,
                        cancel_event=cancel_event,
                        scan_root=scan_root,
                    ),
                    lambda: provider.storage_candidates(),
                )

            def complete(candidates: Any) -> None:
                if is_open():
                    dialog.update_candidates(candidates)
                    dialog.set_scan_state("Scan complete", busy=False)

            def failed(error: Exception) -> None:
                if is_open():
                    dialog.set_scan_state(str(error), busy=False, error=True)

            self._run_daemon(
                task,
                complete,
                failed,
            )

        def cancel_scan() -> None:
            if cancel_event is not None:
                cancel_event.set()

        def move_selected(candidates: list[Any]) -> None:
            dialog.set_action_state(busy=True, message="Moving files to Trash…")

            def task() -> Any:
                return manager.move_to_trash(
                    [candidate.path for candidate in candidates]
                )

            def complete(result: Any) -> None:
                if not is_open():
                    return
                dialog.set_action_state(
                    busy=False,
                    message=f"Moved {len(result.moved)} file(s) to Trash."
                    if not result.errors
                    else " ".join(result.errors),
                )
                self._rescan_node_after_change(node_id)

            def failed(error: Exception) -> None:
                if is_open():
                    dialog.set_action_state(busy=False, message=str(error))

            self._run_daemon(
                task,
                complete,
                failed,
            )

        def close_storage_dialog() -> None:
            if cancel_event is not None:
                cancel_event.set()
            self.__dict__.get("_qt_dialogs", {}).pop(key, None)

        dialog = QtStorageDialog(
            node_title=node_title,
            read_only=not local_target,
            scan_root_label=str(scan_root) if scan_root is not None else None,
            on_scan=scan,
            on_cancel_scan=cancel_scan,
            on_move_selected=move_selected,
            on_close=close_storage_dialog,
            colors=self.colors,
        )
        self._own_qt_dialog(key, dialog)


class QtAppWindow(QtWindowShell):
    """Compose the Qt pages and the application controller into one window."""

    dashboard_page: QtDashboard
    settings_home: QtSettingsHome
    preferences_page: QtPreferencesPage
    nodes_page: QtNodesConnectionsPage
    cluster_page: QtClusterPage
    thermals_page: QtThermalsPage
    help_page: QtHelpPage
    help_topic_pages: dict[str, QtHelpTopicPage]

    def __init__(
        self,
        *,
        preferences_store: Any = None,
        cluster_store: Any = None,
        provision_target_grant: Callable[[Any], bool] | None = None,
    ) -> None:
        super().__init__(title="System Analyzer", on_close=self._close)
        ui_styles.configure_qt_styles(self)
        self.delivery = QtDeliveryQueue(parent=self)
        self.timers = QtTimerDelivery(parent=self)
        self.controller = QtAppController(
            self,
            self.delivery,
            self.timers,
            preferences_store=preferences_store,
            cluster_store=cluster_store,
            provision_target_grant=provision_target_grant,
        )
        self._build_qt_pages()
        for name in (
            "dashboard_page",
            "settings_home",
            "preferences_page",
            "nodes_page",
            "cluster_page",
            "thermals_page",
            "help_page",
            "help_topic_pages",
        ):
            setattr(self, name, getattr(self.controller, name))
        self.controller._apply_appearance()
        self.controller._start_peer_listener()
        self.controller._start_discovery()
        self.controller._schedule_timer(350, self.controller.handle_analyze)

    def _build_qt_pages(self) -> None:
        controller = self.controller
        controller.__dict__["help_topic_pages"] = {}
        controller.dashboard_page = QtDashboard(
            controller._feature_catalog.all(),
            on_open=controller.open_resource,
            on_scan=controller.handle_analyze,
            on_cancel=controller._cancel_analysis,
            button_coordinator=controller._button_coordinator,
            colors=controller.colors,
        )
        controller.__dict__["cards"] = controller.dashboard_page.cards
        controller.__dict__["dashboard"] = controller.dashboard_page
        controller.status_label = controller.dashboard_page.status_label
        controller.analyze_button = controller.dashboard_page.scan_button
        controller.cancel_button = controller.dashboard_page.cancel_button
        self.register_page("dashboard", controller.dashboard_page)

        categories = tuple(
            QtSettingsCategorySpec(item.key, item.title, item.description)
            for item in controller._settings_categories()
        )
        controller.settings_home = QtSettingsHome(
            categories,
            on_select_category=controller._on_select_settings_category,
            on_back=controller._show_dashboard_page,
            button_coordinator=controller._button_coordinator,
            colors=controller.colors,
        )
        self.register_page("settings", controller.settings_home)

        intervals = tuple(
            (
                item.key,
                item.title,
                item.seconds,
                item.minimum_seconds,
                item.maximum_seconds,
                item.step_seconds,
            )
            for item in controller._interval_specs()
        )
        cards = tuple(
            (item.key, item.title, item.enabled) for item in controller._card_specs()
        )
        controller.preferences_page = QtPreferencesPage(
            callbacks=SimpleNamespace(
                on_back=controller._show_settings_page,
                on_interval_commit=controller._on_interval_commit,
                on_card_visibility_change=controller._on_card_visibility_change,
                on_auto_hide_change=controller._on_auto_hide_change,
                on_scan=controller.handle_analyze,
                on_cancel_scan=controller._cancel_analysis,
                on_reset=self._on_reset,
                on_full_system_scan_change=controller._on_full_system_scan_change,
                on_appearance_change=controller._on_appearance_change,
            ),
            intervals=intervals,
            cards=cards,
            hide_unavailable_cards=controller._preferences.hide_unavailable_cards,
            full_system_scan_enabled=controller._preferences.full_system_scan_enabled,
            appearance=controller._preferences.appearance,
            button_coordinator=controller._button_coordinator,
            colors=controller.colors,
        )
        self.register_page("preferences", controller.preferences_page)

        controller.nodes_page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=controller._show_settings_page,
                on_discovery_toggle=controller._apply_discovery_enabled,
                on_pair=controller._pair_discovered_node,
                on_reject=controller._reject_discovered_node,
                on_select_node=lambda node_id: controller._switch_selected_node(
                    NodeId(node_id)
                ),
                on_open_node=controller._open_cluster_node,
                on_test_connection=controller._test_connection,
                on_refresh=controller._refresh_nodes_page,
                on_details=controller._open_qt_node_details,
                on_rename=controller._rename_qt_node,
                on_color=controller._set_qt_node_color,
                on_permissions=controller._set_node_permissions,
                on_role_change=controller._set_node_roles,
                on_remove_manual=controller._remove_qt_manual_host,
                on_revoke=lambda node_id: controller._dispatch_nodes_action(
                    "revoke", node_id
                ),
                on_pause=lambda node_id: controller._dispatch_nodes_action(
                    "pause", node_id
                ),
                on_resume=lambda node_id: controller._dispatch_nodes_action(
                    "resume", node_id
                ),
                on_remove_connection=lambda node_id: controller._dispatch_nodes_action(
                    "remove_connection", node_id
                ),
                on_remove_job=lambda node_id: controller._dispatch_nodes_action(
                    "remove_job", node_id
                ),
                on_start_discovery=controller._start_discovery,
                on_learn_pairing=lambda: controller._show_help_topic_page(
                    "pairing-trust"
                ),
                on_open_connection=controller._open_qt_connection_dialog,
                on_share_dashboard=controller._share_dashboard_with_coordinator,
            ),
            discovery_enabled=controller._cluster_state.discovery_enabled,
            discovered=controller._nodes_peer_specs(),
            trusted=controller._nodes_trusted_specs(),
            manual=controller._nodes_manual_specs(),
            selected_node=(
                context.descriptor
                if (context := controller._selected_context()) is not None
                else None
            ),
            local_cluster=controller._nodes_cluster_spec(),
            colors=controller.colors,
        )
        self.register_page("nodes", controller.nodes_page)

        summary = controller._qt_cluster_summary()
        cluster_nodes = controller._qt_cluster_nodes()
        controller.cluster_page = QtClusterPage(
            summary,
            cluster_nodes,
            callbacks=QtClusterCallbacks(
                on_back=controller._show_dashboard_page,
                on_action={
                    key: (
                        lambda node_id, _intent, key=key: (
                            controller._dispatch_cluster_action(key, node_id)
                        )
                    )
                    for key in (
                        "open",
                        "pause",
                        "revoke",
                        "remove_connection",
                        "remove_job",
                        "create_invite",
                        "join_cluster",
                        "share_dashboard",
                    )
                },
            ),
            colors=controller.colors,
        )
        self.register_page("cluster", controller.cluster_page)

        controller.thermals_page = QtThermalsPage(
            on_back=controller._show_dashboard_page,
            on_learn_more=lambda: controller._show_help_topic_page("thermals"),
            button_coordinator=controller._button_coordinator,
            colors=controller.colors,
        )
        self.register_page("thermals", controller.thermals_page)

        controller.help_page = QtHelpPage(
            on_back=controller._show_settings_page,
            on_open_topic=controller._show_help_topic_page,
            topics=HELP_TOPICS,
            colors=controller.colors,
        )
        self.register_page("help", controller.help_page)
        for topic in HELP_TOPICS:
            page = QtHelpTopicPage(
                topic,
                on_back=controller._show_help_page,
                colors=controller.colors,
            )
            controller.help_topic_pages[topic.key] = page
            self.register_page(f"help:{topic.key}", page)

        if controller._developer_mode:
            controller.diagnostics_page = QtDiagnosticsPage(
                controller._diagnostics_snapshot(),
                on_back=controller._show_settings_page,
                on_copy=controller._copy_diagnostics,
                on_save_capture=controller._save_performance_capture,
                developer_mode_visible=True,
                colors=controller.colors,
            )
            self.register_page("diagnostics", controller.diagnostics_page)
        self.show_page("dashboard")
        controller._sync_render_visibility("dashboard")
        controller._reconcile_cards_and_polling()

    def _close(self) -> None:
        self.controller._close()

    def _on_reset(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset Preferences?",
            "Reset all preferences to their defaults?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            from maintenance.preferences import AppPreferences

            self.controller._apply_preferences(AppPreferences.defaults())

    def run(self) -> None:
        application = QApplication.instance()
        if application is not None:
            self.show()
            application.exec()
