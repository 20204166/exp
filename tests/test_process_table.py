from tests.support.scanner import make_scanner
"""Focused tests for the process tables: sorting, filtering, activity."""

import getpass
import tkinter as tk
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from maintenance.components.coordinator import AppCoordinator
from maintenance.dialogs import (
    ProcessDialog,
    process_matches_query,
    process_row_tags,
    process_sort_key,
    rebuild_tree_rows,
    selected_items,
)
from maintenance.models import ProcessActionResult, ProcessCandidate
from maintenance.nodes import NodeId
from maintenance.scanner import SystemScanner
from tests.support.scheduling import DeferredRunner
from tests.support.widget_recording import RecordingControl, RecordingTree


def _process(
    pid: int,
    name: str,
    *,
    cpu: float = 1.0,
    memory: int = 50 * 1024**2,
    activity: str = "Active",
    allowed: bool = True,
) -> ProcessCandidate:
    return ProcessCandidate(
        pid=pid,
        name=name,
        memory_bytes=memory,
        memory_percent=1.0,
        cpu_percent=cpu,
        activity=activity,
        username=getpass.getuser(),
        action_allowed=allowed,
    )


class ProcessSortKeyTests(unittest.TestCase):
    def test_numeric_columns_sort_numerically(self) -> None:
        low = _process(1000, "alpha", cpu=0.5, memory=10 * 1024**2)
        high = _process(2000, "beta", cpu=99.0, memory=900 * 1024**2)

        self.assertEqual(
            sorted([low, high], key=lambda p: process_sort_key("cpu", p)),
            [low, high],
        )
        self.assertEqual(
            sorted([high, low], key=lambda p: process_sort_key("memory", p)),
            [low, high],
        )
        self.assertEqual(
            sorted([high, low], key=lambda p: process_sort_key("pid", p)),
            [low, high],
        )

    def test_name_column_sorts_case_insensitively(self) -> None:
        a = _process(1, "Bravo")
        b = _process(2, "alpha")

        self.assertEqual(
            sorted([a, b], key=lambda p: process_sort_key("name", p)),
            [b, a],
        )

    def test_activity_and_permission_sort_by_rank(self) -> None:
        active = _process(1, "active", activity="Active")
        idle = _process(2, "idle", activity="Low activity")
        protected = _process(3, "protected", allowed=False)

        self.assertEqual(
            sorted([idle, active], key=lambda p: process_sort_key("activity", p)),
            [active, idle],
        )
        self.assertEqual(
            sorted(
                [protected, active],
                key=lambda p: process_sort_key("permission", p),
            ),
            [active, protected],
        )

    def test_unknown_sort_column_returns_uniform_key(self) -> None:
        first = _process(1, "alpha")
        second = _process(2, "beta")

        self.assertEqual(process_sort_key("bogus", first), 0)
        self.assertEqual(process_sort_key("bogus", second), 0)


class ProcessTableHelperTests(unittest.TestCase):
    def test_row_tags_mark_protected_and_low_activity(self) -> None:
        self.assertEqual(process_row_tags(_process(1, "ok")), ())
        self.assertEqual(
            process_row_tags(_process(1, "idle", activity="Low activity")),
            ("low",),
        )
        self.assertEqual(
            process_row_tags(_process(1, "protected", allowed=False)),
            ("protected",),
        )

    def test_query_matching_is_case_insensitive_and_empty_tolerant(self) -> None:
        process = _process(1, "Firefox Helper")

        self.assertTrue(process_matches_query(process, "firefox"))
        self.assertTrue(process_matches_query(process, "HELPER"))
        self.assertTrue(process_matches_query(process, ""))
        self.assertTrue(process_matches_query(process, "   "))
        self.assertTrue(process_matches_query(process, "  firefox  "))
        self.assertFalse(process_matches_query(process, "chrome"))

    def test_rebuild_tree_rows_replaces_all_rows(self) -> None:
        class FakeTree:
            def __init__(self) -> None:
                self.rows: list[tuple[str, tuple[object, ...], tuple[str, ...]]] = []

            def get_children(self) -> tuple[str, ...]:
                return tuple(row[0] for row in self.rows)

            def delete(self, *items: str) -> None:
                del items
                self.rows = []

            def insert(
                self,
                _parent: str,
                _index: str,
                iid: str,
                values: tuple[object, ...],
                tags: tuple[str, ...],
            ) -> None:
                self.rows.append((iid, values, tags))

        tree = FakeTree()
        rebuild_tree_rows(
            tree,
            [
                ("1", ("alpha",), ("protected",)),
                ("2", ("beta",), ()),
            ],
        )
        self.assertEqual(len(tree.rows), 2)

        rebuild_tree_rows(tree, [("3", ("gamma",), ())])
        self.assertEqual(len(tree.rows), 1)
        self.assertEqual(tree.rows[0][0], "3")

    def test_selected_items_skips_stale_ids_and_transforms_keys(self) -> None:
        class FakeTree:
            def selection(self) -> tuple[str, ...]:
                return ("10", "missing", "11")

        lookup = {10: "alpha", 11: "beta"}

        self.assertEqual(
            selected_items(FakeTree(), lookup, key_transform=int),
            ["alpha", "beta"],
        )

    def test_selected_items_empty_selection_returns_empty_list(self) -> None:
        class EmptyTree:
            def selection(self) -> tuple[str, ...]:
                return ()

        self.assertEqual(selected_items(EmptyTree(), {1: "alpha"}), [])

    def test_finish_refresh_clears_active_state(self) -> None:
        dialog = object.__new__(ProcessDialog)
        dialog._refresh_active = True

        dialog._finish_refresh()

        self.assertFalse(dialog._refresh_active)


