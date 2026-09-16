"""Window resource node test cases."""

import unittest
from unittest.mock import Mock, patch

from maintenance.nodes import LOCAL_NODE_ID, NodeCapability, NodeId
from tests.test_window_nodes import _make_window, _summary, _trusted_context


class WindowOpenResourceNodeTests(unittest.TestCase):
    def test_local_dialog_is_not_read_only(self) -> None:
        window = _make_window()
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=_summary("cpu"))
        window._feature_catalog.get = Mock(return_value=Mock(action_kind="process"))
        with patch("window.ProcessDialog") as dialog:
            window.open_resource("cpu")
        self.assertEqual(dialog.call_args.kwargs["read_only"], False)
        self.assertEqual(dialog.call_args.kwargs["node_id"], NodeId(LOCAL_NODE_ID))
        self.assertIs(dialog.call_args.kwargs["provider"], window.analyzer)

    def test_remote_without_termination_capability_is_read_only(self) -> None:
        window = _make_window(
            _trusted_context(
                "dev",
                "Dev Node",
                cpu_value="x",
                host_label="dev",
                capabilities=frozenset({NodeCapability.PROCESS_REVIEW}),
            )
        )
        window._switch_selected_node(NodeId("dev"))
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=_summary("cpu"))
        window._feature_catalog.get = Mock(return_value=Mock(action_kind="process"))
        with patch("window.ProcessDialog") as dialog:
            window.open_resource("cpu")
        self.assertEqual(dialog.call_args.kwargs["read_only"], True)
        self.assertEqual(dialog.call_args.kwargs["node_title"], "Dev Node")
        self.assertIs(dialog.call_args.kwargs["provider"], window.analyzer)

    def test_remote_cleanup_metadata_does_not_enable_storage_mutation(self) -> None:
        window = _make_window(
            _trusted_context(
                "dev",
                "Dev Node",
                cpu_value="x",
                host_label="dev",
                capabilities=frozenset(
                    {NodeCapability.STORAGE_REVIEW, NodeCapability.CLEANUP}
                ),
            )
        )
        window._switch_selected_node(NodeId("dev"))
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=_summary("storage"))
        window._feature_catalog.get = Mock(return_value=Mock(action_kind="storage"))
        with patch("window.StorageDialog") as dialog:
            window.open_resource("storage")
        self.assertEqual(dialog.call_args.kwargs["read_only"], True)

    def test_remote_storage_dialog_never_gets_a_scan_root(self) -> None:
        window = _make_window(
            _trusted_context(
                "dev",
                "Dev Node",
                cpu_value="x",
                host_label="dev",
                capabilities=frozenset({NodeCapability.STORAGE_REVIEW}),
            )
        )
        window._switch_selected_node(NodeId("dev"))
        window._preferences.full_system_scan_enabled = True
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=_summary("storage"))
        window._feature_catalog.get = Mock(return_value=Mock(action_kind="storage"))
        with patch("window.StorageDialog") as dialog:
            window.open_resource("storage")
        self.assertIsNone(dialog.call_args.kwargs["scan_root"])

    def test_dialog_change_callback_does_not_rescan_a_newly_selected_node(self) -> None:
        window = _make_window(
            _trusted_context("dev", "Dev Node", cpu_value="x", host_label="dev")
        )
        window.snapshot = Mock()
        window.snapshot.get = Mock(return_value=_summary("cpu"))
        window._feature_catalog.get = Mock(return_value=Mock(action_kind="process"))
        window._rescan_after_change = Mock()
        with patch("window.ProcessDialog") as dialog:
            window.open_resource("cpu")
        on_changed = dialog.call_args.kwargs["on_changed"]

        window._switch_selected_node(NodeId("dev"))
        on_changed()

        window._rescan_after_change.assert_not_called()
