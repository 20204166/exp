"""Headless tests for the reusable Nodes & Connections settings page."""

import tkinter as tk
import unittest
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from maintenance.ui.action_coordinator import ButtonCoordinator
from maintenance.ui.nodes_connections import (
    DiscoveredPeerSpec,
    NodesConnectionsCallbacks,
    NodesConnectionsPage,
    TrustedNodeSpec,
)
from maintenance.ui.window_node_actions import _pairing_confirmation
from tests.support.live_tk import DISPLAY_AVAILABLE
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
        on_start_discovery=Mock(),
        on_permissions=Mock(),
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
        **recorder.page_kwargs(),
        checkbutton_cls=recorder.checkbutton_cls(),
        combobox_cls=recorder.combobox_cls(),
        entry_cls=recorder.entry_cls(),
        button_coordinator=button_coordinator,
        var_factory=lambda: FakeVar(""),
        boolean_var_factory=lambda: FakeVar(False),
    )
    return page, parent, recorder


def _discovered_spec(
    node_id: str = "peer-a", *, compatible: bool = True
) -> DiscoveredPeerSpec:
    return DiscoveredPeerSpec(
        node_id,
        f"{node_id}-host",
        "1.2.4.0",
        compatible,
        True,
        5000,
    )


def _trusted_spec(
    node_id: str = "peer-a", *, selectable: bool = True, status: str = "online"
) -> TrustedNodeSpec:
    return TrustedNodeSpec(
        node_id,
        f"Peer {node_id}",
        f"{node_id}-host",
        None,
        status,
        f"192.168.1.{len(node_id)}0",
        5000,
        selectable,
    )