class ProcessDialogCoordinatorTests(unittest.TestCase):
    def _dialog(self) -> Any:
        dialog: Any = object.__new__(ProcessDialog)
        dialog.coordinator = AppCoordinator()
        dialog.analyzer = Mock()
        dialog._waiting_for_shared = False
        dialog._refresh_active = False
        dialog.status_label = Mock()
        dialog.refresh_button = Mock()
        dialog.quit_button = Mock()
        dialog._show_processes = Mock()
        return dialog

    def test_second_instance_waits_instead_of_duplicate_process_scan(self) -> None:
        owner = self._dialog()
        waiter = self._dialog()
        owner.coordinator = waiter.coordinator = AppCoordinator()

        _generation, started = owner.coordinator.begin("process")
        self.assertTrue(started)

        waiter.refresh()

        self.assertTrue(waiter._waiting_for_shared)
        self.assertFalse(waiter._refresh_active)
        owner.coordinator.cancel("process")

    def test_waiter_renders_shared_process_result(self) -> None:
        operations = AppCoordinator()
        waiter = self._dialog()
        waiter.coordinator = operations
        generation, _started = operations.begin("process")
        waiter._wait_for_shared_scan()
        self.assertTrue(waiter._waiting_for_shared)

        operations.finish("process", generation, ["shared"])

        waiter._show_processes.assert_called_once_with(["shared"])
        self.assertFalse(waiter._waiting_for_shared)

    def test_cached_result_is_retrievable_for_instant_reopen(self) -> None:
        dialog = self._dialog()

        dialog.coordinator.store("process", ["cached"])

        self.assertEqual(dialog.coordinator.last_result("process"), ["cached"])
        self.assertIsNone(dialog.coordinator.last_result("never-run"))

    def test_refresh_starts_one_shared_run_and_finishes_idle(self) -> None:
        runner = DeferredRunner()
        dialog = self._dialog()
        dialog.coordinator = AppCoordinator(
            runner=runner,
            deliver=lambda callback: callback(),
        )

        dialog.refresh()

        self.assertTrue(dialog._refresh_active)
        self.assertTrue(dialog.coordinator.in_flight("process"))
        self.assertEqual(len(runner.workers), 1)

        runner.run_next()

        self.assertFalse(dialog._refresh_active)
        self.assertFalse(dialog.coordinator.in_flight("process"))
        dialog._show_processes.assert_called_once()

    def test_owner_error_clears_active_state(self) -> None:
        runner = DeferredRunner()
        dialog = self._dialog()
        dialog.coordinator = AppCoordinator(
            runner=runner, deliver=lambda callback: callback()
        )
        dialog.analyzer.process_candidates.side_effect = RuntimeError("boom")
        dialog._show_error = Mock()

        dialog.refresh()

        self.assertTrue(dialog._refresh_active)
        self.assertTrue(dialog.coordinator.in_flight("process"))

        runner.run_next()

        self.assertFalse(dialog._refresh_active)
        self.assertFalse(dialog.coordinator.in_flight("process"))
        dialog._show_error.assert_called_once_with("boom")

    def test_stale_callback_is_ignored_after_dialog_close(self) -> None:
        dialog = self._dialog()
        dialog._closed = True
        dialog._on_refresh_result(["stale"])
        dialog._show_processes.assert_not_called()


