"""Agent 5 evidence test for SEC-20260912-001.

Per ``security_testing_pack.md`` ("Agent 5 evidence tests"), this file
resolves missing evidence; it does not replace any reviewer section. Two
gaps are decisive for the final per-concern decision:

1. **Escalation bound of the proven ancestry fail-open.** Opposer 2 and
   Opposer 3 independently proved that ``ProcessManager`` (lenient
   ``protected_process_pids`` snapshot) terminates a *same-user,
   non-protected-name* ancestor when ``parents()`` raises, while
   ``ProcessSafetyPolicy`` refuses the identical case. No existing test
   checks whether the remaining action-time gates (same-user, protected
   name, protected executable basename) still block a *foreign-user* or
   *protected* ancestor under unreadable ancestry. That bound decides
   vulnerability vs hardening opportunity.
2. **Opposer 1's planned-but-never-run scenarios (a) and (b).** Opposer 1's
   counter-test artifact was never created: token-less PID reuse by a
   protected-name replacement and by a foreign-user replacement. These
   tests fill that decisive gap without replacing the missing section.

Run:
python3 -m unittest docs/security_reviews/poc/SEC-20260912-001/agent5_ancestry_bounds.py -v
"""

import getpass
import os
import unittest
from unittest.mock import patch

from maintenance.actions import ProcessManager
from maintenance.components import ProcessSafetyPolicy
from tests.support.process_actions import ActionProcess as FakeProcess
from tests.support.process_actions import ActionPsutil as FakePsutil


class HiddenAncestryProcess(FakeProcess):
    """The app's own process, whose parent chain cannot be read."""

    def __init__(self, pid: int) -> None:
        super().__init__(pid, "system-analyzer", getpass.getuser())

    def parents(self) -> list[FakeProcess]:
        raise FakePsutil.AccessDenied("ancestry hidden")


class HiddenAncestryPsutil(FakePsutil):
    """Fake psutil whose own-process ancestry lookup raises AccessDenied."""

    def Process(self, pid: int) -> FakeProcess:
        if pid == os.getpid():
            return HiddenAncestryProcess(pid)
        return super().Process(pid)


class AncestryFailOpenBoundTests(unittest.TestCase):
    """Bound the impact of the action-path ancestry fail-open."""

    def test_same_user_ancestor_is_terminated_when_ancestry_is_unreadable(
        self,
    ) -> None:
        """Independent reproduction: manager fails open, policy fails closed.

        The manager uses the lenient snapshot, so a same-user,
        non-protected-name ancestor becomes terminable when ancestry is
        unreadable; the fail-closed policy refuses the identical case.
        """

        ancestor_pid = 41000
        ancestor = FakeProcess(ancestor_pid, "bash", getpass.getuser())
        fake = HiddenAncestryPsutil({ancestor_pid: ancestor})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([ancestor_pid])

        self.assertTrue(ancestor.terminated)
        self.assertIn(ancestor_pid, result.stopped)

        policy = ProcessSafetyPolicy(
            current_pid_loader=os.getpid,
            process_loader=fake.Process,
        )
        self.assertFalse(
            policy.can_manage_process(
                pid=ancestor_pid,
                current_user=getpass.getuser(),
            )
        )

    def test_foreign_user_ancestor_is_blocked_when_ancestry_is_unreadable(
        self,
    ) -> None:
        """A foreign-user ancestor stays blocked despite the lost ancestry."""

        ancestor_pid = 41001
        ancestor = FakeProcess(ancestor_pid, "bash", "someone_else")
        fake = HiddenAncestryPsutil({ancestor_pid: ancestor})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([ancestor_pid])

        self.assertFalse(ancestor.terminated)
        self.assertNotIn(ancestor_pid, result.stopped)
        self.assertTrue(any("protected" in error for error in result.errors))

    def test_protected_name_ancestor_is_blocked_when_ancestry_is_unreadable(
        self,
    ) -> None:
        """A protected-name ancestor stays blocked despite the lost ancestry."""

        ancestor_pid = 41002
        ancestor = FakeProcess(ancestor_pid, "launchd", getpass.getuser())
        fake = HiddenAncestryPsutil({ancestor_pid: ancestor})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([ancestor_pid])

        self.assertFalse(ancestor.terminated)
        self.assertNotIn(ancestor_pid, result.stopped)
        self.assertTrue(any("protected" in error for error in result.errors))

    def test_protected_executable_ancestor_is_blocked_when_ancestry_is_unreadable(
        self,
    ) -> None:
        """A protected-executable ancestor stays blocked by the exe check."""

        ancestor_pid = 41003
        ancestor = FakeProcess(
            ancestor_pid,
            "weirdsessiond",
            getpass.getuser(),
            exe="/usr/lib/systemd/systemd",
        )
        fake = HiddenAncestryPsutil({ancestor_pid: ancestor})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([ancestor_pid])

        self.assertFalse(ancestor.terminated)
        self.assertNotIn(ancestor_pid, result.stopped)
        self.assertTrue(any("protected" in error for error in result.errors))


class TokenlessReuseBoundTests(unittest.TestCase):
    """Opposer 1's planned scenarios (a)/(b): token-less PID-reuse bounds.

    A direct API caller may omit ``expected_create_times`` (no reachable
    UI/remote caller does). These tests check the residual window: the
    action-time identity gates must still reject a reused PID whose
    replacement process is protected-name or foreign-user.
    """

    def test_reused_pid_with_protected_name_is_blocked_without_token(
        self,
    ) -> None:
        """Replacement process with a protected name is rejected at action time."""

        replacement = FakeProcess(42001, "systemd", getpass.getuser())
        fake = FakePsutil({42001: replacement})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([42001])

        self.assertFalse(replacement.terminated)
        self.assertNotIn(42001, result.stopped)
        self.assertTrue(any("protected" in error for error in result.errors))

    def test_reused_pid_with_foreign_user_is_blocked_without_token(
        self,
    ) -> None:
        """Replacement process owned by another user is rejected at action time."""

        replacement = FakeProcess(42002, "Example App", "someone_else")
        fake = FakePsutil({42002: replacement})

        with patch("maintenance.actions.psutil", fake):
            result = ProcessManager().request_quit([42002])

        self.assertFalse(replacement.terminated)
        self.assertNotIn(42002, result.stopped)
        self.assertTrue(any("protected" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
