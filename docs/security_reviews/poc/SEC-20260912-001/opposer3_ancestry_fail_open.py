"""Architecture counter-test: action-time PID protection is fail-open when ancestry is unreadable.

`ProcessManager` uses `protected_process_pids`, the lenient scan-time helper, to
compute protected PIDs at action time. That helper returns only the base set
``{0, 1, current_pid}`` when process ancestry cannot be read. The separately
shipped ``ProcessSafetyPolicy`` fails closed in the same situation. This test
demonstrates the divergence: a same-user, non-protected-name ancestor can be
terminated when ancestry lookup fails, even though the policy would refuse it.
"""

from __future__ import annotations

import getpass
import os
import unittest
from typing import Any
from unittest.mock import patch

from maintenance.actions import ProcessManager
from maintenance.components.process_safety import ProcessSafetyPolicy


class _FakeProcess:
    """Minimal ``psutil.Process`` fake for ancestry-failure tests."""

    def __init__(
        self,
        pid: int,
        name: str,
        username: str,
        *,
        create_time: float = 1000.0,
        parents: list[_FakeProcess] | None = None,
        parents_raise: bool = False,
        ignores_sigterm: bool = False,
    ) -> None:
        self.pid = pid
        self._name = name
        self._username = username
        self._create_time = create_time
        self._parents = parents or []
        self._parents_raise = parents_raise
        self.ignores_sigterm = ignores_sigterm
        self.terminated = False
        self.killed = False

    def name(self) -> str:
        return self._name

    def username(self) -> str:
        return self._username

    def exe(self) -> str | None:
        return None

    def create_time(self) -> float:
        return self._create_time

    def parents(self) -> list[Any]:
        if self._parents_raise:
            raise _FakePsutil.AccessDenied("ancestry hidden")
        return self._parents

    def children(self, recursive: bool = False) -> list[Any]:
        del recursive
        return []

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class _FakePsutil:
    class NoSuchProcess(Exception):
        pass

    class AccessDenied(Exception):
        pass

    def __init__(self, processes: dict[int, _FakeProcess]) -> None:
        self.processes = processes

    def Process(self, pid: int) -> _FakeProcess:
        try:
            return self.processes[pid]
        except KeyError as exc:
            raise _FakePsutil.NoSuchProcess(f"no process {pid}") from exc

    def wait_procs(
        self,
        processes: list[_FakeProcess],
        timeout: int,
    ) -> tuple[list[_FakeProcess], list[_FakeProcess]]:
        del timeout
        gone = [process for process in processes if not process.ignores_sigterm]
        alive = [process for process in processes if process.ignores_sigterm]
        return gone, alive


class AncestryFailOpenTests(unittest.TestCase):
    def test_manager_allows_ancestor_termination_when_ancestry_unreadable(self) -> None:
        """When ancestry is hidden, ProcessManager does not protect the parent."""

        current_user = getpass.getuser()
        current_pid = os.getpid()
        ancestor_pid = 50000

        current = _FakeProcess(
            current_pid, "system-analyzer", current_user, parents_raise=True
        )
        ancestor = _FakeProcess(ancestor_pid, "bash", current_user)
        fake = _FakePsutil({current_pid: current, ancestor_pid: ancestor})

        with patch("maintenance.actions.psutil", fake):
            manager = ProcessManager()
            result = manager.request_quit([ancestor_pid])

        self.assertIn(ancestor_pid, result.stopped)
        self.assertTrue(ancestor.terminated)

    def test_policy_refuses_ancestor_when_ancestry_unreadable(self) -> None:
        """ProcessSafetyPolicy fails closed for the same ancestor."""

        current_user = getpass.getuser()
        current_pid = os.getpid()
        ancestor_pid = 50000

        current = _FakeProcess(
            current_pid, "system-analyzer", current_user, parents_raise=True
        )
        ancestor = _FakeProcess(ancestor_pid, "bash", current_user)
        fake = _FakePsutil({current_pid: current, ancestor_pid: ancestor})

        policy = ProcessSafetyPolicy(
            current_pid_loader=lambda: current_pid,
            process_loader=fake.Process,
        )
        self.assertFalse(
            policy.can_manage_process(pid=ancestor_pid, current_user=current_user)
        )

    def test_manager_protects_ancestor_when_ancestry_readable(self) -> None:
        """With readable ancestry, the ancestor is correctly protected."""

        current_user = getpass.getuser()
        current_pid = os.getpid()
        ancestor_pid = 50000

        ancestor = _FakeProcess(ancestor_pid, "bash", current_user)
        current = _FakeProcess(
            current_pid, "system-analyzer", current_user, parents=[ancestor]
        )
        fake = _FakePsutil({current_pid: current, ancestor_pid: ancestor})

        with patch("maintenance.actions.psutil", fake):
            manager = ProcessManager()
            result = manager.request_quit([ancestor_pid])

        self.assertNotIn(ancestor_pid, result.stopped)
        self.assertFalse(ancestor.terminated)
        self.assertTrue(any(str(ancestor_pid) in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
