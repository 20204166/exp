"""Application-window integration tests for the Qt cutover."""

from __future__ import annotations

import threading
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtWidgets import QMainWindow, QMessageBox

from maintenance.cluster import ClusterState, ClusterStore
from maintenance.preferences import PreferencesStore
from maintenance.ui.page_specs import (
    ClusterNodeSpec,
    DiscoveredPeerSpec,
    TrustedNodeSpec,
)
from maintenance.ui.qt_app_window import QtAppController, QtAppWindow
from maintenance.ui.qt_node_dialogs import (
    QtConnectionDialog,
    QtNodeDetailsDialog,
    QtPairingDialog,
    QtSharingDialog,
)
from maintenance.ui.qt_resource_dialogs import QtInfoDialog
from maintenance.ui.qt_window import QtWindowShell
from tests.support.models import make_snapshot, make_summary
from tests.support.qt import get_qapplication


class QtAppWindowTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def test_application_window_is_a_native_qt_main_window(self) -> None:
        self.assertTrue(issubclass(QtAppWindow, QMainWindow))

    def test_qt_controller_uses_toolkit_neutral_application_controller(self) -> None:
        from maintenance.application_controller import ApplicationController

        self.assertTrue(issubclass(QtAppController, ApplicationController))

    def test_run_shows_window_before_entering_event_loop(self) -> None:
        from PySide6.QtWidgets import QApplication

        window = QtAppWindow.__new__(QtAppWindow)
        QtWindowShell.__init__(window, title="Test")
        with patch.object(QApplication, "exec", return_value=0) as event_loop:
            window.run()
        self.assertTrue(window.isVisible())
        event_loop.assert_called_once_with()
        window.close()

    def test_window_builds_retained_dashboard_and_settings_pages(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = PreferencesStore(root / "preferences.json")
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=preferences,
                    cluster_store=cluster,
                )

            self.assertEqual(window.active_page, "dashboard")
            self.assertIsNotNone(window.page("dashboard"))
            self.assertIsNotNone(window.page("settings"))
            self.assertIs(window.dashboard_page, window.controller.dashboard_page)
            window.show_page("settings")
            self.assertEqual(window.active_page, "settings")
            window.show_page("dashboard")
            window.close()

    def test_startup_restores_state_then_starts_listener_and_defers_first_scan(
        self,
    ) -> None:
        events: list[object] = []
        with TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = PreferencesStore(root / "preferences.json")
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            original_preferences_load = preferences.load
            original_cluster_load = cluster.load

            def load_preferences():
                events.append("preferences-loaded")
                return original_preferences_load()

            def load_cluster():
                events.append("cluster-loaded")
                return original_cluster_load()

            def start_listener(_controller):
                events.append("listener-started")

            def schedule(_controller, delay, callback):
                events.append(("scan-scheduled", delay, callback.__name__))
                return "timer-id"

            with (
                patch.object(preferences, "load", side_effect=load_preferences),
                patch.object(cluster, "load", side_effect=load_cluster),
                patch.object(QtAppController, "_start_peer_listener", start_listener),
                patch.object(QtAppController, "_schedule_timer", schedule),
            ):
                window = QtAppWindow(
                    preferences_store=preferences,
                    cluster_store=cluster,
                )

            self.assertLess(
                events.index("preferences-loaded"), events.index("listener-started")
            )
            self.assertLess(
                events.index("cluster-loaded"), events.index("listener-started")
            )
            self.assertIn("listener-started", events)
            discovery_session = window.controller.__dict__.get("_discovery_session")
            assert discovery_session is not None
            self.assertFalse(discovery_session._active)
            self.assertIn(("scan-scheduled", 350, "handle_analyze"), events)
            self.assertFalse(window.isVisible())
            window.close()

    def test_close_suppresses_pending_qt_delivery_and_timer_callbacks(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            delivered: list[str] = []
            cancellation = threading.Event()
            window.controller._analysis_cancel_event = cancellation
            window.delivery.submit(lambda: delivered.append("worker"))
            window.timers.schedule(0, lambda: delivered.append("timer"))
            window.close()
            window.close()
            self.app.processEvents()

            self.assertEqual(delivered, [])
            self.assertTrue(cancellation.is_set())
            self.assertTrue(window.controller._is_closing)

    def test_controller_builds_a_toolkit_neutral_diagnostics_snapshot(self) -> None:
        from maintenance.diagnostics import DiagnosticsSnapshot

        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            self.assertIsInstance(
                window.controller._diagnostics_snapshot(), DiagnosticsSnapshot
            )
            window.close()

    def test_startup_appearance_uses_the_persisted_accent_theme(self) -> None:
        from maintenance.preferences import AppPreferences
        from maintenance.ui.styles import accent_theme_colors

        with TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = PreferencesStore(root / "preferences.json")
            preferences.save(replace(AppPreferences.defaults(), appearance="rose"))
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=preferences,
                    cluster_store=cluster,
                )

            self.assertEqual(window.controller.colors, accent_theme_colors("rose"))
            self.assertIn(accent_theme_colors("rose")["accent"], window.styleSheet())
            window.close()

    def test_discovery_approval_prompts_are_owned_by_the_qt_shell(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
                patch.object(
                    QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
                ) as question,
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )
                runtime = window.controller._discovery_runtime
                self.assertTrue(runtime.approve_pairing("Pair", "Review"))
                self.assertTrue(runtime.approve_elevation("Access", "Review"))

            self.assertEqual(question.call_count, 2)
            window.close()

    def test_cluster_page_projects_the_controller_node_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            expected = {spec.node_id for spec in window.controller._cluster_specs()}
            self.assertTrue(expected)
            self.assertEqual(set(window.cluster_page.node_labels), expected)
            window.close()

    def test_cluster_projection_offers_create_invite_and_join_actions(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            local = ClusterNodeSpec(
                node_id="local",
                display_name="This System",
                hostname="localhost",
                color=None,
                trust="local",
                status="online",
                capabilities=(),
                is_local=True,
                selectable=False,
                role="coordinator",
                role_editable=True,
                share_active=True,
            )
            trusted_peer = ClusterNodeSpec(
                node_id="peer",
                display_name="Peer",
                hostname="peer-host",
                color=None,
                trust="trusted",
                status="offline",
                capabilities=(),
                is_local=False,
                selectable=True,
                is_cluster_member=False,
            )
            with patch.object(
                window.controller, "_cluster_specs", return_value=(local, trusted_peer)
            ):
                projected = {
                    spec.node_id: {action.key for action in spec.actions}
                    for spec in window.controller._qt_cluster_nodes()
                }

            self.assertIn("create_invite", projected["local"])
            self.assertIn("share_dashboard", projected["local"])
            self.assertIn("join_cluster", projected["peer"])
            window.close()

    def test_cluster_dashboard_share_action_opens_retained_dialog(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )
            local = ClusterNodeSpec(
                node_id="local",
                display_name="This System",
                hostname="localhost",
                color=None,
                trust="local",
                status="online",
                capabilities=(),
                is_local=True,
                selectable=False,
                role="coordinator",
                role_editable=True,
                share_active=True,
            )
            with (
                patch.object(
                    window.controller, "_cluster_specs", return_value=(local,)
                ),
                patch.object(window.controller, "_share_dashboard") as share,
            ):
                window.controller._dispatch_cluster_action("share_dashboard", "local")
                dialog = window.controller.__dict__["_qt_dialogs"]["dashboard-sharing"]
                self.assertIsInstance(dialog, QtSharingDialog)
                self.assertTrue(dialog.active)
                self.assertEqual(dialog.action_button.text(), "Stop sharing")
                dialog.action_button.click()
            share.assert_called_once_with()
            window.close()

    def test_cluster_invite_dispatch_uses_existing_policy_and_qt_notice(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )
            local = ClusterNodeSpec(
                node_id="local",
                display_name="This System",
                hostname="localhost",
                color=None,
                trust="local",
                status="online",
                capabilities=(),
                is_local=True,
                selectable=False,
                role="coordinator",
                role_editable=True,
            )
            with (
                patch.object(
                    window.controller, "_cluster_specs", return_value=(local,)
                ),
                patch(
                    "maintenance.ui.qt_app_window.ui_node_actions.create_cluster_invite",
                    return_value="opaque-invite",
                ) as create_invite,
                patch("maintenance.ui.qt_app_window.QMessageBox.information") as notice,
            ):
                window.controller._dispatch_cluster_action("create_invite", "local")

            create_invite.assert_called_once_with(window.controller)
            self.assertIn("opaque-invite", notice.call_args.args[2])
            window.close()

    def test_cluster_join_dispatch_uses_qt_input_and_existing_policy(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )
            peer = ClusterNodeSpec(
                node_id="peer",
                display_name="Peer",
                hostname="peer-host",
                color=None,
                trust="trusted",
                status="online",
                capabilities=(),
                is_local=False,
                selectable=True,
                is_cluster_member=False,
            )
            with (
                patch.object(window.controller, "_cluster_specs", return_value=(peer,)),
                patch(
                    "maintenance.ui.qt_app_window.QInputDialog.getText",
                    return_value=("opaque-invite", True),
                ) as prompt,
                patch(
                    "maintenance.ui.qt_app_window.ui_node_actions.join_cluster_via_invite"
                ) as join,
            ):
                window.controller._dispatch_cluster_action("join_cluster", "peer")

            prompt.assert_called_once_with(
                window,
                "Join cluster",
                "Paste the invite from the other machine:",
            )
            join.assert_called_once_with(window.controller, "peer", "opaque-invite")
            window.close()

    def test_nodes_page_wires_management_and_dialog_callbacks(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            callbacks = window.nodes_page.callbacks
            for callback_name in (
                "on_rename",
                "on_color",
                "on_permissions",
                "on_role_change",
                "on_remove_manual",
                "on_revoke",
                "on_pause",
                "on_resume",
                "on_remove_connection",
                "on_remove_job",
                "on_start_discovery",
                "on_learn_pairing",
                "on_open_connection",
                "on_share_dashboard",
            ):
                with self.subTest(callback=callback_name):
                    self.assertIsNotNone(getattr(callbacks, callback_name))
            window.close()

    def test_open_connection_callback_opens_retained_qt_dialog(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )
            spec = TrustedNodeSpec(
                "peer",
                "Peer",
                "peer.example",
                None,
                "online",
                "192.0.2.10",
                8123,
                True,
                openable=True,
                connection_status="online",
            )
            window.controller._nodes_trusted_specs = lambda: [spec]
            with patch.object(window.controller, "_test_connection") as test_connection:
                window.controller._open_qt_connection_dialog(spec)
                dialog = window.controller.__dict__["_qt_dialogs"]["connection:peer"]
                self.assertIsInstance(dialog, QtConnectionDialog)
                self.assertEqual(dialog.name_input.text(), "Peer")
                self.assertEqual(dialog.host_input.text(), "192.0.2.10")
                self.assertEqual(dialog.port_input.text(), "8123")
                assert dialog.test_button is not None
                dialog.test_button.click()
                test_connection.assert_called_once_with("peer")
            window.close()

    def test_manual_host_removal_confirms_and_invalidates_pending_activation(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )
            spec = TrustedNodeSpec(
                "manual-peer",
                "Manual peer",
                "manual.example",
                None,
                "offline",
                "192.0.2.22",
                None,
                False,
                is_manual=True,
                connection_status="offline",
            )
            window.controller._nodes_manual_specs = lambda: [spec]
            with (
                patch(
                    "maintenance.ui.qt_app_window.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.Yes,
                ) as confirm,
                patch(
                    "maintenance.ui.qt_app_window.ui_node_actions.revoke_trusted_node"
                ) as revoke,
            ):
                window.controller._remove_qt_manual_host("manual-peer")

            confirm.assert_called_once()
            revoke.assert_called_once_with(window.controller, "manual-peer")
            from maintenance.nodes import NodeId

            self.assertEqual(
                window.controller.__dict__["_activation_generations"][
                    NodeId("manual-peer")
                ],
                1,
            )
            window.close()

    def test_trusted_node_details_dialog_is_retained_and_released_on_close(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )
            spec = TrustedNodeSpec(
                "peer",
                "Peer",
                "peer.example",
                None,
                "offline",
                "peer.example",
                443,
                True,
                openable=True,
                identity_fingerprint="identity",
                identity_status="verified",
                permissions=("dashboard_read",),
                role="worker",
                role_editable=True,
                has_active_job=True,
                connection_status="offline",
            )
            window.controller._nodes_trusted_specs = lambda: [spec]
            window.controller._nodes_manual_specs = list
            window.controller._open_qt_node_details("peer")
            dialog = window.controller.__dict__["_qt_dialogs"]["node-details:peer"]
            self.assertIsInstance(dialog, QtNodeDetailsDialog)
            self.assertEqual(dialog.detail_labels["Role"].text(), "worker")
            self.assertIn("identity", dialog.identity_fingerprint_label.text())
            pause_button = dialog.action("pause")
            revoke_button = dialog.action("revoke")
            self.assertIsNotNone(pause_button)
            self.assertIsNotNone(revoke_button)
            assert pause_button is not None
            assert revoke_button is not None
            self.assertTrue(pause_button.isEnabled())
            self.assertTrue(revoke_button.isEnabled())
            self.assertEqual(dialog.detail_labels["Selectable"].text(), "Yes")
            self.assertEqual(dialog.detail_labels["Role editable"].text(), "Yes")
            with patch.object(window.controller, "_test_connection") as test_connection:
                window.controller._nodes_trusted_specs = lambda: [
                    replace(spec, selectable=False)
                ]
                dialog.invoke_action("test")
                test_connection.assert_not_called()
                window.controller._nodes_trusted_specs = lambda: [spec]
                dialog.invoke_action("test")
                test_connection.assert_called_once_with("peer")
            with (
                patch(
                    "maintenance.ui.qt_app_window.ui_node_actions.revoke_node"
                ) as revoke,
                patch(
                    "maintenance.ui.qt_app_window.ui_node_actions.remove_job_node"
                ) as remove_job,
            ):
                window.controller._nodes_trusted_specs = lambda: [
                    replace(spec, role_editable=False)
                ]
                dialog.invoke_action("revoke")
                window.controller._nodes_trusted_specs = lambda: [
                    replace(spec, has_active_job=False)
                ]
                dialog.invoke_action("remove_job")
                revoke.assert_not_called()
                remove_job.assert_not_called()

            window.controller._nodes_trusted_specs = lambda: [spec]
            with (
                patch(
                    "maintenance.ui.qt_app_window.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.No,
                ),
                patch(
                    "maintenance.ui.window_node_actions.revoke_trusted_node"
                ) as revoke_trusted,
            ):
                dialog.invoke_action("revoke")
                revoke_trusted.assert_not_called()

            manual_spec = replace(spec, node_id="manual", is_manual=True)
            window.controller._nodes_trusted_specs = list
            window.controller._nodes_manual_specs = lambda: [manual_spec]
            window.controller._open_qt_node_details("manual")
            manual_dialog = window.controller.__dict__["_qt_dialogs"][
                "node-details:manual"
            ]
            self.assertIsNone(manual_dialog.action("revoke"))
            with patch.object(window.controller, "_peer_connections") as connections:
                window.controller._nodes_manual_specs = lambda: [
                    replace(manual_spec, is_manual=False)
                ]
                manual_dialog.invoke_action("remove_connection")
                connections.assert_not_called()

                window.controller._nodes_manual_specs = lambda: [manual_spec]
                with patch(
                    "maintenance.ui.qt_app_window.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.No,
                ) as confirm:
                    manual_dialog.invoke_action("remove_connection")
                confirm.assert_called_once()
                connections.assert_not_called()
            manual_dialog.close()

            job_dialog = dialog
            window.controller._nodes_trusted_specs = lambda: [spec]
            with (
                patch(
                    "maintenance.ui.qt_app_window.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.No,
                ) as confirm,
                patch(
                    "maintenance.ui.window_node_actions_impl.roles._role_state"
                ) as role_state,
            ):
                job_dialog.invoke_action("remove_job")
            confirm.assert_called_once()
            role_state.assert_not_called()
            dialog.close()
            self.assertNotIn(
                "node-details:peer", window.controller.__dict__["_qt_dialogs"]
            )
            window.close()

    def test_discovered_node_details_show_fingerprints_without_trust_actions(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )
            peer = DiscoveredPeerSpec(
                node_id="untrusted-peer",
                hostname="untrusted.example",
                app_version="1.0",
                compatible=True,
                connectable=True,
                port=8123,
                identity_fingerprint="identity-fingerprint",
                transport_fingerprint="transport-fingerprint",
            )
            window.controller._nodes_peer_specs = lambda: [peer]
            window.controller._open_qt_node_details(peer)
            dialog = window.controller.__dict__.get("_qt_dialogs", {}).get(
                "node-details:untrusted-peer"
            )
            self.assertIsInstance(dialog, QtNodeDetailsDialog)
            assert isinstance(dialog, QtNodeDetailsDialog)
            self.assertEqual(dialog.detail_labels["Pairing"].text(), "discovered")
            assert dialog.identity_fingerprint_label is not None
            self.assertIn(
                "identity-fingerprint", dialog.identity_fingerprint_label.text()
            )
            self.assertIsNone(dialog.action("open"))
            self.assertIsNone(dialog.action("revoke"))
            window.close()

    def test_cluster_actions_follow_legacy_policy_and_use_qt_confirmations(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            spec = ClusterNodeSpec(
                "peer-1",
                "Peer",
                "peer.example",
                None,
                "trusted",
                "online",
                (),
                False,
                True,
                role="worker",
                paused=False,
                role_editable=True,
                has_active_job=True,
                is_cluster_member=True,
            )
            controller = window.controller
            controller._cluster_specs = lambda: [spec]
            controller._refresh_cluster_page()
            buttons = window.cluster_page.action_buttons["peer-1"]
            self.assertEqual(
                set(buttons),
                {"open", "pause", "revoke", "remove_connection", "remove_job"},
            )
            self.assertTrue(all(button.isEnabled() for button in buttons.values()))

            with (
                patch.object(controller, "_open_cluster_node") as open_node,
                patch.object(controller, "_pause_node") as pause_node,
                patch(
                    "maintenance.ui.qt_app_window.ui_node_actions.revoke_node"
                ) as revoke,
                patch(
                    "maintenance.ui.qt_app_window.ui_node_actions.remove_connection_node"
                ) as remove_connection,
                patch(
                    "maintenance.ui.qt_app_window.ui_node_actions.remove_job_node"
                ) as remove_job,
                patch(
                    "maintenance.ui.qt_app_window.QMessageBox.question", return_value=1
                ) as confirm,
            ):
                for key in (
                    "open",
                    "pause",
                    "revoke",
                    "remove_connection",
                    "remove_job",
                ):
                    buttons[key].click()
                open_node.assert_called_once_with("peer-1")
                pause_node.assert_called_once_with("peer-1")
                self.assertEqual(revoke.call_args.args[1], "peer-1")
                self.assertEqual(remove_connection.call_args.args[1], "peer-1")
                self.assertEqual(remove_job.call_args.args[1], "peer-1")
                self.assertEqual(confirm.call_count, 0)
                self.assertIsNotNone(revoke.call_args.kwargs["messagebox_module"])
                self.assertIsNotNone(
                    remove_connection.call_args.kwargs["messagebox_module"]
                )
                self.assertIsNotNone(remove_job.call_args.kwargs["messagebox_module"])
                for action in (revoke, remove_connection, remove_job):
                    action.call_args.kwargs["messagebox_module"].askyesno(
                        "Confirmation", "Confirm?", parent=window
                    )
                self.assertEqual(confirm.call_count, 3)

            local = replace(spec, node_id="local", is_local=True)
            controller._cluster_specs = lambda: [local]
            controller._refresh_cluster_page()
            self.assertEqual(
                set(window.cluster_page.action_buttons["local"]),
                {"open", "share_dashboard"},
            )
            share_button = window.cluster_page.action_buttons["local"][
                "share_dashboard"
            ]
            self.assertEqual(share_button.text(), "Share dashboard")
            with patch.object(controller, "_share_dashboard") as share_dashboard:
                share_button.click()
                dialog = controller.__dict__["_qt_dialogs"]["dashboard-sharing"]
                self.assertIsInstance(dialog, QtSharingDialog)
                self.assertFalse(dialog.active)
                self.assertEqual(dialog.action_button.text(), "Share for 5 minutes")
                dialog.action_button.click()
            share_dashboard.assert_called_once_with()
            window.close()

    def test_dashboard_share_dialog_revalidates_state_before_confirming(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            inactive = ClusterNodeSpec(
                "local",
                "Local",
                "localhost",
                None,
                "local",
                "online",
                (),
                True,
                True,
                share_active=False,
            )
            active = replace(inactive, share_active=True)
            controller = window.controller
            current = [inactive]
            controller._cluster_specs = lambda: current
            controller._refresh_cluster_page()
            with patch.object(controller, "_share_dashboard") as share_dashboard:
                window.cluster_page.action_buttons["local"]["share_dashboard"].click()
                dialog = controller.__dict__["_qt_dialogs"]["dashboard-sharing"]
                current[:] = [active]
                dialog.action_button.click()

                share_dashboard.assert_not_called()
                self.assertTrue(dialog.active)
                self.assertEqual(dialog.state_label.text(), "Active")
                self.assertEqual(dialog.action_button.text(), "Stop sharing")
                self.assertIs(
                    controller.__dict__["_qt_dialogs"]["dashboard-sharing"], dialog
                )
            window.close()

    def test_scan_state_updates_qt_dashboard_and_preferences_controls(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = PreferencesStore(root / "preferences.json")
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=preferences,
                    cluster_store=cluster,
                )

            window.controller._set_busy(True)
            scan_button = window.controller.dashboard_page.scan_button
            cancel_button = window.controller.dashboard_page.cancel_button
            assert scan_button is not None
            assert cancel_button is not None
            self.assertFalse(scan_button.isEnabled())
            self.assertTrue(cancel_button.isEnabled())
            window.controller._show_progress("Scanning storage")
            self.assertIn(
                "Scanning storage", window.controller.dashboard_page.status_label.text()
            )
            self.assertIn(
                "Scanning storage",
                window.controller.preferences_page.status_label.text(),
            )
            window.controller._set_busy(False)
            window.close()

    def test_scan_request_starts_shared_lifecycle_and_sets_qt_busy_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            controller = window.controller
            with patch.object(controller, "_run_daemon") as run:
                controller.handle_analyze()

            self.assertTrue(controller._scan_coordinator_state().active)
            self.assertIsNotNone(controller._analysis_cancel_event)
            cancel_button = window.dashboard_page.cancel_button
            assert cancel_button is not None
            self.assertTrue(cancel_button.isEnabled())
            run.assert_called_once()
            controller._cancel_analysis()
            window.close()

    def test_component_refresh_updates_the_retained_qt_dashboard_card(self) -> None:
        from maintenance.ui.window_components import apply_component

        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            summary = make_summary("cpu", "Processor", value="27%")
            apply_component(window.controller, "cpu", summary)

            self.assertEqual(
                window.dashboard_page.cards["cpu"].value_label.text(), "27%"
            )
            window.close()

    def test_cancelled_scan_notice_is_visible_on_both_scan_surfaces(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer", return_value="timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            notice = "Scan cancelled. Previous results are unchanged."
            window.controller._show_scan_cancelled_notice(notice)

            self.assertEqual(window.dashboard_page.status_label.text(), notice)
            self.assertEqual(window.preferences_page.status_label.text(), notice)
            window.close()

    def test_informational_resource_opens_a_qt_owned_details_dialog(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            window.controller.snapshot = make_snapshot(
                make_summary("battery", "Battery", details=("Charge: 80%",))
            )
            window.controller.open_resource("battery")

            dialog = window.controller.__dict__["_qt_dialogs"]["resource:battery"]
            self.assertIsInstance(dialog, QtInfoDialog)
            self.assertTrue(dialog.isVisible())
            dialog.close()
            window.close()

    def test_process_resource_routes_to_the_qt_process_review_dialog(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
                patch(
                    "maintenance.ui.qt_app_window.QtProcessDialog", create=True
                ) as dialog_factory,
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )
                window.controller.snapshot = make_snapshot(
                    make_summary("cpu", "CPU", actionable=True)
                )
                window.controller.open_resource("cpu")

            dialog_factory.assert_called_once()
            self.assertTrue(dialog_factory.call_args.kwargs["read_only"] is False)
            dialog_factory.return_value.open.assert_called_once_with()
            window.close()

    def test_storage_resource_routes_to_the_qt_storage_review_dialog(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
                patch(
                    "maintenance.ui.qt_app_window.QtStorageDialog", create=True
                ) as dialog_factory,
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )
                window.controller.snapshot = make_snapshot(
                    make_summary("storage", "Storage", actionable=True)
                )
                window.controller.open_resource("storage")

            dialog_factory.assert_called_once()
            self.assertFalse(dialog_factory.call_args.kwargs["read_only"])
            self.assertEqual(dialog_factory.call_args.kwargs["scan_root_label"], None)
            dialog_factory.return_value.open.assert_called_once_with()
            window.close()

    def test_pairing_requires_qt_fingerprint_review_before_transaction(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            controller = window.controller
            peer = DiscoveredPeerSpec(
                "peer-1",
                "peer.example",
                "1.0",
                True,
                True,
                443,
                "identity-fingerprint",
                "transport-fingerprint",
            )
            controller._nodes_peer_specs = lambda: [peer]
            with patch(
                "maintenance.ui.window_node_actions.pair_discovered_node_async"
            ) as pair:
                controller._pair_discovered_node("peer-1")
                dialog = controller.__dict__["_qt_dialogs"]["pairing:peer-1"]
                self.assertIsInstance(dialog, QtPairingDialog)
                self.assertIn(
                    "identity-fingerprint", dialog.identity_fingerprint_label.text()
                )
                self.assertIn(
                    "transport-fingerprint", dialog.transport_fingerprint_label.text()
                )
                pair.assert_not_called()
                dialog.confirm()
                pair.assert_called_once()
                self.assertIs(pair.call_args.kwargs["dialog"], dialog)
            window.close()

    def test_successful_pairing_completion_allows_a_fresh_pairing_dialog(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            controller = window.controller
            peer = DiscoveredPeerSpec(
                "peer-1",
                "peer.example",
                "1.0",
                True,
                True,
                443,
                "identity-fingerprint",
                "transport-fingerprint",
            )
            controller._nodes_peer_specs = lambda: [peer]

            def complete_transaction(*args, **kwargs):
                kwargs["dialog"].complete()

            with patch(
                "maintenance.ui.window_node_actions.pair_discovered_node_async",
                side_effect=complete_transaction,
            ):
                controller._pair_discovered_node("peer-1")
                first_dialog = controller.__dict__["_qt_dialogs"]["pairing:peer-1"]
                first_dialog.confirm()
                self.assertFalse(first_dialog.isVisible())

                controller._pair_discovered_node("peer-1")
                second_dialog = controller.__dict__["_qt_dialogs"]["pairing:peer-1"]

            self.assertIsNot(second_dialog, first_dialog)
            self.assertIsInstance(second_dialog, QtPairingDialog)
            self.assertTrue(second_dialog.isVisible())
            window.close()

    def test_pairing_confirmation_rejects_changed_fingerprints(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cluster = ClusterStore(root / "cluster.json")
            cluster.save(replace(ClusterState.create_local(), discovery_enabled=False))
            with (
                patch.object(QtAppController, "_start_peer_listener"),
                patch.object(QtAppController, "_start_discovery"),
                patch.object(QtAppController, "_schedule_timer"),
            ):
                window = QtAppWindow(
                    preferences_store=PreferencesStore(root / "preferences.json"),
                    cluster_store=cluster,
                )

            controller = window.controller
            peer = DiscoveredPeerSpec(
                "peer-1",
                "peer.example",
                "1.0",
                True,
                True,
                443,
                "identity-fingerprint",
                "transport-fingerprint",
            )
            controller._nodes_peer_specs = lambda: [peer]
            with patch(
                "maintenance.ui.window_node_actions.pair_discovered_node_async"
            ) as pair:
                controller._pair_discovered_node("peer-1")
                dialog = controller.__dict__["_qt_dialogs"]["pairing:peer-1"]
                controller._nodes_peer_specs = lambda: [
                    replace(peer, identity_fingerprint="changed-fingerprint")
                ]

                dialog.confirm()

                pair.assert_not_called()
                self.assertEqual(
                    dialog.status_label.text(),
                    "Peer fingerprints changed; review the node again",
                )
                self.assertTrue(dialog.isVisible())
            window.close()


if __name__ == "__main__":
    unittest.main()
