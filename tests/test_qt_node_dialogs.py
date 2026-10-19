"""Focused behavior tests for isolated Qt node dialogs."""

from __future__ import annotations

import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QPushButton

from maintenance.ui.node_dialog_contracts import (
    ConnectionDialogCallbacks,
    NodeDetailsDialogCallbacks,
    NodeDetailsDialogSpec,
    PairingDialogSpec,
    SharingDialogCallbacks,
)
from maintenance.ui.qt_node_dialogs import (
    QtConnectionDialog,
    QtNodeDetailsDialog,
    QtPairingDialog,
    QtSharingDialog,
)
from tests.support.qt import get_qapplication


class QtNodeDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = get_qapplication()

    def test_connection_validation_keeps_dialog_open_and_preserves_bounds(self) -> None:
        added: list[tuple[str, str, int | None]] = []
        dialog = QtConnectionDialog(
            None,
            callbacks=ConnectionDialogCallbacks(
                on_add=lambda name, host, port: added.append((name, host, port))
            ),
        )
        dialog.name_input.setText(" Peer ")
        dialog.host_input.setText("peer.local")
        dialog.port_input.setText("65536")
        dialog.show()
        dialog.submit()
        self.assertEqual(added, [])
        self.assertTrue(dialog.isVisible())
        self.assertIn("65535", dialog.status_label.text())
        dialog.port_input.setText("0")
        dialog.submit()
        self.assertEqual(added, [("Peer", "peer.local", 0)])
        self.assertFalse(dialog.isVisible())

    def test_connection_optional_port_and_test_callback(self) -> None:
        added: list[tuple[str, str, int | None]] = []
        tested: list[str] = []
        dialog = QtConnectionDialog(
            None,
            callbacks=ConnectionDialogCallbacks(
                on_add=lambda *args: added.append(args),
                on_test=tested.append,
            ),
            node_id="node-7",
        )
        dialog.name_input.setText("Peer")
        dialog.host_input.setText(" peer.local ")
        self.assertIsNotNone(dialog.test_button)
        assert dialog.test_button is not None
        dialog.test_button.click()
        self.assertEqual(tested, ["node-7"])
        dialog.port_input.setText("")
        dialog.submit()
        self.assertEqual(added, [("Peer", "peer.local", None)])

    def test_connection_refuses_blank_host_and_accepts_upper_bound(self) -> None:
        added: list[tuple[str, str, int | None]] = []
        dialog = QtConnectionDialog(
            None,
            callbacks=ConnectionDialogCallbacks(
                on_add=lambda *args: added.append(args)
            ),
        )
        dialog.port_input.setText("65535")
        dialog.show()
        dialog.submit()
        self.assertEqual(added, [])
        self.assertTrue(dialog.isVisible())
        self.assertIn("Host", dialog.status_label.text())
        dialog.host_input.setText("peer.local")
        dialog.port_input.setText("-1")
        dialog.submit()
        self.assertTrue(dialog.isVisible())
        self.assertEqual(added, [])
        dialog.port_input.setText("not-a-port")
        dialog.submit()
        self.assertTrue(dialog.isVisible())
        self.assertEqual(added, [])

    def test_pairing_states_retry_and_cancel_once_on_escape(self) -> None:
        paired: list[str] = []
        cancelled: list[str] = []
        dialog = QtPairingDialog(
            None,
            spec=PairingDialogSpec(
                "peer-1", "Peer", "identity-public", "transport-public"
            ),
            on_pair=paired.append,
            on_cancel=cancelled.append,
        )
        self.assertIn("identity-public", dialog.identity_fingerprint_label.text())
        self.assertIn("transport-public", dialog.transport_fingerprint_label.text())
        dialog.pair_button.click()
        dialog.set_pending()
        dialog.pair_button.click()
        self.assertEqual(paired, ["peer-1"])
        self.assertFalse(dialog.pair_button.isEnabled())
        dialog.show_error("Could not pair; retry")
        self.assertTrue(dialog.pair_button.isEnabled())
        self.assertEqual(dialog.status_label.text(), "Could not pair; retry")
        dialog.set_pending()
        dialog.show_error("Could not pair; retry")
        dialog.show()
        dialog.activateWindow()
        dialog.setFocus()
        from PySide6.QtTest import QTest

        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertEqual(cancelled, ["peer-1"])
        dialog.close()
        self.assertEqual(cancelled, ["peer-1"])

    def test_pairing_completion_does_not_cancel(self) -> None:
        cancelled: list[str] = []
        dialog = QtPairingDialog(
            None,
            spec=PairingDialogSpec("peer-1"),
            on_pair=lambda _node: None,
            on_cancel=cancelled.append,
        )
        dialog.complete()
        self.assertEqual(cancelled, [])
        self.assertFalse(dialog.isVisible())

    def test_details_show_distinct_states_fields_and_gate_actions(self) -> None:
        called: list[str] = []
        long_fingerprint = "identity:" + "ab:" * 100
        dialog = QtNodeDetailsDialog(
            None,
            spec=NodeDetailsDialogSpec(
                node_id="peer",
                display_name="Peer",
                hostname="peer.local",
                host="192.0.2.4",
                port=8123,
                pairing_state="trusted",
                target_state="online",
                role="worker",
                permissions=("read",),
                selectable=True,
                openable=True,
                role_editable=True,
                identity_status="verified",
                identity_fingerprint=long_fingerprint,
                transport_fingerprint="tls:" + "cd:" * 100,
            ),
            callbacks=NodeDetailsDialogCallbacks(
                on_open=called.append,
                on_test=called.append,
                on_pause=called.append,
            ),
        )
        self.assertIn("trusted", dialog.detail_labels["Pairing"].text())
        self.assertIn("online", dialog.detail_labels["Target"].text())
        self.assertIn("192.0.2.4", dialog.detail_labels["Host"].text())
        self.assertIsNotNone(dialog.identity_fingerprint_label)
        self.assertIsNotNone(dialog.transport_fingerprint_label)
        assert dialog.identity_fingerprint_label is not None
        assert dialog.transport_fingerprint_label is not None
        self.assertIn("identity:", dialog.identity_fingerprint_label.text())
        self.assertIn("tls:", dialog.transport_fingerprint_label.text())
        self.assertIsNotNone(dialog.action("open"))
        self.assertIsNone(dialog.action("revoke"))
        dialog.invoke_action("open")
        self.assertEqual(called, ["peer"])
        dialog.resize(900, 600)
        dialog.show()
        self.app.processEvents()
        self.assertGreater(dialog.scroll_area.verticalScrollBar().maximum(), 0)

    def test_node_details_callbacks_cannot_override_spec_flags(self) -> None:
        dialog = QtNodeDetailsDialog(
            None,
            spec=NodeDetailsDialogSpec(node_id="peer", openable=False),
            callbacks=NodeDetailsDialogCallbacks(on_open=lambda _node: None),
        )
        self.assertIsNone(dialog.action("open"))
        callbackless = QtNodeDetailsDialog(
            None,
            spec=NodeDetailsDialogSpec(node_id="peer", openable=True),
        )
        self.assertIsNone(callbackless.action("open"))

    def test_sharing_displays_duration_and_dispatches_explicit_action(self) -> None:
        calls: list[str] = []
        dialog = QtSharingDialog(
            None,
            active=False,
            callbacks=SharingDialogCallbacks(
                on_share=lambda: calls.append("share"),
                on_stop=lambda: calls.append("stop"),
            ),
        )
        self.assertIn("Inactive", dialog.state_label.text())
        self.assertIn("5 minutes", dialog.action_button.text())
        dialog.show()
        dialog.action_button.click()
        self.assertEqual(calls, ["share"])
        self.assertFalse(dialog.isVisible())
        active = QtSharingDialog(
            None,
            active=True,
            callbacks=SharingDialogCallbacks(
                on_share=lambda: calls.append("share"),
                on_stop=lambda: calls.append("stop"),
            ),
        )
        self.assertIn("Active", active.state_label.text())
        active.show()
        active.action_button.click()
        self.assertEqual(calls, ["share", "stop"])
        self.assertFalse(active.isVisible())

    def test_dialogs_are_nonblocking_and_escape_closes(self) -> None:
        dialog = QtConnectionDialog(None, callbacks=ConnectionDialogCallbacks())
        self.assertIsInstance(dialog, QDialog)
        dialog.open()
        dialog.show()
        self.app.processEvents()
        self.assertTrue(dialog.isVisible())
        from PySide6.QtTest import QTest

        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertFalse(dialog.isVisible())
        self.assertEqual(
            [widget.text() for widget in dialog.findChildren(QPushButton)], []
        )
        self.assertEqual(len(dialog.findChildren(QLineEdit)), 3)


if __name__ == "__main__":
    unittest.main()
