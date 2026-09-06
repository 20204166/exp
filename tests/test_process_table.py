"""Focused tests for the process tables: sorting, filtering, activity."""

import getpass
import tkinter as tk
import unittest
from pathlib import Path
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
)
from maintenance.models import ProcessCandidate
from maintenance.scanner import SystemScanner
from tests.support.scheduling import DeferredRunner


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


class ActivityClassificationTests(unittest.TestCase):
    def test_activity_label_uses_delta_threshold(self) -> None:
        self.assertEqual(SystemScanner._activity_label(0.0), "Low activity")
        self.assertEqual(SystemScanner._activity_label(0.5), "Low activity")
        self.assertEqual(SystemScanner._activity_label(1.0), "Active")
        self.assertEqual(SystemScanner._activity_label(12.5), "Active")


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
            candidates = SystemScanner(Path("Downloads")).scan_processes()

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
            candidates = SystemScanner(Path("Downloads")).scan_processes()

        by_pid = {candidate.pid: candidate for candidate in candidates}
        self.assertEqual(by_pid[50001].activity, "Low activity")
        self.assertEqual(by_pid[50002].activity, "Active")
        self.assertTrue(by_pid[50001].action_allowed)


class FakeTree:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    def delete(self, *items: object) -> None:
        self.rows.clear()

    def get_children(self) -> tuple[()]:
        return ()

    def insert(self, *args: object, **kwargs: object) -> None:
        self.rows.append(args)


class FakeControl:
    def __init__(self) -> None:
        self.state: str | None = None
        self.text: str | None = None

    def config(self, **options: object) -> None:
        state = options.get("state")
        text = options.get("text")
        self.state = state if isinstance(state, str) else None
        self.text = text if isinstance(text, str) else None


def _dialog_with(processes: dict[int, ProcessCandidate]) -> Any:
    dialog: Any = object.__new__(ProcessDialog)
    dialog.processes = processes
    dialog._displayed = list(processes.values())
    dialog._sort_column = "name"
    dialog._sort_reverse = False
    dialog.tree = FakeTree()
    dialog.status_label = FakeControl()
    dialog.quit_button = FakeControl()
    dialog.refresh_button = FakeControl()
    return dialog


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
