"""Contract tests for the presentation-only node dialog adapters."""

import unittest
from typing import Any

from maintenance.ui.connection_dialog import ConnectionDialog
from maintenance.ui.node_details_dialog import (
    NodeDetailsDialog,
    NodeDetailsDialogCallbacks,
    NodeDetailsDialogSpec,
)
from maintenance.ui.pairing_dialog import PairingDialog, PairingDialogSpec
from maintenance.ui.sharing_dialog import SharingDialog
from tests.support.widget_recording import RecordingWidget, WidgetRecorder


class FakeToplevel(RecordingWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.destroy_calls = 0
        self.window_options: dict[str, Any] = {}

    def title(self, value: str) -> None:
        self.window_options["title"] = value

    def geometry(self, value: str) -> None:
        self.window_options["geometry"] = value

    def minsize(self, width: int, height: int) -> None:
        self.window_options["minsize"] = (width, height)

    def transient(self, parent: Any) -> None:
        self.window_options["transient"] = parent

    def protocol(self, name: str, callback: Any) -> None:
        self.window_options[name] = callback

    def destroy(self) -> None:
        self.destroy_calls += 1
        super().destroy()


def _dialog_widgets(*, include_entry: bool = False) -> dict[str, Any]:
    recorder = WidgetRecorder()
    widgets = {
        "toplevel_cls": FakeToplevel,
        "frame_cls": recorder.frame_cls(),
        "label_cls": recorder.label_cls(),
        "button_cls": recorder.button_cls(),
    }
    if include_entry:
        widgets["entry_cls"] = recorder.entry_cls()
    return widgets


def recorder_var() -> Any:
    from tests.support.widget_recording import FakeVar

    return FakeVar()


class NodeToplevelDialogContractTests(unittest.TestCase):
    def test_connection_dialog_dispatches_manual_host_callback(self) -> None:
        calls: list[tuple[str, str, int]] = []
        dialog = ConnectionDialog(
            RecordingWidget(),
            on_add=lambda name, host, port: calls.append((name, host, port)),
            var_factory=recorder_var,
            **_dialog_widgets(include_entry=True),
        )
        dialog.host_var.set("peer.local")
        dialog.port_var.set("8123")
        dialog.name_var.set("Peer")

        dialog.submit()

        self.assertEqual(calls, [("Peer", "peer.local", 8123)])

    def test_connection_dialog_creates_entries_and_rejects_invalid_port(self) -> None:
        recorder = WidgetRecorder()
        calls: list[tuple[str, str, int | None]] = []
        dialog = ConnectionDialog(
            recorder.parent(),
            on_add=lambda name, host, port: calls.append((name, host, port)),
            var_factory=recorder_var,
            frame_cls=recorder.frame_cls(),
            label_cls=recorder.label_cls(),
            button_cls=recorder.button_cls(),
            entry_cls=recorder.entry_cls(),
            toplevel_cls=FakeToplevel,
        )
        dialog.host_var.set("peer.local")
        dialog.port_var.set("70000")
        dialog.submit()

        self.assertEqual(len(recorder.widgets("entry")), 3)
        self.assertEqual(calls, [])
        self.assertIn("port", dialog.status_text().lower())

    def test_connection_dialog_rejects_blank_host(self) -> None:
        calls: list[tuple[str, str, int | None]] = []
        dialog = ConnectionDialog(
            RecordingWidget(),
            on_add=lambda name, host, port: calls.append((name, host, port)),
            var_factory=recorder_var,
            **_dialog_widgets(include_entry=True),
        )
        dialog.host_var.set("")
        dialog.port_var.set("")

        dialog.submit()

        self.assertEqual(calls, [])
        self.assertIn("host", dialog.status_text().lower())

    def test_connection_dialog_rejects_non_numeric_port(self) -> None:
        calls: list[tuple[str, str, int | None]] = []
        dialog = ConnectionDialog(
            RecordingWidget(),
            on_add=lambda name, host, port: calls.append((name, host, port)),
            var_factory=recorder_var,
            **_dialog_widgets(include_entry=True),
        )
        dialog.host_var.set("peer.local")
        dialog.port_var.set("not-a-port")

        dialog.submit()

        self.assertEqual(calls, [])
        self.assertIn("port", dialog.status_text().lower())

    def test_connection_dialog_allows_optional_port(self) -> None:
        calls: list[tuple[str, str, int | None]] = []
        dialog = ConnectionDialog(
            RecordingWidget(),
            on_add=lambda name, host, port: calls.append((name, host, port)),
            var_factory=recorder_var,
            **_dialog_widgets(include_entry=True),
        )
        dialog.name_var.set("Peer")
        dialog.host_var.set("peer.local")
        dialog.port_var.set("")

        dialog.submit()

        self.assertEqual(calls, [("Peer", "peer.local", None)])

    def test_connection_dialog_test_action_dispatches_node_id(self) -> None:
        calls: list[str] = []
        recorder = WidgetRecorder()
        _dialog = ConnectionDialog(
            recorder.parent(),
            on_add=lambda *_args: None,
            node_id="node-1",
            on_test=lambda node_id: calls.append(node_id),
            var_factory=recorder_var,
            frame_cls=recorder.frame_cls(),
            label_cls=recorder.label_cls(),
            button_cls=recorder.button_cls(),
            entry_cls=recorder.entry_cls(),
            toplevel_cls=FakeToplevel,
        )

        recorder.button_with_text("Test connection").kwargs["command"]()

        self.assertEqual(calls, ["node-1"])

    def test_pairing_dialog_dispatches_node_id(self) -> None:
        calls: list[str] = []
        dialog = PairingDialog(
            RecordingWidget(),
            spec=PairingDialogSpec(node_id="node-1"),
            on_pair=lambda node_id: calls.append(node_id),
            **_dialog_widgets(),
        )

        dialog.confirm()

        self.assertEqual(calls, ["node-1"])

    def test_pairing_dialog_renders_identity_and_tls_fingerprints(self) -> None:
        recorder = WidgetRecorder()
        PairingDialog(
            recorder.parent(),
            spec=PairingDialogSpec(
                node_id="node-1",
                display_name="Peer",
                identity_fingerprint="identity:aa:bb",
                transport_fingerprint="tls:11:22",
            ),
            on_pair=lambda _node_id: None,
            frame_cls=recorder.frame_cls(),
            label_cls=recorder.label_cls(),
            button_cls=recorder.button_cls(),
            toplevel_cls=FakeToplevel,
        )

        labels = recorder.label_texts()
        self.assertTrue(any("identity:aa:bb" in text for text in labels))
        self.assertTrue(any("tls:11:22" in text for text in labels))

    def test_pairing_dialog_cancellation_does_not_pair(self) -> None:
        calls: list[str] = []
        dialog = PairingDialog(
            RecordingWidget(),
            spec=PairingDialogSpec(node_id="node-1"),
            on_pair=lambda node_id: calls.append(node_id),
            **_dialog_widgets(),
        )

        dialog.close()

        self.assertEqual(calls, [])

    def test_node_details_dialog_dispatches_allowed_open_action(self) -> None:
        calls: list[str] = []
        dialog = NodeDetailsDialog(
            RecordingWidget(),
            spec=NodeDetailsDialogSpec(
                node_id="node-1", display_name="Peer", openable=True
            ),
            callbacks=NodeDetailsDialogCallbacks(
                on_open=lambda node_id: calls.append(node_id)
            ),
            **_dialog_widgets(),
        )

        dialog.invoke_action("open")

        self.assertEqual(calls, ["node-1"])

    def test_node_details_dialog_hides_disallowed_actions_and_renders_spec(
        self,
    ) -> None:
        recorder = WidgetRecorder()
        dialog = NodeDetailsDialog(
            recorder.parent(),
            spec=NodeDetailsDialogSpec(
                node_id="node-1",
                display_name="Peer",
                hostname="peer.local",
                host="10.0.0.2",
                port=8123,
                pairing_state="trusted",
                target_state="Ready",
                role="worker",
                permissions=("read",),
                openable=False,
                selectable=False,
            ),
            callbacks=NodeDetailsDialogCallbacks(),
            frame_cls=recorder.frame_cls(),
            label_cls=recorder.label_cls(),
            button_cls=recorder.button_cls(),
            toplevel_cls=FakeToplevel,
        )

        self.assertIsNone(dialog.action("open"))
        labels = recorder.label_texts()
        self.assertTrue(any("Peer" in text for text in labels))
        self.assertTrue(any("peer.local" in text for text in labels))
        self.assertTrue(any("10.0.0.2" in text for text in labels))
        self.assertTrue(any("8123" in text for text in labels))
        self.assertTrue(any("Ready" in text for text in labels))

    def test_sharing_dialog_dispatches_existing_callbacks(self) -> None:
        calls: list[str] = []
        dialog = SharingDialog(
            RecordingWidget(),
            active=False,
            on_share=lambda: calls.append("share"),
            on_stop=lambda: calls.append("stop"),
            **_dialog_widgets(),
        )

        dialog.confirm()
        dialog.active = True
        dialog.confirm()

        self.assertEqual(calls, ["share", "stop"])

    def test_sharing_dialog_presents_active_and_inactive_states(self) -> None:
        for active, expected_state, expected_button in (
            (False, "Inactive", "Share for 5 minutes"),
            (True, "Active", "Stop sharing"),
        ):
            recorder = WidgetRecorder()
            SharingDialog(
                recorder.parent(),
                active=active,
                on_share=lambda: None,
                on_stop=lambda: None,
                frame_cls=recorder.frame_cls(),
                label_cls=recorder.label_cls(),
                button_cls=recorder.button_cls(),
                toplevel_cls=FakeToplevel,
            )
            self.assertIn(expected_state, recorder.label_texts())
            self.assertIn(
                expected_button,
                recorder.label_texts()
                | {
                    widget.kwargs.get("text")
                    for widget in recorder.widgets("button")
                    if isinstance(widget.kwargs.get("text"), str)
                },
            )

    def test_each_dialog_closes_its_toplevel_once(self) -> None:
        dialogs = (
            ConnectionDialog(
                RecordingWidget(),
                on_add=lambda *_args: None,
                var_factory=recorder_var,
                **_dialog_widgets(include_entry=True),
            ),
            PairingDialog(
                RecordingWidget(),
                spec=PairingDialogSpec(node_id="node-1"),
                on_pair=lambda _node_id: None,
                **_dialog_widgets(),
            ),
            NodeDetailsDialog(
                RecordingWidget(),
                spec=NodeDetailsDialogSpec(node_id="node-1"),
                **_dialog_widgets(),
            ),
            SharingDialog(
                RecordingWidget(),
                active=False,
                on_share=lambda: None,
                on_stop=lambda: None,
                **_dialog_widgets(),
            ),
        )

        for dialog in dialogs:
            dialog.close()
            dialog.close()
            self.assertEqual(dialog.window.destroy_calls, 1)


if __name__ == "__main__":
    unittest.main()
