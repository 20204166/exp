"""Focused tests for process protection and termination behaviour."""

import getpass
import os
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from maintenance.actions import ProcessManager
from tests.support.process_actions import ActionProcess as FakeProcess
from tests.support.process_actions import ActionPsutil as FakePsutil


def _manager_with(
    processes: dict[int, FakeProcess],
) -> tuple[ProcessManager, FakePsutil, Any]:
    fake = FakePsutil(processes)
    patcher = patch("maintenance.actions.psutil", fake)
    patcher.start()
    return ProcessManager(), fake, patcher


class ProcessProtectionTests(unittest.TestCase):
    def test_create_time_change_before_action_is_rejected(self) -> None:
        class ChangingProcess(FakeProcess):
            def __init__(self) -> None:
                super().__init__(50001, "Example App", getpass.getuser())
                self._create_time_reads = 0

            def create_time(self) -> float:
                self._create_time_reads += 1
                return 1000.0 if self._create_time_reads == 1 else 2000.0

        process = ChangingProcess()
        manager, fake, patcher = _manager_with({50001: process})

        try:
            result = manager.request_quit(
                [50001], expected_create_times={50001: 1000.0}
            )
        finally:
            patcher.stop()

        self.assertFalse(fake.processes[50001].terminated)
        self.assertTrue(any("changed" in error for error in result.errors))

    def test_protected_by_pid_is_not_terminated(self) -> None:
        manager, fake, patcher = _manager_with(
            {os.getpid(): FakeProcess(os.getpid(), "python", getpass.getuser())}
        )

        try:
            result = manager.request_quit([os.getpid()])
        finally:
            patcher.stop()

        self.assertFalse(fake.processes[os.getpid()].terminated)
        self.assertTrue(any("protected" in error for error in result.errors))

    def test_protected_by_name_is_not_terminated(self) -> None:
        manager, fake, patcher = _manager_with(
            {50001: FakeProcess(50001, "systemd", getpass.getuser())}
        )

        try:
            result = manager.request_quit([50001])
        finally:
            patcher.stop()

        self.assertFalse(fake.processes[50001].terminated)
        self.assertTrue(any("protected" in error for error in result.errors))

    def test_protected_by_executable_path_is_not_terminated(self) -> None:
        manager, fake, patcher = _manager_with(
            {
                50001: FakeProcess(
                    50001,
                    "",
                    getpass.getuser(),
                    exe="/usr/lib/systemd/systemd",
                )
            }
        )

        try:
            result = manager.request_quit([50001])
        finally:
            patcher.stop()

        self.assertFalse(fake.processes[50001].terminated)
        self.assertTrue(any("protected" in error for error in result.errors))

    def test_pid_reuse_is_detected_via_create_time(self) -> None:
        manager, fake, patcher = _manager_with(
            {
                50001: FakeProcess(
                    50001, "Example App", getpass.getuser(), create_time=2000.0
                )
            }
        )

        try:
            result = manager.request_quit(
                [50001],
                expected_create_times={50001: 1000.0},
            )
        finally:
            patcher.stop()

        self.assertFalse(fake.processes[50001].terminated)
        self.assertTrue(any("changed" in error for error in result.errors))

    def test_matching_create_time_allows_quit(self) -> None:
        manager, fake, patcher = _manager_with(
            {
                50001: FakeProcess(
                    50001, "Example App", getpass.getuser(), create_time=1000.0
                )
            }
        )

        try:
            result = manager.request_quit(
                [50001],
                expected_create_times={50001: 1000.0},
            )
        finally:
            patcher.stop()

        self.assertTrue(fake.processes[50001].terminated)
        self.assertEqual(result.stopped, (50001,))

    def test_process_exited_before_click_is_reported_not_terminated(self) -> None:
        manager, _fake, patcher = _manager_with({})

        try:
            result = manager.request_quit([50001])
        finally:
            patcher.stop()

        self.assertEqual(result.stopped, ())
        self.assertTrue(any("50001" in error for error in result.errors))

    def test_permission_denied_is_reported_not_terminated(self) -> None:
        manager, fake, patcher = _manager_with(
            {
                50001: FakeProcess(
                    50001,
                    "Example App",
                    getpass.getuser(),
                    deny_name=True,
                )
            }
        )

        try:
            result = manager.request_quit([50001])
        finally:
            patcher.stop()

        self.assertFalse(fake.processes[50001].terminated)
        self.assertTrue(any("50001" in error for error in result.errors))