class ActivityClassificationTests(unittest.TestCase):
    def test_activity_label_uses_delta_threshold(self) -> None:
        self.assertEqual(SystemScanner._activity_label(0.0), "Low activity")
        self.assertEqual(SystemScanner._activity_label(0.5), "Low activity")
        self.assertEqual(SystemScanner._activity_label(1.0), "Active")
        self.assertEqual(SystemScanner._activity_label(12.5), "Active")

    def test_activity_label_handles_negative_and_below_threshold_deltas(self) -> None:
        threshold = SystemScanner.PROCESS_ACTIVITY_MIN_CPU_PERCENT
        self.assertEqual(SystemScanner._activity_label(threshold - 0.001), "Low activity")
        self.assertEqual(SystemScanner._activity_label(-1.0), "Low activity")


class FakeProcess:
    def __init__(
        self,
        pid: int,
        name: str,
        username: str,
        *,
        cpu: float,
        memory: int,
        create_time: float = 100.0,
        disappears: bool = False,
    ) -> None:
        self.pid = pid
        self._name = name
        self._username = username
        self._cpu = cpu
        self._memory = memory
        self._create_time = create_time
        self._disappears = disappears
        self.info = {"pid": pid, "create_time": create_time}

    def cpu_percent(self, _interval: float | None = None) -> float:
        return self._cpu

    def as_dict(self, attrs: list[str] | None = None) -> dict[str, Any]:
        del attrs
        if self._disappears:
            raise FakePsutil.NoSuchProcess("process exited")
        return {
            "pid": self.pid,
            "name": self._name,
            "username": self._username,
            "memory_info": SimpleNamespace(rss=self._memory),
            "memory_percent": 1.0,
            "create_time": self._create_time,
        }


class FakePsutil:
    class NoSuchProcess(Exception):
        pass

    class AccessDenied(Exception):
        pass

    def __init__(self, processes: list[FakeProcess]) -> None:
        self.processes = processes

    def process_iter(self, attrs: list[str] | None = None) -> list[FakeProcess]:
        del attrs
        return self.processes

    def Process(self, _pid: int) -> SimpleNamespace:
        return SimpleNamespace(parents=list)


class ProcessScanBehaviourTests(unittest.TestCase):
    def test_scan_processes_skips_process_that_disappears(self) -> None:
        keep = FakeProcess(
            50001,
            "Example App",
            getpass.getuser(),
            cpu=3.0,
            memory=50 * 1024**2,
        )
        gone = FakeProcess(
            50002,
            "Vanishing App",
            getpass.getuser(),
            cpu=3.0,
            memory=50 * 1024**2,
            disappears=True,
        )
        fake = FakePsutil([keep, gone])

        with patch("maintenance.scanner.psutil", fake):
            candidates = make_scanner().scan_processes()

        pids = {candidate.pid for candidate in candidates}
        self.assertIn(50001, pids)
        self.assertNotIn(50002, pids)

    def test_scan_processes_classifies_activity_from_delta(self) -> None:
        idle = FakeProcess(
            50001,
            "Idle App",
            getpass.getuser(),
            cpu=0.5,
            memory=50 * 1024**2,
        )
        busy = FakeProcess(
            50002,
            "Busy App",
            getpass.getuser(),
            cpu=3.0,
            memory=50 * 1024**2,
        )
        fake = FakePsutil([idle, busy])

        with patch("maintenance.scanner.psutil", fake):
            candidates = make_scanner().scan_processes()

        by_pid = {candidate.pid: candidate for candidate in candidates}
        self.assertEqual(by_pid[50001].activity, "Low activity")
        self.assertEqual(by_pid[50002].activity, "Active")
        self.assertTrue(by_pid[50001].action_allowed)


def _dialog_with(processes: dict[int, ProcessCandidate]) -> Any:
    dialog: Any = object.__new__(ProcessDialog)
    dialog.processes = processes
    dialog._displayed = list(processes.values())
    dialog._sort_column = "name"
    dialog._sort_reverse = False
    dialog.tree = RecordingTree()
    dialog.status_label = RecordingControl()
    dialog.quit_button = RecordingControl()
    dialog.refresh_button = RecordingControl()
    return dialog


