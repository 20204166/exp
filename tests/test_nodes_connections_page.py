"""Headless tests for the reusable Nodes & Connections settings page."""

import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.nodes_connections import (
    DiscoveredPeerSpec,
    NodesConnectionsCallbacks,
    NodesConnectionsPage,
    TrustedNodeSpec,
)
from tests.support.widget_recording import FakeVar, RecordingWidget, WidgetRecorder


def make_callbacks() -> Any:
    return NodesConnectionsCallbacks(
        on_back=Mock(),
        on_discovery_toggle=Mock(),
        on_pair=Mock(),
        on_reject=Mock(),
        on_rename=Mock(),
        on_color=Mock(),
        on_revoke=Mock(),
        on_test_connection=Mock(),
        on_open_node=Mock(),
        on_add_manual_host=Mock(),
        on_remove_manual=Mock(),
    )


def make_page(
    callbacks: NodesConnectionsCallbacks | None = None,
    *,
    discovery_enabled: bool = True,
    discovered: list[DiscoveredPeerSpec] | None = None,
    trusted: list[TrustedNodeSpec] | None = None,
    manual: list[TrustedNodeSpec] | None = None,
    button_coordinator: ButtonCoordinator | None = None,
) -> tuple[NodesConnectionsPage, RecordingWidget, WidgetRecorder]:
    recorder = WidgetRecorder()
    parent = recorder.parent()
    page = NodesConnectionsPage(
        parent,
        callbacks=callbacks or make_callbacks(),
        discovery_enabled=discovery_enabled,
        discovered=discovered
        or [DiscoveredPeerSpec("peer-a", "peer-a-host", "1.2.4.0", True, True, 5000)],
        trusted=trusted
        or [
            TrustedNodeSpec(
                "peer-a",
                "Peer A",
                "peer-a-host",
                None,
                "online",
                "192.168.1.10",
                5000,
                True,
            )
        ],
        manual=manual
        or [
            TrustedNodeSpec(
                "manual-x:9",
                "Lab Box",
                "192.168.1.20",
                None,
                "unknown",
                "192.168.1.20",
                9,
                False,
                True,
            )
        ],
        frame_cls=recorder.frame_cls(),
        label_cls=recorder.label_cls(),
        style_frame_cls=recorder.style_frame_cls(),
        style_label_cls=recorder.style_label_cls(),
        button_cls=recorder.button_cls(),
        canvas_cls=recorder.canvas_cls(),
        scrollbar_cls=recorder.scrollbar_cls(),
        checkbutton_cls=recorder.checkbutton_cls(),
        combobox_cls=recorder.combobox_cls(),
        entry_cls=recorder.entry_cls(),
        button_coordinator=button_coordinator,
        var_factory=lambda: FakeVar(""),
        boolean_var_factory=lambda: FakeVar(False),
    )
    return page, parent, recorder


def button_with_text(recorder: WidgetRecorder, text: str) -> RecordingWidget:
    return next(
        widget
        for widget in recorder.widgets("button")
        if widget.kwargs.get("text") == text
    )


