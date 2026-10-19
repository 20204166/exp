"""Qt presentation tests for the standalone cluster page."""

import unittest
from unittest.mock import Mock

from PySide6.QtCore import Qt

from maintenance.ui.qt_cluster import (
    QtClusterActionSpec,
    QtClusterCallbacks,
    QtClusterNodeSpec,
    QtClusterPage,
    QtClusterSummary,
)
from tests.support.qt import get_qapplication


def _node(
    node_id: str,
    *,
    trust: str = "Trusted",
    connection: str = "Online",
    member: bool = True,
    roles: tuple[str, ...] = ("Worker",),
    coordinator_id: str | None = None,
    actions: tuple[QtClusterActionSpec, ...] = (),
    display_name: str | None = None,
) -> QtClusterNodeSpec:
    return QtClusterNodeSpec(
        node_id=node_id,
        display_name=display_name or node_id,
        hostname=f"{node_id}.host",
        trust_state=trust,
        connection_state=connection,
        cluster_member=member,
        roles=roles,
        coordinator_id=coordinator_id,
        actions=actions,
    )


def _page(
    nodes: tuple[QtClusterNodeSpec, ...],
    *,
    summary: QtClusterSummary | None = None,
    actions: dict[str, Mock] | None = None,
):
    callbacks = QtClusterCallbacks(on_back=Mock(), on_action=actions or {})
    page = QtClusterPage(
        summary or QtClusterSummary("cluster-1", "coord-1", 7),
        nodes,
        callbacks=callbacks,
    )
    page.resize(900, 600)
    page.show()
    get_qapplication().processEvents()
    return page, callbacks


class QtClusterPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def test_trust_connection_and_cluster_membership_are_separate_axes(self) -> None:
        page, _ = _page(
            (
                _node(
                    "discovered", trust="Untrusted", connection="Offline", member=False
                ),
                _node("trusted-offline", connection="Offline", member=False),
                _node("online-not-joined", member=False),
            )
        )
        try:
            labels = page.node_labels
            self.assertIn("Untrusted", labels["discovered"].text())
            self.assertIn("Offline", labels["discovered"].text())
            self.assertIn("Not in cluster", labels["discovered"].text())
            self.assertIn("Trusted", labels["trusted-offline"].text())
            self.assertIn("Offline", labels["trusted-offline"].text())
            self.assertIn("Online", labels["online-not-joined"].text())
            self.assertIn("Not in cluster", labels["online-not-joined"].text())
        finally:
            page.close()

    def test_joined_worker_shows_epoch_coordinator_identity(self) -> None:
        page, _ = _page((_node("worker-1", coordinator_id="epoch-coordinator"),))
        try:
            text = page.node_labels["worker-1"].text()
            self.assertIn("Worker", text)
            self.assertIn("Cluster member", text)
            self.assertIn("Coordinator: epoch-coordinator", text)
        finally:
            page.close()

    def test_coordinator_assignment_and_role_display_are_visible(self) -> None:
        page, _ = _page(
            (_node("coord", roles=("Coordinator", "Worker")),),
            summary=QtClusterSummary("cluster-1", "coord", 7),
        )
        try:
            self.assertIn("Coordinator", page.node_labels["coord"].text())
            self.assertIn("Worker", page.node_labels["coord"].text())
            self.assertIn("Coordinator: coord", page.coordinator_label.text())
            self.assertIn("Epoch 7", page.coordinator_label.text())
        finally:
            page.close()

    def test_action_policy_visibility_enabled_dispatch_and_confirmation_are_injected(
        self,
    ) -> None:
        confirmation = "Pause this worker?"
        dispatch = Mock()
        hidden = QtClusterActionSpec("hidden", "Hidden", visible=False, enabled=True)
        disabled = QtClusterActionSpec("revoke", "Revoke", visible=True, enabled=False)
        pause = QtClusterActionSpec(
            "pause",
            "Pause",
            visible=True,
            enabled=True,
            confirmation_intent=confirmation,
        )
        page, _callbacks = _page(
            (_node("worker", actions=(hidden, disabled, pause)),),
            actions={"pause": dispatch},
        )
        try:
            self.assertNotIn("hidden", page.action_buttons["worker"])
            self.assertFalse(page.action_buttons["worker"]["revoke"].isEnabled())
            self.assertTrue(page.action_buttons["worker"]["pause"].isEnabled())
            page.action_buttons["worker"]["pause"].click()
            dispatch.assert_called_once_with("worker", confirmation)
        finally:
            page.close()

    def test_accessible_names_and_focusable_actions(self) -> None:
        page, _ = _page(
            (
                _node(
                    "node-1", actions=(QtClusterActionSpec("open", "Open", True, True),)
                ),
            )
        )
        try:
            self.assertEqual(page.accessibleName(), "Cluster overview")
            button = page.action_buttons["node-1"]["open"]
            self.assertEqual(button.accessibleName(), "Open node-1")
            self.assertEqual(button.focusPolicy(), Qt.FocusPolicy.StrongFocus)
            page.back_button.setFocus()
            self.assertTrue(page.back_button.hasFocus())
        finally:
            page.close()

    def test_refresh_replaces_nodes_and_cluster_epoch_projection(self) -> None:
        page, _ = _page((_node("old-node"),))
        try:
            page.refresh(
                QtClusterSummary("cluster-2", "coordinator-2", 8),
                (_node("new-node", coordinator_id="coordinator-2"),),
            )

            self.assertEqual(set(page.node_labels), {"new-node"})
            self.assertEqual(page.cluster_label.text(), "Cluster: cluster-2")
            self.assertIn("coordinator-2", page.coordinator_label.text())
            self.assertIn("Epoch 8", page.coordinator_label.text())
        finally:
            page.close()

    def test_refresh_rejects_duplicate_node_ids_without_mutating_current_projection(
        self,
    ) -> None:
        page, _ = _page((_node("existing"),))
        try:
            with self.assertRaisesRegex(ValueError, "Duplicate cluster node id"):
                page.refresh(
                    QtClusterSummary("cluster-2", "coordinator-2", 8),
                    (_node("duplicate"), _node("duplicate")),
                )

            self.assertEqual(set(page.node_labels), {"existing"})
            self.assertEqual(page.cluster_label.text(), "Cluster: cluster-1")
        finally:
            page.close()

    def test_layout_handles_required_widths_long_labels_and_vertical_scrolling(
        self,
    ) -> None:
        long_name = "Very long node label " * 12
        page, _ = _page(
            tuple(_node(f"node-{i}", display_name=long_name) for i in range(8))
        )
        try:
            for width in (900, 1280, 1600):
                page.resize(width, 320)
                self.app.processEvents()
                self.assertGreaterEqual(page.scroll_area.viewport().width(), 0)
                self.assertTrue(page.scroll_area.verticalScrollBar().maximum() > 0)
            self.assertIn(long_name, page.node_names["node-0"].text())
            self.assertTrue(page.node_names["node-0"].wordWrap())
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()