class ProcessDialogNodeTests(unittest.TestCase):
    def _action_dialog(
        self,
        coordinator: AppCoordinator,
        manager: Any,
    ) -> Any:
        dialog: Any = object.__new__(ProcessDialog)
        dialog.coordinator = coordinator
        dialog.manager = manager
        dialog.node_id = NodeId("target")
        dialog._closed = False
        dialog._action_generation = 1
        dialog._action_in_flight = True
        dialog._action_unknown = False
        dialog._after_normal_quit = Mock()
        dialog._after_force_quit = Mock()
        dialog.status_label = Mock()
        dialog.quit_button = Mock()
        dialog._action_subscription_key = None
        dialog._action_subscription = None
        return dialog

    def test_two_dialogs_share_one_process_action_lease(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        first = self._action_dialog(coordinator, Mock())
        second = self._action_dialog(coordinator, Mock())

        first._run_shared_process_action("request_quit", [42], {42: 10.0}, 1)
        second._run_shared_process_action("request_quit", [42], {42: 10.0}, 1)

        self.assertEqual(len(runner.workers), 1)
        runner.run_next()
        first.manager.request_quit.assert_called_once_with([42], {42: 10.0})
        second.manager.request_quit.assert_not_called()
        first._after_normal_quit.assert_called_once()
        second._after_normal_quit.assert_called_once()

    def test_fresh_transport_nonce_does_not_make_a_second_action_key(self) -> None:
        coordinator = AppCoordinator(deliver=lambda callback: None)
        first = self._action_dialog(coordinator, Mock())
        second = self._action_dialog(coordinator, Mock())

        first_key = first._process_action_key("request_quit", [42], {42: 10.0})
        second_key = second._process_action_key("request_quit", [42], {42: 10.0})

        self.assertEqual(first_key, second_key)
        self.assertIn("node:target:process_action:request_quit", first_key)

    def test_response_loss_is_unknown_in_both_dialogs(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        first = self._action_dialog(coordinator, Mock())
        second = self._action_dialog(coordinator, Mock())
        first.manager.request_quit.side_effect = RuntimeError(
            "remote transport failed: connection closed"
        )

        first._run_shared_process_action("request_quit", [42], {42: 10.0}, 1)
        second._run_shared_process_action("request_quit", [42], {42: 10.0}, 1)
        runner.run_next()

        self.assertTrue(first._action_unknown)
        self.assertTrue(second._action_unknown)
        self.assertTrue(first._action_in_flight)
        self.assertTrue(second._action_in_flight)
        self.assertEqual(first.quit_button.config.call_count, 1)
        self.assertEqual(second.quit_button.config.call_count, 1)

    def test_normal_to_force_transition_stays_one_in_flight_request(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        first = self._action_dialog(coordinator, Mock())
        second = self._action_dialog(coordinator, Mock())
        first._after_normal_quit = ProcessDialog._after_normal_quit.__get__(first)
        second._after_normal_quit = ProcessDialog._after_normal_quit.__get__(second)
        first._selected_create_times = {42: 10.0}
        second._selected_create_times = {42: 10.0}
        normal = ProcessActionResult(1, (), (42,), ())

        with patch("maintenance.dialogs.messagebox.askyesno", return_value=True):
            first._after_normal_quit(normal)
            second._after_normal_quit(normal)

        self.assertEqual(len(runner.workers), 1)
        runner.run_next()
        first.manager.force_quit.assert_called_once_with([42], {42: 10.0})
        second.manager.force_quit.assert_not_called()

    def test_closed_dialog_drops_shared_action_result(self) -> None:
        runner = DeferredRunner()
        coordinator = AppCoordinator(runner=runner, deliver=lambda callback: callback())
        dialog = self._action_dialog(coordinator, Mock())

        dialog._run_shared_process_action("request_quit", [42], {42: 10.0}, 1)
        dialog._closed = True
        runner.run_next()

        dialog._after_normal_quit.assert_not_called()

    def test_duplicate_click_is_denied_while_action_is_in_flight(self) -> None:
        dialog: Any = object.__new__(ProcessDialog)
        dialog._action_in_flight = True
        dialog.quit_selected = ProcessDialog.quit_selected.__get__(dialog)
        dialog._read_only = False
        dialog.manager = Mock()
        dialog.quit_selected()
        dialog.manager.request_quit.assert_not_called()

    def test_stale_action_result_is_ignored_after_generation_changes(self) -> None:
        dialog: Any = object.__new__(ProcessDialog)
        dialog._closed = False
        dialog._action_generation = 2
        dialog._after_normal_quit = Mock()
        dialog._after_normal_quit_for_generation(1, Mock())
        dialog._after_normal_quit.assert_not_called()

    def test_lost_action_response_stays_unknown_and_disabled(self) -> None:
        dialog: Any = object.__new__(ProcessDialog)
        dialog._closed = False
        dialog._action_generation = 1
        dialog.quit_button = RecordingControl()
        dialog.status_label = RecordingControl()
        dialog._action_in_flight = True
        dialog._process_action_error(1, "remote transport failed: connection closed")
        self.assertTrue(dialog._action_in_flight)
        self.assertEqual(dialog.quit_button.state, tk.DISABLED)
        self.assertIsNotNone(dialog.status_label.text)
        assert dialog.status_label.text is not None
        self.assertIn("unknown", dialog.status_label.text)

    def test_node_qualified_operation_key_is_used(self) -> None:
        from maintenance.components.coordinator import AppCoordinator

        dialog: Any = object.__new__(ProcessDialog)
        dialog.coordinator = AppCoordinator(deliver=lambda cb: None)
        dialog.analyzer = Mock()
        dialog._operation_key = "node:dev:process"
        dialog._read_only = False
        dialog._waiting_for_shared = False
        dialog._refresh_active = False
        dialog.status_label = RecordingControl()
        dialog.refresh_button = RecordingControl()
        dialog.quit_button = RecordingControl()
        dialog._show_processes = Mock()
        dialog._on_refresh_result = Mock()

        dialog.refresh()

        self.assertTrue(dialog.coordinator.in_flight("node:dev:process"))

    def test_default_operation_key_is_local_process(self) -> None:
        dialog: Any = object.__new__(ProcessDialog)
        self.assertEqual(dialog._operation_key, "process")
        self.assertFalse(dialog._read_only)

    def test_read_only_dialog_keeps_quit_disabled_even_when_actionable(self) -> None:
        dialog = _dialog_with({100: _process(100, "Firefox")})
        dialog._read_only = True
        dialog._apply_filter("")
        dialog._render_rows()

        self.assertEqual(dialog.quit_button.state, tk.DISABLED)

    def test_dialog_source_provider_is_target_bound(self) -> None:
        dialog: Any = object.__new__(ProcessDialog)
        provider_a = Mock()
        dialog.provider = provider_a
        dialog.analyzer = Mock()
        dialog.node_id = "node-a"
        dialog._closed = False
        dialog._refresh_active = False
        dialog._waiting_for_shared = False
        dialog.coordinator = AppCoordinator(
            runner=lambda worker: None,
            deliver=lambda callback: None,
        )
        dialog._operation_key = "node:node-a:process_candidates"
        dialog.status_label = RecordingControl()
        dialog.refresh_button = RecordingControl()
        dialog.quit_button = RecordingControl()
        dialog._show_processes = Mock()
        dialog.refresh()
        self.assertIs(dialog.provider, provider_a)
        dialog.analyzer.process_candidates.assert_not_called()


class ProcessDialogEmptyStateTests(unittest.TestCase):
    def test_no_processes_shows_empty_state_and_disables_quit(self) -> None:
        dialog = _dialog_with({})
        dialog._apply_filter("")
        dialog._render_rows()

        self.assertEqual(
            dialog.status_label.text,
            "No processes available for cleanup review.",
        )
        self.assertEqual(dialog.quit_button.state, tk.DISABLED)
        self.assertEqual(dialog.refresh_button.state, tk.NORMAL)

    def test_filtered_out_processes_shows_match_message(self) -> None:
        dialog = _dialog_with({100: _process(100, "Firefox")})
        dialog._apply_filter("no-match")
        dialog._render_rows()

        self.assertEqual(dialog.status_label.text, 'No processes match "no-match"')
        self.assertEqual(dialog.quit_button.state, tk.DISABLED)

    def test_all_protected_rows_disable_quit(self) -> None:
        dialog = _dialog_with(
            {100: _process(100, "Protected App", allowed=False)},
        )
        dialog._apply_filter("")
        dialog._render_rows()

        self.assertEqual(dialog.status_label.text, "1 shown • 0 available for review")
        self.assertEqual(dialog.quit_button.state, tk.DISABLED)

    def test_available_rows_show_count_and_enable_quit(self) -> None:
        dialog = _dialog_with({100: _process(100, "Firefox")})
        dialog._apply_filter("")
        dialog._render_rows()

        self.assertEqual(dialog.status_label.text, "1 shown • 1 available for review")
        self.assertEqual(dialog.quit_button.state, tk.NORMAL)
        self.assertEqual(dialog.refresh_button.state, tk.NORMAL)


if __name__ == "__main__":
    unittest.main()