class NodesConnectionsPageTests(unittest.TestCase):
    def test_page_root_is_not_packed(self) -> None:
        _page, parent, _recorder = make_page()
        self.assertEqual(parent.pack_calls, [])

    def test_back_button_invokes_on_back(self) -> None:
        callbacks = make_callbacks()
        page, _parent, _recorder = make_page(callbacks)
        page.back_button.kwargs["command"]()
        callbacks.on_back.assert_called_once_with()

    def test_discovery_toggle_emits_enabled_state(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(callbacks, discovery_enabled=False)
        toggle = recorder.widgets("checkbutton")[0]
        toggle.kwargs["variable"].set(True)
        toggle.kwargs["command"]()
        callbacks.on_discovery_toggle.assert_called_once_with(True)

    def test_stable_actions_are_registered_and_cleared_by_prefix(self) -> None:
        coordinator = ButtonCoordinator()
        _page, _parent, _recorder = make_page(button_coordinator=coordinator)

        self.assertIn("nodes:discovery:toggle", coordinator.registered_ids())
        self.assertIn("nodes:peer:peer-a:pair", coordinator.registered_ids())

        coordinator.clear_prefix("nodes:peer:")

        self.assertFalse(coordinator.dispatch("nodes:peer:peer-a:pair"))
        self.assertTrue(coordinator.dispatch("nodes:discovery:toggle"))

    def test_pair_button_emits_peer_id(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(callbacks)
        button_with_text(recorder, "Pair").kwargs["command"]()
        callbacks.on_pair.assert_called_once_with("peer-a")

    def test_reject_button_emits_peer_id(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(callbacks)
        button_with_text(recorder, "Reject").kwargs["command"]()
        callbacks.on_reject.assert_called_once_with("peer-a")

    def test_discovered_rows_show_stable_id(self) -> None:
        _page, _parent, recorder = make_page()
        row_texts = [
            widget.kwargs.get("text", "") for widget in recorder.widgets("label")
        ]
        self.assertTrue(any("ID peer-a" in text for text in row_texts))

    def test_incompatible_peer_pair_button_is_disabled(self) -> None:
        _page, _parent, recorder = make_page(
            discovered=[DiscoveredPeerSpec("bad", "bad-host", "9", False, False, None)]
        )
        button = button_with_text(recorder, "Pair")
        self.assertEqual(button.kwargs["state"], "disabled")

    def test_trusted_actions_emit(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(callbacks)
        button_with_text(recorder, "Rename").kwargs["command"]()
        callbacks.on_rename.assert_called_once_with("peer-a")
        button_with_text(recorder, "Revoke").kwargs["command"]()
        callbacks.on_revoke.assert_called_once_with("peer-a")
        button_with_text(recorder, "Test").kwargs["command"]()
        callbacks.on_test_connection.assert_called_once_with("peer-a")
        button_with_text(recorder, "Open").kwargs["command"]()
        callbacks.on_open_node.assert_called_once_with("peer-a")

    def test_open_button_disabled_for_non_selectable(self) -> None:
        _page, _parent, recorder = make_page(
            trusted=[
                TrustedNodeSpec(
                    "peer", "Peer", "peer-host", None, "unknown", "h", None, False
                )
            ]
        )
        self.assertEqual(button_with_text(recorder, "Open").kwargs["state"], "disabled")

    def test_color_change_emits(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(callbacks)
        combo = recorder.widgets("combobox")[0]
        combo.kwargs["textvariable"].set("emerald")
        combo.bindings["<<ComboboxSelected>>"](None)
        callbacks.on_color.assert_called_once_with("peer-a", "emerald")

    def test_manual_host_add_emits_with_port(self) -> None:
        callbacks = make_callbacks()
        page, _parent, _recorder = make_page(callbacks)
        page._manual_name_var.set("Lab Box")
        page._manual_host_var.set("192.168.1.20")
        page._manual_port_var.set("9")
        page.add_host_button.kwargs["command"]()
        callbacks.on_add_manual_host.assert_called_once_with(
            "Lab Box", "192.168.1.20", 9
        )

    def test_manual_host_add_without_port(self) -> None:
        callbacks = make_callbacks()
        page, _parent, _recorder = make_page(callbacks)
        page._manual_name_var.set("Lab Box")
        page._manual_host_var.set("192.168.1.20")
        page._manual_port_var.set("")
        page.add_host_button.kwargs["command"]()
        callbacks.on_add_manual_host.assert_called_once_with(
            "Lab Box", "192.168.1.20", None
        )

    def test_manual_host_remove_emits(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(callbacks)
        button_with_text(recorder, "Remove").kwargs["command"]()
        callbacks.on_remove_manual.assert_called_once_with("manual-x:9")

    def test_refresh_updates_lists(self) -> None:
        _page, _parent, _recorder = make_page()
        _page.refresh_discovered([])
        _page.refresh_trusted([])
        _page.refresh_manual([])


if __name__ == "__main__":
    unittest.main()