class NodesConnectionsPageTests(unittest.TestCase):
    @unittest.skipUnless(DISPLAY_AVAILABLE, "Tk display unavailable")
    def test_narrow_page_keeps_content_inside_scroll_view(self) -> None:
        root = tk.Tk()
        root.geometry("420x700")
        callbacks = make_callbacks()
        page = NodesConnectionsPage(
            root,
            callbacks=callbacks,
            discovery_enabled=True,
            discovered=[
                DiscoveredPeerSpec(
                    "peer-a",
                    "m75-node1",
                    "1.4.5.0",
                    True,
                    True,
                    5000,
                    "aaaa:bbbb:cccc:dddd:eeee:ffff",
                )
            ],
            trusted=[],
            manual=[],
        )
        try:
            root.update()
            root.update_idletasks()
            root.update()
            # A few pixels of tolerance absorbs font-metric differences between
            # display backends (e.g. Xvfb vs. a real X server) -- this test's
            # intent is "content doesn't overflow the scroll viewport", not
            # "content is pixel-identical across renderers".
            self.assertLessEqual(
                page.content.winfo_width(), page.canvas.winfo_width() + 4
            )
        finally:
            root.destroy()

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

    def test_start_discovery_button_invokes_callback(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(callbacks)

        recorder.button_with_text("Start Discovery").kwargs["command"]()

        callbacks.on_start_discovery.assert_called_once_with()

    def test_learn_pairing_button_absent_by_default(self) -> None:
        _page, _parent, recorder = make_page()

        self.assertNotIn(
            "Learn about pairing & trust", recorder.label_texts(("button",))
        )

    def test_learn_pairing_button_invokes_callback_when_provided(self) -> None:
        callbacks = replace(make_callbacks(), on_learn_pairing=Mock())
        _page, _parent, recorder = make_page(callbacks)

        recorder.button_with_text("Learn about pairing & trust").kwargs["command"]()

        callbacks.on_learn_pairing.assert_called_once_with()

    def test_stable_actions_are_registered_and_cleared_by_prefix(self) -> None:
        coordinator = ButtonCoordinator()
        _page, _parent, _recorder = make_page(button_coordinator=coordinator)

        self.assertIn("nodes:discovery:toggle", coordinator.registered_ids())
        self.assertIn("nodes:discovery:start", coordinator.registered_ids())
        self.assertIn("nodes:peer:peer-a:pair", coordinator.registered_ids())

        coordinator.clear_prefix("nodes:peer:")

        self.assertFalse(coordinator.dispatch("nodes:peer:peer-a:pair"))
        self.assertTrue(coordinator.dispatch("nodes:discovery:toggle"))

    def test_pair_button_emits_peer_id(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(callbacks)
        recorder.button_with_text("Pair").kwargs["command"]()
        callbacks.on_pair.assert_called_once_with("peer-a")

    def test_pair_button_routes_selected_peer_to_pairing_opener(self) -> None:
        callbacks = replace(make_callbacks(), on_open_pairing=Mock())
        _page, _parent, recorder = make_page(callbacks)

        recorder.button_with_text("Pair").kwargs["command"]()

        callbacks.on_open_pairing.assert_called_once_with(_discovered_spec())

    def test_reject_button_emits_peer_id(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(callbacks)
        recorder.button_with_text("Reject").kwargs["command"]()
        callbacks.on_reject.assert_called_once_with("peer-a")

    def test_discovered_rows_show_stable_id(self) -> None:
        _page, _parent, recorder = make_page()
        row_texts = [
            widget.kwargs.get("text", "") for widget in recorder.widgets("label")
        ]
        self.assertTrue(any("Node ID: peer-a" in text for text in row_texts))

    def test_discovered_rows_show_identity_fingerprint(self) -> None:
        _page, _parent, recorder = make_page(
            discovered=[
                DiscoveredPeerSpec(
                    "peer-a",
                    "peer-a-host",
                    "1.2.4.0",
                    True,
                    True,
                    5000,
                    "aaaa:bbbb",
                )
            ]
        )
        row_texts = [
            widget.kwargs.get("text", "") for widget in recorder.widgets("label")
        ]
        self.assertTrue(any("fingerprint available" in text for text in row_texts))

    def test_pairing_confirmation_keeps_full_fingerprint_grouped(self) -> None:
        candidate = SimpleNamespace(
            hostname="peer-a",
            stable_id="peer-a",
            identity_fingerprint=":".join(f"{index:04x}" for index in range(17)),
        )

        message = _pairing_confirmation(candidate)

        self.assertIn(candidate.identity_fingerprint, message.replace("\n", ":"))
        self.assertIn("Stable node ID: peer-a", message)
        self.assertIn("trusted channel", message)

    def test_incompatible_peer_pair_button_is_disabled(self) -> None:
        _page, _parent, recorder = make_page(
            discovered=[DiscoveredPeerSpec("bad", "bad-host", "9", False, False, None)]
        )
        button = recorder.button_with_text("Pair")
        self.assertEqual(button.kwargs["state"], "disabled")

    def test_trusted_actions_emit(self) -> None:
        callbacks = make_callbacks()
        _page, _parent, recorder = make_page(callbacks)
        recorder.button_with_text("Rename").kwargs["command"]()
        callbacks.on_rename.assert_called_once_with("peer-a")
        recorder.button_with_text("Revoke").kwargs["command"]()
        callbacks.on_revoke.assert_called_once_with("peer-a")
        recorder.button_with_text("Test").kwargs["command"]()
        callbacks.on_test_connection.assert_called_once_with("peer-a")
        recorder.button_with_text("Open").kwargs["command"]()
        callbacks.on_open_node.assert_called_once_with("peer-a")

    def test_test_button_routes_selected_node_to_connection_opener(self) -> None:
        spec = _trusted_spec()
        callbacks = replace(make_callbacks(), on_open_connection=Mock())
        _page, _parent, recorder = make_page(callbacks, trusted=[spec])

        recorder.button_with_text("Test").kwargs["command"]()

        callbacks.on_open_connection.assert_called_once_with(spec)

    def test_manual_add_routes_to_connection_opener(self) -> None:
        callbacks = replace(make_callbacks(), on_open_connection=Mock())
        page, _parent, _recorder = make_page(callbacks)

        page.add_host_button.kwargs["command"]()

        callbacks.on_open_connection.assert_called_once_with(None)

    def test_trusted_actions_use_primary_and_danger_styles(self) -> None:
        _page, _parent, recorder = make_page()

        self.assertEqual(
            recorder.button_with_text("Open").kwargs["style"],
            "Primary.TButton",
        )
        self.assertEqual(
            recorder.button_with_text("Revoke").kwargs["style"],
            "Danger.TButton",
        )

    def test_trusted_permissions_are_grouped_and_destructive(self) -> None:
        _page, _parent, recorder = make_page()

        self.assertIn("Permissions", recorder.label_texts())
        controls = [
            control
            for control in recorder.widgets("checkbutton")
            if control.kwargs.get("text") != "Enabled"
        ]
        self.assertEqual(
            [control.kwargs["text"] for control in controls],
            [
                "View dashboard",
                "View components",
                "Review storage",
                "Review processes",
                "Terminate processes",
                "Force terminate",
            ],
        )
        self.assertEqual(
            [control.kwargs["style"] for control in controls],
            [
                "App.TCheckbutton",
                "App.TCheckbutton",
                "App.TCheckbutton",
                "App.TCheckbutton",
                "Danger.TCheckbutton",
                "Danger.TCheckbutton",
            ],
        )

    def test_open_button_disabled_for_non_selectable(self) -> None:
        _page, _parent, recorder = make_page(
            trusted=[
                TrustedNodeSpec(
                    "peer", "Peer", "peer-host", None, "unknown", "h", None, False
                )
            ]
        )
        self.assertEqual(recorder.button_with_text("Open").kwargs["state"], "disabled")

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
        recorder.button_with_text("Remove").kwargs["command"]()
        callbacks.on_remove_manual.assert_called_once_with("manual-x:9")

    def test_refresh_updates_lists(self) -> None:
        page, _parent, recorder = make_page()
        page.refresh_discovered([])
        page.refresh_trusted([])
        page.refresh_manual([])
        self.assertIn("No peers discovered yet.", recorder.label_texts())
        self.assertIn("No trusted nodes yet.", recorder.label_texts())
        self.assertIn("No manual hosts configured.", recorder.label_texts())

    @unittest.skipUnless(DISPLAY_AVAILABLE, "Tk display unavailable")
    def test_trusted_retained_buttons_stay_registered_exactly_once(self) -> None:
        root = tk.Tk()
        coordinator = ButtonCoordinator()
        page = NodesConnectionsPage(
            root,
            callbacks=make_callbacks(),
            discovery_enabled=False,
            discovered=[],
            trusted=[_trusted_spec("peer-a", selectable=True)],
            manual=[],
            button_coordinator=coordinator,
        )
        try:
            prior = coordinator._actions["nodes:trusted:peer-a:open"].widgets[0]
            for _ in range(30):
                page.refresh_trusted([_trusted_spec("peer-a", selectable=True)])
                self.assertTrue(prior.winfo_exists())
                widgets = coordinator._actions["nodes:trusted:peer-a:open"].widgets
                self.assertEqual(len(widgets), 1)
                self.assertIs(widgets[0], prior)
            page.refresh_trusted([])
            self.assertNotIn("nodes:trusted:peer-a:open", coordinator.registered_ids())
            self.assertFalse(coordinator.dispatch("nodes:trusted:peer-a:open"))
        finally:
            root.destroy()

    @unittest.skipUnless(DISPLAY_AVAILABLE, "Tk display unavailable")
    def test_discovered_row_retained_across_identical_refresh(self) -> None:
        root = tk.Tk()
        coordinator = ButtonCoordinator()
        page = NodesConnectionsPage(
            root,
            callbacks=make_callbacks(),
            discovery_enabled=False,
            discovered=[_discovered_spec("peer-a")],
            trusted=[],
            manual=[],
            button_coordinator=coordinator,
        )
        try:
            prior = coordinator._actions["nodes:peer:peer-a:pair"].widgets[0]
            page.refresh_discovered([_discovered_spec("peer-a")])
            self.assertTrue(prior.winfo_exists())
            self.assertIs(
                coordinator._actions["nodes:peer:peer-a:pair"].widgets[0], prior
            )
        finally:
            root.destroy()


class NodePresentationConnectionTests(unittest.TestCase):
    def test_connecting_label(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(connection_status_label("connecting"), "Connecting…")

    def test_auth_failed_label(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(connection_status_label("authentication_failed"), "Auth failed")

    def test_identity_changed_label(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(connection_status_label("identity_changed"), "Identity changed")

    def test_offline_retrying(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(
            connection_status_label("offline", retry_automatic=True), "Offline · retrying"
        )

    def test_offline_not_retrying(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(
            connection_status_label("offline", retry_automatic=False), "Offline"
        )

    def test_manual_disconnected(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(
            connection_status_label("offline", manual_disconnected=True), "Disconnected"
        )

    def test_online_label(self) -> None:
        from maintenance.ui.node_presentation import connection_status_label
        self.assertEqual(connection_status_label("online"), "Online")

    def test_auth_failed_color(self) -> None:
        from maintenance.ui.node_presentation import connection_status_color_role
        self.assertEqual(connection_status_color_role("authentication_failed"), "danger")

    def test_identity_changed_color(self) -> None:
        from maintenance.ui.node_presentation import connection_status_color_role
        self.assertEqual(connection_status_color_role("identity_changed"), "danger")

    def test_connecting_color(self) -> None:
        from maintenance.ui.node_presentation import connection_status_color_role
        self.assertEqual(connection_status_color_role("connecting"), "secondary")

    def test_online_color(self) -> None:
        from maintenance.ui.node_presentation import connection_status_color_role
        self.assertEqual(connection_status_color_role("online"), "success")

    def test_manual_disconnected_color(self) -> None:
        from maintenance.ui.node_presentation import connection_status_color_role
        self.assertEqual(
            connection_status_color_role("offline", manual_disconnected=True), "secondary"
        )

    def test_meta_text_uses_connection_status(self) -> None:
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="connecting")
        text = page._trusted_meta_text(spec)
        self.assertIn("Connecting", text)
        self.assertNotIn("Online", text)

    def test_meta_text_auth_failed(self) -> None:
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="authentication_failed")
        self.assertIn("Auth failed", page._trusted_meta_text(spec))

    def test_meta_text_manual_disconnected(self) -> None:
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), manual_disconnected=True)
        self.assertIn("Disconnected", page._trusted_meta_text(spec))

    def test_meta_text_offline_retrying(self) -> None:
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="offline", retry_automatic=True)
        self.assertIn("retrying", page._trusted_meta_text(spec))

    def test_meta_color_auth_failed_is_danger(self) -> None:
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="authentication_failed")
        self.assertEqual(page._trusted_meta_color(spec), "danger")

    def test_meta_color_manual_disconnected_is_secondary(self) -> None:
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), manual_disconnected=True)
        self.assertEqual(page._trusted_meta_color(spec), "secondary")

    def test_meta_color_identity_changed_is_danger(self) -> None:
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="identity_changed")
        self.assertEqual(page._trusted_meta_color(spec), "danger")

    def test_meta_color_online_is_success(self) -> None:
        page, _, _ = make_page()
        spec = replace(_trusted_spec("n1"), connection_status="online")
        self.assertEqual(page._trusted_meta_color(spec), "success")


