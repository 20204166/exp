"""Opposer 2 control-verification counter-test for SEC-20260912-001.

Verifies the controls claimed in the review's "Existing Controls" section
against the actual action path (``ProcessManager``) and the fail-closed
policy (``ProcessSafetyPolicy``):

1. Protected PID set includes PID 0, PID 1, the current process, and ancestry.
2. Protected names are centralized and case-folded.
3. Windows domain prefixes are normalized before username comparison.
4. Incomplete ancestry or lookup failures fail closed.
5. Create-time checks defend against PID reuse.
6. Access-denied on identity reads blocks the action.
7. Force-quit children are rechecked before termination.

Decisive question for control 4: does the ACTION path fail closed when the
current process's ancestry cannot be read? ``ProcessSafetyPolicy`` fails
closed, but ``ProcessManager._allowed_processes`` uses the lenient
``protected_process_pids`` snapshot, so the action path is expected to
terminate a same-user parent PID even when ancestry is unreadable.

Run: python -m unittest docs/security_reviews/poc/SEC-20260912-001/opposer2_control_verification.py -v
"""

import getpass
import os
import unittest
from unittest.mock import patch

from maintenance.actions import ProcessManager
from maintenance.components import ProcessSafetyPolicy
from maintenance.nodes import (
    NodeId,
    ProcessActionKind,
    ProcessRef,
    ProcessTerminationRequest,
)
from tests.support.process_actions import ActionProcess as FakeProcess
from tests.support.process_actions import ActionPsutil as FakePsutil


class DeniedAncestryProcess(FakeProcess):
    """Fake process whose ancestry lookup raises AccessDenied."""

    def __init__(self, pid: int) -> None:
        super().__init__(pid, "Example App", getpass.getuser())

    def parents(self) -> list[FakeProcess]:
        raise FakePsutil.AccessDenied("permission denied")


class DeniedAncestryPsutil(FakePsutil):
    """Fake psutil whose own-process ancestry lookup raises AccessDenied."""

    def Process(self, pid: int) -> FakeProcess:
        if pid == os.getpid():
            return DeniedAncestryProcess(pid)
        return super().Process(pid)


