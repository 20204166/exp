"""Tests for the isolated Qt Nodes & Connections page."""

import unittest
from unittest.mock import Mock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox

from maintenance.nodes import local_node_descriptor
from maintenance.ui.page_specs import (
    DiscoveredPeerSpec,
    LocalClusterSpec,
    TrustedNodeSpec,
)
from maintenance.ui.qt_nodes_connections import (
    QtNodesConnectionsCallbacks,
    QtNodesConnectionsPage,
)
from tests.support.qt import get_qapplication


class QtNodesConnectionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def test_projects_distinct_axes_and_uses_coordinator_epoch_projection(self) -> None:
        page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=Mock(),
                on_discovery_toggle=Mock(),
                on_pair=Mock(),
                on_reject=Mock(),
                on_select_node=Mock(),
                on_open_node=Mock(),
                on_test_connection=Mock(),
                on_refresh=Mock(),
            ),
            discovery_enabled=True,
            discovered=[
                DiscoveredPeerSpec("candidate", "Untrusted", "1", True, True, 5000)
            ],
            trusted=[
                TrustedNodeSpec(
                    "offline",
                    "Trusted offline",
                    "offline",
                    None,
                    "offline",
                    "host",
                    1,
                    False,
                    connection_status="offline",
                ),
                TrustedNodeSpec(
                    "online",
                    "Connected, not member",
                    "online",
                    None,
                    "online",
                    "host",
                    2,
                    True,
                    connection_status="online",
                    is_cluster_member=False,
                ),
                TrustedNodeSpec(
                    "worker",
                    "Worker",
                    "worker",
                    None,
                    "online",
                    "host",
                    3,
                    True,
                    connection_status="online",
                    is_cluster_member=True,
                    role="worker",
                ),
            ],
            manual=[],
            selected_node=local_node_descriptor(),
            local_cluster=LocalClusterSpec(
                True, "worker", "coord-id", "Coordinator", "online", False, 0, False
            ),
        )
        self.assertIn("Untrusted", page.discovered_rows["candidate"].text())
        self.assertIn("Trusted", page.trusted_rows["offline"].text())
        self.assertIn("Offline", page.trusted_rows["offline"].text())
        self.assertIn("Not in cluster", page.trusted_rows["online"].text())
        self.assertIn("Cluster member", page.trusted_rows["worker"].text())
        cluster_summary = page.cluster_summary
        selected_node_label = page.selected_node_label
        assert cluster_summary is not None
        assert selected_node_label is not None
        self.assertIn("Coordinator", cluster_summary.text())
        self.assertNotIn("coord-id", cluster_summary.text())
        self.assertIn("This System · Local", selected_node_label.text())
        self.assertLess(
            page.section_order.index("Discovered peers"),
            page.section_order.index("Trusted nodes"),
        )
        page.close()

    def test_explicit_actions_selection_and_refresh_dispatch(self) -> None:
        on_discovery_toggle = Mock()
        on_pair = Mock()
        on_select_node = Mock()
        on_open_node = Mock()
        on_test_connection = Mock()
        on_refresh = Mock()
        callbacks = QtNodesConnectionsCallbacks(
            on_back=Mock(),
            on_discovery_toggle=on_discovery_toggle,
            on_pair=on_pair,
            on_reject=Mock(),
            on_select_node=on_select_node,
            on_open_node=on_open_node,
            on_test_connection=on_test_connection,
            on_refresh=on_refresh,
        )
        page = QtNodesConnectionsPage(
            callbacks=callbacks,
            discovery_enabled=False,
            discovered=[DiscoveredPeerSpec("d", "Found", "1", True, True, 5)],
            trusted=[
                TrustedNodeSpec(
                    "t",
                    "Trusted",
                    "host",
                    None,
                    "online",
                    "host",
                    5,
                    True,
                    openable=True,
                )
            ],
            manual=[],
        )
        page.pair_buttons["d"].click()
        page.select_buttons["t"].click()
        page.open_buttons["t"].click()
        page.test_buttons["t"].click()
        page.refresh_button.click()
        page.discovery_toggle.click()
        on_pair.assert_called_once_with("d")
        on_select_node.assert_called_once_with("t")
        on_open_node.assert_called_once_with("t")
        on_test_connection.assert_called_once_with("t")
        on_refresh.assert_called_once_with()
        on_discovery_toggle.assert_called_once_with(True)
        page.close()

    def test_refresh_replaces_stale_peer_and_trusted_node_projections(self) -> None:
        page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=Mock(),
                on_discovery_toggle=Mock(),
                on_pair=Mock(),
                on_reject=Mock(),
                on_select_node=Mock(),
                on_open_node=Mock(),
                on_test_connection=Mock(),
                on_refresh=Mock(),
            ),
            discovery_enabled=True,
            discovered=[DiscoveredPeerSpec("old", "Old", "1", True, True, 5)],
            trusted=[],
            manual=[],
        )
        page.refresh(
            discovery_enabled=False,
            discovered=[DiscoveredPeerSpec("new", "New", "2", True, False, 5)],
            trusted=[
                TrustedNodeSpec(
                    "trusted-new",
                    "Trusted New",
                    "host",
                    None,
                    "online",
                    "host",
                    5,
                    True,
                )
            ],
            manual=[],
            selected_node=local_node_descriptor(),
            local_cluster=None,
        )

        self.assertEqual(set(page.discovered_rows), {"new"})
        self.assertEqual(set(page.trusted_rows), {"trusted-new"})
        self.assertFalse(page.discovery_toggle.isChecked())
        self.assertIn("This System · Local", page.selected_node_label.text())
        page.close()

    def test_accessibility_scroll_long_names_and_widths(self) -> None:
        long_name = "A very long node display name " * 10
        page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=Mock(),
                on_discovery_toggle=Mock(),
                on_pair=Mock(),
                on_reject=Mock(),
                on_select_node=Mock(),
                on_open_node=Mock(),
                on_test_connection=Mock(),
                on_refresh=Mock(),
            ),
            discovery_enabled=True,
            discovered=[],
            trusted=[
                TrustedNodeSpec(
                    "long", long_name, "host", None, "offline", "host", None, False
                )
            ],
            manual=[],
        )
        self.assertEqual(page.accessibleName(), "Nodes and connections")
        self.assertTrue(page.refresh_button.accessibleName())
        self.assertTrue(page.refresh_button.focusPolicy() & Qt.FocusPolicy.TabFocus)
        self.assertTrue(page.scroll_area.widgetResizable())
        self.assertIn(long_name, page.trusted_rows["long"].text())
        for width in (900, 1280, 1600):
            page.resize(width, 360)
            page.show()
            self.app.processEvents()
            self.assertGreaterEqual(page.width(), width - 10)
        page.close()

    def test_trusted_rows_offer_details_and_dispatch_node_spec(self) -> None:
        on_details = Mock()
        trusted_spec = TrustedNodeSpec(
            "trusted", "Trusted", "host", None, "online", "host", 5, True
        )
        callbacks = QtNodesConnectionsCallbacks(
            on_back=Mock(),
            on_discovery_toggle=Mock(),
            on_pair=Mock(),
            on_reject=Mock(),
            on_select_node=Mock(),
            on_open_node=Mock(),
            on_test_connection=Mock(),
            on_refresh=Mock(),
            on_details=on_details,
        )
        page = QtNodesConnectionsPage(
            callbacks=callbacks,
            discovery_enabled=False,
            discovered=[],
            trusted=[trusted_spec],
            manual=[],
        )
        page.details_buttons["trusted"].click()
        on_details.assert_called_once_with(trusted_spec)
        page.close()

    def test_manual_host_rows_offer_details_and_dispatch_node_spec(self) -> None:
        on_details = Mock()
        manual_spec = TrustedNodeSpec(
            "manual",
            "Manual",
            "manual.example",
            None,
            "offline",
            "manual.example",
            443,
            False,
            is_manual=True,
        )
        callbacks = QtNodesConnectionsCallbacks(
            on_back=Mock(),
            on_discovery_toggle=Mock(),
            on_pair=Mock(),
            on_reject=Mock(),
            on_select_node=Mock(),
            on_open_node=Mock(),
            on_test_connection=Mock(),
            on_refresh=Mock(),
            on_details=on_details,
        )
        page = QtNodesConnectionsPage(
            callbacks=callbacks,
            discovery_enabled=False,
            discovered=[],
            trusted=[],
            manual=[manual_spec],
        )
        page.details_buttons["manual"].click()
        on_details.assert_called_once_with(manual_spec)
        page.close()

    def test_trusted_and_manual_rows_expose_injected_behavior_callbacks(self) -> None:
        from maintenance.ui.page_specs import TrustedNodeSpec

        rename, color, permissions, roles = Mock(), Mock(), Mock(), Mock()
        open_connection, remove_manual = Mock(), Mock()
        trusted_spec = TrustedNodeSpec(
            "trusted",
            "Trusted",
            "host",
            None,
            "online",
            "host",
            5,
            True,
            role="worker",
            roles=("worker",),
            role_editable=True,
        )
        callbacks = QtNodesConnectionsCallbacks(
            on_back=Mock(),
            on_discovery_toggle=Mock(),
            on_pair=Mock(),
            on_reject=Mock(),
            on_select_node=Mock(),
            on_open_node=Mock(),
            on_test_connection=Mock(),
            on_refresh=Mock(),
            on_rename=rename,
            on_color=color,
            on_permissions=permissions,
            on_role_change=roles,
            on_open_connection=open_connection,
            on_remove_manual=remove_manual,
        )
        page = QtNodesConnectionsPage(
            callbacks=callbacks,
            discovery_enabled=False,
            discovered=[],
            trusted=[trusted_spec],
            manual=[
                TrustedNodeSpec(
                    "manual",
                    "Manual",
                    "manual.host",
                    None,
                    "offline",
                    "manual.host",
                    443,
                    False,
                    is_manual=True,
                )
            ],
        )
        page.rename_buttons["trusted"].click()
        page.color_controls["trusted"].setCurrentIndex(1)
        page.permission_controls["trusted"]["dashboard_read"].click()
        page.role_controls["trusted"]["subcoordinator"].click()
        page.test_buttons["trusted"].click()
        page.remove_manual_buttons["manual"].click()
        rename.assert_called_once_with("trusted")
        color.assert_called_once_with(
            "trusted", page.color_controls["trusted"].currentText()
        )
        permissions.assert_called_once_with("trusted", frozenset({"dashboard_read"}))
        roles.assert_called_once_with(
            "trusted", frozenset({"worker", "subcoordinator"})
        )
        open_connection.assert_called_once_with(trusted_spec)
        remove_manual.assert_called_once_with("manual")
        self.assertIsInstance(page.color_controls["trusted"], QComboBox)
        self.assertIsInstance(
            page.permission_controls["trusted"]["dashboard_read"], QCheckBox
        )
        self.assertTrue(page.rename_buttons["trusted"].accessibleName())
        page.close()

    def test_discovery_pairing_help_and_dashboard_share_affordances_dispatch(
        self,
    ) -> None:
        start_discovery, learn_pairing, share = Mock(), Mock(), Mock()
        page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=Mock(),
                on_discovery_toggle=Mock(),
                on_pair=Mock(),
                on_reject=Mock(),
                on_select_node=Mock(),
                on_open_node=Mock(),
                on_test_connection=Mock(),
                on_refresh=Mock(),
                on_start_discovery=start_discovery,
                on_learn_pairing=learn_pairing,
                on_share_dashboard=share,
            ),
            discovery_enabled=False,
            discovered=[],
            trusted=[],
            manual=[],
            local_cluster=LocalClusterSpec(
                True, "worker", "coord", "Coordinator", "online", False, 0, True
            ),
        )
        start_button = page.start_discovery_button
        help_button = page.learn_pairing_button
        share_button = page.share_dashboard_button
        assert start_button is not None
        assert help_button is not None
        assert share_button is not None
        start_button.click()
        help_button.click()
        share_button.click()
        start_discovery.assert_called_once_with()
        learn_pairing.assert_called_once_with()
        share.assert_called_once_with()
        for button in (
            start_button,
            help_button,
            share_button,
        ):
            self.assertTrue(button.accessibleName())
            self.assertTrue(button.focusPolicy() & Qt.FocusPolicy.TabFocus)
        page.close()

    def test_legacy_trusted_actions_preserve_revoke_and_connection_dispatch(
        self,
    ) -> None:
        from maintenance.ui.page_specs import TrustedNodeSpec

        revoke, open_connection, test_connection = Mock(), Mock(), Mock()
        spec = TrustedNodeSpec(
            "trusted", "Trusted", "host", None, "online", "host", 5, True
        )
        page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=Mock(),
                on_discovery_toggle=Mock(),
                on_pair=Mock(),
                on_reject=Mock(),
                on_select_node=Mock(),
                on_open_node=Mock(),
                on_test_connection=test_connection,
                on_refresh=Mock(),
                on_revoke=revoke,
                on_open_connection=open_connection,
            ),
            discovery_enabled=False,
            discovered=[],
            trusted=[spec],
            manual=[],
        )
        page.revoke_buttons["trusted"].click()
        page.test_buttons["trusted"].click()
        revoke.assert_called_once_with("trusted")
        open_connection.assert_called_once_with(spec)
        test_connection.assert_not_called()
        page.close()

    def test_test_action_falls_back_to_node_id_without_open_connection_callback(
        self,
    ) -> None:
        test_connection = Mock()
        page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=Mock(),
                on_discovery_toggle=Mock(),
                on_pair=Mock(),
                on_reject=Mock(),
                on_select_node=Mock(),
                on_open_node=Mock(),
                on_test_connection=test_connection,
                on_refresh=Mock(),
            ),
            discovery_enabled=False,
            discovered=[],
            trusted=[
                TrustedNodeSpec(
                    "fallback", "Fallback", "host", None, "online", "host", 5, True
                )
            ],
            manual=[],
        )
        page.test_buttons["fallback"].click()
        test_connection.assert_called_once_with("fallback")
        page.close()

    def test_pause_resume_and_removal_actions_follow_legacy_conditions(self) -> None:
        on_pause, on_resume = Mock(), Mock()
        on_remove_connection, on_remove_job = Mock(), Mock()
        editable = TrustedNodeSpec(
            "editable",
            "Editable",
            "host",
            None,
            "online",
            "host",
            5,
            True,
            role_editable=True,
            has_active_job=True,
        )
        paused = TrustedNodeSpec(
            "paused",
            "Paused",
            "host",
            None,
            "online",
            "host",
            6,
            True,
            role_editable=True,
            paused=True,
        )
        ineligible = TrustedNodeSpec(
            "ineligible",
            "Ineligible",
            "host",
            None,
            "online",
            "host",
            7,
            True,
            role_editable=False,
            has_active_job=False,
        )
        manual = TrustedNodeSpec(
            "manual",
            "Manual",
            "host",
            None,
            "online",
            "host",
            8,
            True,
            role_editable=True,
            has_active_job=True,
            is_manual=True,
        )
        page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=Mock(),
                on_discovery_toggle=Mock(),
                on_pair=Mock(),
                on_reject=Mock(),
                on_select_node=Mock(),
                on_open_node=Mock(),
                on_test_connection=Mock(),
                on_refresh=Mock(),
                on_pause=on_pause,
                on_resume=on_resume,
                on_remove_connection=on_remove_connection,
                on_remove_job=on_remove_job,
            ),
            discovery_enabled=False,
            discovered=[],
            trusted=[editable, paused, ineligible],
            manual=[manual],
        )
        self.assertEqual(page.pause_buttons["editable"].text(), "Pause")
        self.assertEqual(page.pause_buttons["paused"].text(), "Re-enable")
        self.assertNotIn("ineligible", page.pause_buttons)
        self.assertNotIn("manual", page.pause_buttons)
        self.assertIn("editable", page.remove_connection_buttons)
        self.assertIn("paused", page.remove_connection_buttons)
        self.assertNotIn("manual", page.remove_connection_buttons)
        self.assertIn("editable", page.remove_job_buttons)
        self.assertNotIn("paused", page.remove_job_buttons)
        self.assertNotIn("ineligible", page.remove_job_buttons)
        self.assertNotIn("manual", page.remove_job_buttons)
        page.pause_buttons["editable"].click()
        page.pause_buttons["paused"].click()
        page.remove_connection_buttons["editable"].click()
        page.remove_job_buttons["editable"].click()
        on_pause.assert_called_once_with("editable")
        on_resume.assert_called_once_with("paused")
        on_remove_connection.assert_called_once_with("editable")
        on_remove_job.assert_called_once_with("editable")
        page.close()

    def test_discovered_existing_pair_relationship_hides_actions_and_shows_status(
        self,
    ) -> None:
        page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=Mock(),
                on_discovery_toggle=Mock(),
                on_pair=Mock(),
                on_reject=Mock(),
                on_select_node=Mock(),
                on_open_node=Mock(),
                on_test_connection=Mock(),
                on_refresh=Mock(),
            ),
            discovery_enabled=False,
            discovered=[
                DiscoveredPeerSpec(
                    "paired",
                    "Already paired",
                    "1",
                    True,
                    True,
                    5000,
                    has_pair_relationship=True,
                )
            ],
            trusted=[],
            manual=[],
        )
        self.assertNotIn("paired", page.pair_buttons)
        self.assertNotIn("paired", page.reject_buttons)
        self.assertEqual(page.paired_status_labels["paired"].text(), "Paired")
        page.close()

    def test_discovered_rows_show_details_only_when_callback_is_supplied(self) -> None:
        on_details = Mock()
        discovered = [
            DiscoveredPeerSpec("ordinary", "Ordinary", "1", True, True, 5000),
            DiscoveredPeerSpec(
                "paired",
                "Paired",
                "1",
                True,
                True,
                5001,
                has_pair_relationship=True,
            ),
        ]
        callbacks = QtNodesConnectionsCallbacks(
            on_back=Mock(),
            on_discovery_toggle=Mock(),
            on_pair=Mock(),
            on_reject=Mock(),
            on_select_node=Mock(),
            on_open_node=Mock(),
            on_test_connection=Mock(),
            on_refresh=Mock(),
            on_details=on_details,
        )
        page = QtNodesConnectionsPage(
            callbacks=callbacks,
            discovery_enabled=False,
            discovered=discovered,
            trusted=[],
            manual=[],
        )
        self.assertEqual(set(page.discovered_details_buttons), {"ordinary", "paired"})
        page.discovered_details_buttons["ordinary"].click()
        page.discovered_details_buttons["paired"].click()
        on_details.assert_any_call(discovered[0])
        on_details.assert_any_call(discovered[1])
        self.assertNotIn("paired", page.pair_buttons)
        self.assertNotIn("paired", page.reject_buttons)
        page.close()

        no_details_page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=Mock(),
                on_discovery_toggle=Mock(),
                on_pair=Mock(),
                on_reject=Mock(),
                on_select_node=Mock(),
                on_open_node=Mock(),
                on_test_connection=Mock(),
                on_refresh=Mock(),
            ),
            discovery_enabled=False,
            discovered=discovered,
            trusted=[],
            manual=[],
        )
        self.assertEqual(no_details_page.discovered_details_buttons, {})
        no_details_page.close()

    def test_details_control_is_omitted_without_explicit_callback(self) -> None:
        from maintenance.ui.page_specs import TrustedNodeSpec

        page = QtNodesConnectionsPage(
            callbacks=QtNodesConnectionsCallbacks(
                on_back=Mock(),
                on_discovery_toggle=Mock(),
                on_pair=Mock(),
                on_reject=Mock(),
                on_select_node=Mock(),
                on_open_node=Mock(),
                on_test_connection=Mock(),
                on_refresh=Mock(),
            ),
            discovery_enabled=False,
            discovered=[],
            trusted=[
                TrustedNodeSpec(
                    "trusted", "Trusted", "host", None, "online", "host", 5, True
                )
            ],
            manual=[
                TrustedNodeSpec(
                    "manual",
                    "Manual",
                    "manual",
                    None,
                    "offline",
                    "manual",
                    5,
                    False,
                    is_manual=True,
                )
            ],
        )
        self.assertEqual(page.details_buttons, {})
        page.close()


if __name__ == "__main__":
    unittest.main()