class ConnectionStateMatrixTests(unittest.TestCase):
    """Assert backend state → TrustedNodeSpec → UI text/color for every state."""

    def _make_spec(
        self,
        connection_status: str = "online",
        manual_disconnected: bool = False,
        retry_automatic: bool = True,
        identity_status: str = "verified",
    ) -> TrustedNodeSpec:
        return TrustedNodeSpec(
            "n1", "Node 1", "host", None, "online", "host", 5000, True,
            connection_status=connection_status,
            manual_disconnected=manual_disconnected,
            retry_automatic=retry_automatic,
            identity_status=identity_status,
        )

    def _meta(self, spec: TrustedNodeSpec) -> tuple[str, str]:
        page, _, _ = make_page()
        return page._trusted_meta_text(spec), page._trusted_meta_color(spec)

    def test_online_shows_online(self) -> None:
        text, color = self._meta(self._make_spec("online"))
        self.assertIn("Online", text)
        self.assertEqual(color, "success")

    def test_connecting_not_offline(self) -> None:
        text, color = self._meta(self._make_spec("connecting"))
        self.assertIn("Connecting", text)
        self.assertNotIn("Offline", text)
        self.assertEqual(color, "secondary")

    def test_offline_retrying(self) -> None:
        text, color = self._meta(self._make_spec("offline", retry_automatic=True))
        self.assertIn("Offline", text)
        self.assertIn("retrying", text)
        self.assertEqual(color, "warning")

    def test_offline_no_retry(self) -> None:
        text, color = self._meta(self._make_spec("offline", retry_automatic=False))
        self.assertIn("Offline", text)
        self.assertNotIn("retrying", text)
        self.assertEqual(color, "warning")

    def test_authentication_failed_distinct(self) -> None:
        text, color = self._meta(self._make_spec("authentication_failed"))
        self.assertNotIn("Offline", text)
        self.assertIn("Auth failed", text)
        self.assertEqual(color, "danger")

    def test_identity_changed_distinct(self) -> None:
        text, color = self._meta(self._make_spec("identity_changed"))
        self.assertNotIn("Offline", text)
        self.assertIn("Identity changed", text)
        self.assertEqual(color, "danger")

    def test_manual_disconnect_shows_disconnected(self) -> None:
        text, color = self._meta(self._make_spec("offline", manual_disconnected=True))
        self.assertIn("Disconnected", text)
        self.assertNotIn("Offline", text)
        self.assertEqual(color, "secondary")

    def test_identity_mismatch_overrides_to_danger(self) -> None:
        _, color = self._meta(self._make_spec("online", identity_status="mismatch"))
        self.assertEqual(color, "danger")

    def test_unknown_does_not_crash(self) -> None:
        text, color = self._meta(self._make_spec("unknown"))
        self.assertIsInstance(text, str)
        self.assertIsInstance(color, str)


if __name__ == "__main__":
    unittest.main()