class ControlVerificationTests(unittest.TestCase):
    """Control-by-control verification of the process-termination surface."""

    # --- Control 1: protected PID set (0, 1, current process) -------------

    def test_protected_pids_are_never_terminated(self) -> None:
        for pid in (0, 1, os.getpid()):
            process = FakeProcess(pid, "Example App", getpass.getuser())
            fake = FakePsutil({pid: process})
            with patch("maintenance.actions.psutil", fake):
                result = ProcessManager().request_quit([pid])
            self.assertFalse(process.terminated, f"PID {pid} was terminated")
            self.assertTrue(
                any("protected" in error for error in result.errors),
                f"PID {pid} produced no protected error",
            )

    def test_ancestry_pids_are_protected_when_readable(self) -> None:
        class ParentChainProcess(FakeProcess):
            def __init__(self, pid: int) -> None:
                super().__init__(pid, "Example App", getpass.getuser())

            def parents(self) -> list[FakeProcess]:
                return [FakeProcess(4242, "Example App", getpass.getuser())]

        class ParentChainPsutil(FakePsutil):
            def Process(self, pid: int) -> FakeProcess:
                if pid == os.getpid():
                    return ParentChainProcess(pid)
                return super().Process(pid)

        parent = FakeProcess(4242, "Example App", getpass.getuser())
        fake = ParentChainPsutil({4242: parent})
        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([4242])
        self.assertFalse(parent.terminated)
        self.assertTrue(any("protected" in error for error in result.errors))

    # --- Control 4 (decisive): ancestry lookup failure --------------------

    def test_policy_fails_closed_when_ancestry_is_unreadable(self) -> None:
        def loader(pid: int) -> FakeProcess:
            if pid == os.getpid():
                return DeniedAncestryProcess(pid)
            raise KeyError(pid)

        policy = ProcessSafetyPolicy(
            current_pid_loader=os.getpid,
            process_loader=loader,
        )
        self.assertFalse(
            policy.can_manage(
                pid=999,
                name="Example App",
                username=getpass.getuser(),
                current_user=getpass.getuser(),
            )
        )

    def test_action_path_terminates_parent_when_ancestry_is_unreadable(
        self,
    ) -> None:
        parent_pid = 999
        parent = FakeProcess(parent_pid, "Example App", getpass.getuser())
        fake = DeniedAncestryPsutil({parent_pid: parent})
        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([parent_pid])
        self.assertTrue(parent.terminated)
        self.assertIn(parent_pid, result.stopped)

    # --- Control 2: protected names centralized and case-folded -----------

    def test_protected_name_is_case_folded_and_blocks(self) -> None:
        process = FakeProcess(50001, "SYSTEMD", getpass.getuser())
        fake = FakePsutil({50001: process})
        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([50001])
        self.assertFalse(process.terminated)
        self.assertTrue(any("protected" in error for error in result.errors))

    def test_protected_name_sets_are_the_single_centralized_frozenset(
        self,
    ) -> None:
        from maintenance.components import PROTECTED_PROCESS_NAMES
        from maintenance.scanner import SystemScanner

        self.assertIs(ProcessManager.PROTECTED_NAMES, PROTECTED_PROCESS_NAMES)
        self.assertIs(SystemScanner.PROTECTED_PROCESS_NAMES, PROTECTED_PROCESS_NAMES)
        self.assertIs(ProcessSafetyPolicy.PROTECTED_NAMES, PROTECTED_PROCESS_NAMES)

    # --- Control 3: Windows domain prefixes normalized --------------------

    def test_domain_prefixed_same_user_is_allowed(self) -> None:
        current = getpass.getuser()
        process = FakeProcess(50001, "Example App", f"WORKGROUP\\{current}")
        fake = FakePsutil({50001: process})
        with patch("maintenance.actions.psutil", fake):
            ProcessManager().request_quit([50001])
        self.assertTrue(process.terminated)

    def test_foreign_user_is_never_terminated(self) -> None:
        process = FakeProcess(50001, "Example App", "someone_else")
        fake = FakePsutil({50001: process})
        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([50001])
        self.assertFalse(process.terminated)
        self.assertTrue(any("protected" in error for error in result.errors))

    # --- Control 5: create-time checks defend against PID reuse -----------

    def test_create_time_mismatch_blocks_termination(self) -> None:
        process = FakeProcess(
            50001, "Example App", getpass.getuser(), create_time=2000.0
        )
        fake = FakePsutil({50001: process})
        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([50001], {50001: 1000.0})
        self.assertFalse(process.terminated)
        self.assertTrue(any("changed" in error for error in result.errors))

    def test_matching_create_time_allows_termination(self) -> None:
        process = FakeProcess(
            50001, "Example App", getpass.getuser(), create_time=1000.0
        )
        fake = FakePsutil({50001: process})
        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([50001], {50001: 1000.0})
        self.assertTrue(process.terminated)
        self.assertIn(50001, result.stopped)

    def test_typed_request_requires_create_time(self) -> None:
        with self.assertRaises(ValueError):
            ProcessTerminationRequest(
                target_node_id=NodeId("local"),
                processes=(ProcessRef(NodeId("local"), 50001, None),),
                action=ProcessActionKind.REQUEST_QUIT,
            )

    # --- Control 6: access-denied on identity reads blocks the action -----

    def test_access_denied_on_name_read_blocks_termination(self) -> None:
        process = FakeProcess(50001, "Example App", getpass.getuser(), deny_name=True)
        fake = FakePsutil({50001: process})
        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([50001])
        self.assertFalse(process.terminated)
        self.assertTrue(any("50001" in error for error in result.errors))

    def test_access_denied_on_username_read_blocks_termination(self) -> None:
        process = FakeProcess(
            50001, "Example App", getpass.getuser(), deny_username=True
        )
        fake = FakePsutil({50001: process})
        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([50001])
        self.assertFalse(process.terminated)
        self.assertTrue(any("50001" in error for error in result.errors))

    # --- Control 7: force-quit children are rechecked ---------------------

    def test_force_quit_rechecks_children_before_killing(self) -> None:
        parent = FakeProcess(50001, "Example App", getpass.getuser())
        protected_child = FakeProcess(50002, "systemd", getpass.getuser())
        fake = FakePsutil(
            {50001: parent, 50002: protected_child},
        )
        parent._children = [protected_child]
        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().force_quit([50001])
        self.assertTrue(parent.killed)
        self.assertFalse(protected_child.killed)
        self.assertTrue(any("protected" in error for error in result.errors))

    def test_force_quit_child_create_time_change_blocks_child(self) -> None:
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
            result = ProcessManager().force_quit([50001], {50001: 1000.0})
        self.assertFalse(child.killed)
        self.assertTrue(parent.killed)
        self.assertTrue(any("changed" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