class ProcessTerminationTests(unittest.TestCase):
    def test_force_quit_rejects_child_identity_change(self) -> None:
        class ChangingChild(FakeProcess):
            def __init__(self) -> None:
                super().__init__(50002, "worker", getpass.getuser(), create_time=2000.0)
                self._create_time_reads = 0

            def create_time(self) -> float:
                self._create_time_reads += 1
                return 2000.0 if self._create_time_reads == 1 else 3000.0

        child = ChangingChild()
        parent = FakeProcess(
            50001,
            "Example App",
            getpass.getuser(),
            create_time=1000.0,
            children=[child],
        )
        fake = FakePsutil({50001: parent, 50002: child})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().force_quit(
                [50001], expected_create_times={50001: 1000.0}
            )

        self.assertFalse(child.killed)
        self.assertTrue(parent.killed)
        self.assertTrue(any("changed" in error for error in result.errors))

    def test_request_quit_terminates_but_does_not_kill_children(self) -> None:
        child = FakeProcess(50002, "worker", getpass.getuser())
        parent = FakeProcess(50001, "Example App", getpass.getuser(), children=[child])
        fake = FakePsutil({50001: parent, 50002: child})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([50001])

        self.assertTrue(parent.terminated)
        self.assertFalse(parent.killed)
        self.assertFalse(child.terminated)
        self.assertFalse(child.killed)
        self.assertEqual(result.stopped, (50001,))

    def test_force_quit_kills_children_then_parent(self) -> None:
        child = FakeProcess(50002, "worker", getpass.getuser())
        parent = FakeProcess(50001, "Example App", getpass.getuser(), children=[child])
        fake = FakePsutil({50001: parent, 50002: child})
        events: list[int] = []

        original_kill = parent.kill

        def record_child_kill() -> None:
            events.append(child.pid)
            child.killed = True

        child.kill = record_child_kill  # type: ignore[method-assign]

        def record_parent_kill() -> None:
            events.append(parent.pid)
            original_kill()

        parent.kill = record_parent_kill  # type: ignore[method-assign]

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().force_quit([50001])

        self.assertTrue(parent.killed)
        self.assertTrue(child.killed)
        self.assertEqual(events, [50002, 50001])
        self.assertEqual(result.stopped, (50001,))

    def test_process_ignoring_sigterm_requires_force(self) -> None:
        process = FakeProcess(
            50001,
            "Example App",
            getpass.getuser(),
            ignores_sigterm=True,
        )
        fake = FakePsutil({50001: process})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([50001])

        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)
        self.assertEqual(result.stopped, ())
        self.assertEqual(result.force_required, (50001,))

    def test_multiple_processes_quit_with_protected_skipped(self) -> None:
        first = FakeProcess(50001, "App A", getpass.getuser())
        second = FakeProcess(50002, "App B", getpass.getuser())
        protected = FakeProcess(50003, "systemd", getpass.getuser())
        fake = FakePsutil({50001: first, 50002: second, 50003: protected})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([50001, 50002, 50003])

        self.assertTrue(first.terminated)
        self.assertTrue(second.terminated)
        self.assertFalse(protected.terminated)
        self.assertEqual(result.stopped, (50001, 50002))
        self.assertEqual(result.requested, 3)


class ProtectedProcessCheckTests(unittest.TestCase):
    def test_is_protected_process_by_name(self) -> None:
        process = FakeProcess(1, "systemd", getpass.getuser())

        self.assertTrue(ProcessManager._is_protected_process("systemd", process))

    def test_is_protected_process_by_executable_basename(self) -> None:
        process = FakeProcess(
            1,
            "unrelated",
            getpass.getuser(),
            exe=str(Path("/usr/lib/systemd/systemd")),
        )

        self.assertTrue(ProcessManager._is_protected_process("unrelated", process))

    def test_is_protected_process_returns_false_when_exe_unreadable(self) -> None:
        process = FakeProcess(1, "unrelated", getpass.getuser(), exe=None)

        self.assertFalse(ProcessManager._is_protected_process("unrelated", process))


class ProcessSafetyEdgeTests(unittest.TestCase):
    def test_foreign_user_process_is_not_terminated(self) -> None:
        manager, fake, patcher = _manager_with(
            {50001: FakeProcess(50001, "Example App", "someone_else")}
        )

        try:
            result = manager.request_quit([50001])
        finally:
            patcher.stop()

        self.assertFalse(fake.processes[50001].terminated)
        self.assertTrue(any("protected" in error for error in result.errors))

    def test_permission_error_during_username_read_is_not_terminated(self) -> None:
        manager, fake, patcher = _manager_with(
            {
                50001: FakeProcess(
                    50001,
                    "Example App",
                    getpass.getuser(),
                    deny_username=True,
                )
            }
        )

        try:
            result = manager.request_quit([50001])
        finally:
            patcher.stop()

        self.assertFalse(fake.processes[50001].terminated)
        self.assertTrue(any("50001" in error for error in result.errors))

    def test_force_quit_skips_protected_child(self) -> None:
        parent = FakeProcess(50001, "Example App", getpass.getuser())
        protected_child = FakeProcess(50002, "systemd", getpass.getuser())
        foreign_child = FakeProcess(50003, "worker", "someone_else")
        parent._children = [protected_child, foreign_child]
        fake = FakePsutil({50001: parent, 50002: protected_child, 50003: foreign_child})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().force_quit([50001])

        # The parent is killed; unsafe children are not touched.
        self.assertTrue(parent.killed)
        self.assertFalse(protected_child.killed)
        self.assertFalse(foreign_child.killed)
        self.assertTrue(any("protected" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
