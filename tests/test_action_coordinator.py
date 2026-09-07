"""Tests for the reusable direct-action coordinator."""

import tkinter as tk
import unittest
from unittest.mock import Mock

from maintenance.ui.action_coordinator import ButtonCoordinator
from tests.support.widget_recording import RecordingWidget


class ButtonCoordinatorTests(unittest.TestCase):
    def test_register_and_dispatch_calls_callback(self) -> None:
        coordinator = ButtonCoordinator()
        callback = Mock()

        coordinator.register("dashboard:settings", callback)

        self.assertTrue(coordinator.dispatch("dashboard:settings"))
        callback.assert_called_once_with()

    def test_bind_sets_command_and_state(self) -> None:
        coordinator = ButtonCoordinator()
        callback = Mock()
        widget = RecordingWidget()

        coordinator.register("settings:category:preferences", callback)
        coordinator.bind(widget, "settings:category:preferences")

        self.assertEqual(widget.config_options["state"], "normal")
        self.assertTrue(callable(widget.config_options["command"]))
        widget.config_options["command"]()
        callback.assert_called_once_with()

    def test_disabled_action_blocks_dispatch_and_updates_widgets(self) -> None:
        coordinator = ButtonCoordinator()
        callback = Mock()
        widget = RecordingWidget()

        coordinator.register("preferences:cancel-scan", callback, enabled=False)
        coordinator.bind(widget, "preferences:cancel-scan")

        self.assertEqual(widget.config_options["state"], "disabled")
        self.assertFalse(coordinator.dispatch("preferences:cancel-scan"))
        callback.assert_not_called()

    def test_duplicate_registration_requires_replace(self) -> None:
        coordinator = ButtonCoordinator()
        first = Mock()
        second = Mock()

        coordinator.register("nodes:peer:peer-a:pair", first)
        with self.assertRaises(ValueError):
            coordinator.register("nodes:peer:peer-a:pair", second)

        coordinator.register(
            "nodes:peer:peer-a:pair", second, replace=True, enabled=False
        )
        self.assertFalse(coordinator.dispatch("nodes:peer:peer-a:pair"))
        second.assert_not_called()

    def test_dead_widgets_are_dropped_during_replacement(self) -> None:
        coordinator = ButtonCoordinator()
        callback = Mock()
        widget = RecordingWidget()

        coordinator.register("dashboard:settings", callback)
        coordinator.bind(widget, "dashboard:settings")
        widget.destroy()

        coordinator.register("dashboard:settings", callback, replace=True)

        self.assertEqual(coordinator.registered_ids(), ("dashboard:settings",))
        self.assertEqual(coordinator._actions["dashboard:settings"].widgets, [])

    def test_clear_prefix_removes_only_matching_actions(self) -> None:
        coordinator = ButtonCoordinator()
        pair = Mock()
        open_node = Mock()

        coordinator.register("nodes:peer:peer-a:pair", pair)
        coordinator.register("cluster:node:peer-a:open", open_node)

        coordinator.clear_prefix("nodes:peer:")

        self.assertFalse(coordinator.dispatch("nodes:peer:peer-a:pair"))
        self.assertTrue(coordinator.dispatch("cluster:node:peer-a:open"))
        open_node.assert_called_once_with()

    def test_bind_unknown_action_raises_key_error(self) -> None:
        coordinator = ButtonCoordinator()

        with self.assertRaises(KeyError):
            coordinator.bind(RecordingWidget(), "missing")

    def test_bind_tcl_error_drops_dead_widget(self) -> None:
        coordinator = ButtonCoordinator()
        callback = Mock()

        class RaisingWidget:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def winfo_exists(self) -> bool:
                return True

            def config(self, **options: object) -> None:
                raise tk.TclError("invalid command name")

        widget = RaisingWidget()

        coordinator.register("dashboard:settings", callback)
        coordinator.bind(widget, "dashboard:settings")

        self.assertEqual(coordinator._actions["dashboard:settings"].widgets, [])
        self.assertTrue(coordinator.dispatch("dashboard:settings"))
        callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
