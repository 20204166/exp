"""Host-runnable regression tests for platform-specific production branches.

Each test targets a branch that executes differently on Windows versus other platforms
but can be exercised on any host via environment manipulation, monkeypatching, or
injected exceptions.

Evidence label: UNIT / EMULATED WINDOWS BRANCH
These tests DO NOT constitute physical Windows evidence.
"""

from __future__ import annotations

import logging
import os
import tempfile
import typing
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from maintenance.persistence import fsync_directory
from maintenance.remote_security import _chmod_best_effort
from maintenance.remote_support.protocol import RemoteTransportError
from maintenance.remote_support.transport import SocketRemoteTransport


class ChmodBestEffortTests(unittest.TestCase):
    """_chmod_best_effort must silently absorb OSError.

    On Windows, os.chmod() does not fully map to NTFS ACLs and may raise
    PermissionError (a subclass of OSError).  The helper must not propagate.
    """

    def test_chmod_best_effort_silences_oserror(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "maintenance.remote_security.os.chmod",
                side_effect=OSError("Windows ACL error"),
            ),
        ):
            path = Path(directory) / "testfile"
            path.write_bytes(b"content")
            # Must not raise even though os.chmod raises.
            _chmod_best_effort(path, 0o600)

    def test_chmod_best_effort_applies_mode_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "testfile"
            path.write_bytes(b"content")
            _chmod_best_effort(path, 0o600)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class FsyncDirectoryWindowsBranchTests(unittest.TestCase):
    """fsync_directory must be a no-op when os.O_DIRECTORY is absent.

    On Windows, os.O_DIRECTORY does not exist.  The guard at persistence.py:94
    must short-circuit before touching the filesystem.
    """

    def test_fsync_directory_is_noop_when_o_directory_absent(self) -> None:
        # Build a spec list that excludes O_DIRECTORY, emulating Windows os module.
        os_spec = [attr for attr in dir(os) if attr != "O_DIRECTORY"]
        mock_os = MagicMock(spec=os_spec)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("maintenance.persistence.os", mock_os),
        ):
            # No exception, no os.open / os.fsync calls.
            fsync_directory(
                Path(directory) / "file.json",
                logger=logging.getLogger("test"),
                warning_template="fsync failed: %s",
            )

        mock_os.open.assert_not_called()
        mock_os.fsync.assert_not_called()

    def test_fsync_directory_runs_normally_when_o_directory_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "file.json"
            path.write_text("x", encoding="utf-8")
            # Should not raise; runs the real fsync path on Linux.
            fsync_directory(
                path,
                logger=logging.getLogger("test"),
                warning_template="fsync failed: %s",
            )


class CreationFlagsTests(unittest.TestCase):
    """_creationflags() must return 0 on POSIX and CREATE_NO_WINDOW on Windows.

    The branch `if os.name == "nt"` is not exercised on Linux by default.
    Monkeypatching os.name lets us prove both paths without a real Windows host.
    """

    def test_creationflags_returns_zero_on_posix(self) -> None:
        from maintenance.scanner_support import temperature_platform

        with patch.object(temperature_platform.os, "name", "posix"):
            self.assertEqual(temperature_platform._creationflags(), 0)

    def test_creationflags_returns_create_no_window_on_nt(self) -> None:
        from maintenance.scanner_support import temperature_platform

        expected_flag = 0x08000000  # subprocess.CREATE_NO_WINDOW value
        with (
            patch.object(temperature_platform.os, "name", "nt"),
            patch.object(
                temperature_platform.subprocess,
                "CREATE_NO_WINDOW",
                expected_flag,
                create=True,
            ),
        ):
            self.assertEqual(temperature_platform._creationflags(), expected_flag)

    def test_creationflags_falls_back_to_zero_when_attribute_absent_on_nt(
        self,
    ) -> None:
        """getattr fallback: if somehow CREATE_NO_WINDOW is not on subprocess, returns 0."""
        from maintenance.scanner_support import temperature_platform

        mock_subprocess = MagicMock(spec=[])  # no attributes
        with (
            patch.object(temperature_platform.os, "name", "nt"),
            patch.object(temperature_platform, "subprocess", mock_subprocess),
        ):
            self.assertEqual(temperature_platform._creationflags(), 0)


class WindowsSocketErrorMappingTests(unittest.TestCase):
    """OSError from socket layer must become RemoteTransportError.

    On Windows, socket errors arrive as OSError subclasses with .winerror
    attributes (e.g. 10061 WSAECONNREFUSED).  Python maps them to the same
    OSError hierarchy as POSIX.  This test verifies the transport catches the
    parent class and wraps it — no Windows runtime required.
    """

    def _make_transport(self) -> SocketRemoteTransport:
        return SocketRemoteTransport(
            "127.0.0.1",
            9,  # discard port — connection will be intercepted by the patch
            timeout=1.0,
        )

    def _oserror_with_winerror(self, winerror: int, message: str) -> OSError:
        error = OSError(message)
        error.winerror = winerror  # type: ignore[attr-defined]
        return error

    def test_connection_refused_oserror_becomes_transport_error(self) -> None:
        with patch(
            "maintenance.remote_support.transport.socket_module.create_connection",
            side_effect=ConnectionRefusedError("connection refused"),
        ), self.assertRaises(RemoteTransportError):
            self._make_transport().request("{}")

    def test_timeout_oserror_becomes_transport_error(self) -> None:
        with patch(
            "maintenance.remote_support.transport.socket_module.create_connection",
            side_effect=TimeoutError("connection timed out"),
        ), self.assertRaises(RemoteTransportError):
            self._make_transport().request("{}")

    def test_windows_wsaeconnrefused_10061_becomes_transport_error(self) -> None:
        """WinError 10061 is the Windows analogue of ECONNREFUSED."""
        error = self._oserror_with_winerror(10061, "Connection refused")
        with patch(
            "maintenance.remote_support.transport.socket_module.create_connection",
            side_effect=error,
        ), self.assertRaises(RemoteTransportError):
            self._make_transport().request("{}")

    def test_windows_wsaetimedout_10060_becomes_transport_error(self) -> None:
        """WinError 10060 is the Windows analogue of ETIMEDOUT."""
        error = self._oserror_with_winerror(10060, "Connection timed out")
        with patch(
            "maintenance.remote_support.transport.socket_module.create_connection",
            side_effect=error,
        ), self.assertRaises(RemoteTransportError):
            self._make_transport().request("{}")

    def test_windows_wsaeconnreset_10054_becomes_transport_error(self) -> None:
        """WinError 10054 is the Windows analogue of ECONNRESET."""
        error = self._oserror_with_winerror(10054, "Connection reset by peer")
        with patch(
            "maintenance.remote_support.transport.socket_module.create_connection",
            side_effect=error,
        ), self.assertRaises(RemoteTransportError):
            self._make_transport().request("{}")

    def test_windows_wsaeaccess_10013_becomes_transport_error(self) -> None:
        """WinError 10013 maps to EACCES — firewall/permission block."""
        error = self._oserror_with_winerror(10013, "Permission denied")
        with patch(
            "maintenance.remote_support.transport.socket_module.create_connection",
            side_effect=error,
        ), self.assertRaises(RemoteTransportError):
            self._make_transport().request("{}")


class AppDataConfigPathTests(unittest.TestCase):
    """Windows APPDATA path derivation works correctly.

    This exercises the `if system == "Windows"` branch in preferences.py
    using synthetic environment values — no real Windows paths required.
    """

    def test_windows_config_path_uses_appdata_env(self) -> None:
        from pathlib import PureWindowsPath

        from maintenance.preferences import default_preferences_path

        path = default_preferences_path(
            environment={"APPDATA": r"C:\Users\TestUser\AppData\Roaming"},
            home=Path("C:/Users/TestUser"),
            platform_name="Windows",
        )
        self.assertEqual(
            PureWindowsPath(path),
            PureWindowsPath(
                r"C:\Users\TestUser\AppData\Roaming\system-analyzer\preferences.json"
            ),
        )

    def test_windows_config_path_falls_back_to_roaming_subdir(self) -> None:
        from pathlib import PureWindowsPath

        from maintenance.preferences import default_preferences_path

        path = default_preferences_path(
            environment={},
            home=Path("C:/Users/TestUser"),
            platform_name="Windows",
        )
        self.assertEqual(
            PureWindowsPath(path),
            PureWindowsPath(
                "C:/Users/TestUser/AppData/Roaming/system-analyzer/preferences.json"
            ),
        )

    def test_isolated_appdata_env_var_does_not_bleed_into_real_env(self) -> None:
        original = os.environ.get("APPDATA")
        from maintenance.preferences import default_preferences_path

        # Providing a synthetic env dict does not touch os.environ.
        default_preferences_path(
            environment={"APPDATA": r"C:\Temp\sa-test"},
            home=Path("C:/Temp"),
            platform_name="Windows",
        )
        self.assertEqual(os.environ.get("APPDATA"), original)


class WindowsInstanceLockBranchTests(unittest.TestCase):
    """UNIT / EMULATED WINDOWS BRANCH: instance lock msvcrt path on Linux.

    The single-instance lock has a POSIX path (fcntl.flock) and a Windows
    path (msvcrt.locking).  These tests prove that the Windows branch is
    correctly isolated behind the sys.platform == "win32" guard and that
    msvcrt.locking is called with the expected arguments when that branch
    executes.
    """

    _LK_NBLCK = 2  # msvcrt.LK_NBLCK constant value

    def _msvcrt_stub(self, locking_raises: BaseException | None = None) -> MagicMock:
        stub = MagicMock()
        stub.LK_NBLCK = self._LK_NBLCK
        if locking_raises is not None:
            stub.locking.side_effect = locking_raises
        return stub

    def test_windows_branch_calls_msvcrt_locking_with_correct_args(self) -> None:
        from maintenance import instance_lock

        stub = self._msvcrt_stub()
        with (
            tempfile.TemporaryDirectory() as d,
            patch("sys.platform", "win32"),
            patch.dict("sys.modules", {"msvcrt": stub}),
        ):
            lock = instance_lock.acquire(Path(d) / "test.lock")

        self.assertIsNotNone(lock)
        stub.locking.assert_called_once()
        _, args, _ = stub.locking.mock_calls[0]
        self.assertEqual(args[1], self._LK_NBLCK)  # mode
        self.assertEqual(args[2], 1)  # nbytes
        if lock:
            lock.release()

    def test_windows_branch_returns_none_when_already_locked(self) -> None:
        from maintenance import instance_lock

        stub = self._msvcrt_stub(locking_raises=OSError("already locked"))
        with (
            tempfile.TemporaryDirectory() as d,
            patch("sys.platform", "win32"),
            patch.dict("sys.modules", {"msvcrt": stub}),
        ):
            result = instance_lock.acquire(Path(d) / "test.lock")

        self.assertIsNone(result)

    def test_windows_lock_guard_does_not_call_fcntl(self) -> None:
        from maintenance import instance_lock

        stub = self._msvcrt_stub()
        fcntl_stub = MagicMock()
        with (
            tempfile.TemporaryDirectory() as d,
            patch("sys.platform", "win32"),
            patch.dict("sys.modules", {"msvcrt": stub, "fcntl": fcntl_stub}),
        ):
            lock = instance_lock.acquire(Path(d) / "test.lock")

        fcntl_stub.flock.assert_not_called()
        if lock:
            lock.release()


class NoFirewallMutationTests(unittest.TestCase):
    """AppWindow/RemoteService startup must never invoke privileged firewall tools."""

    _FIREWALL_LITERALS: typing.ClassVar[list[str]] = [
        "sudo",
        "ufw",
        "iptables",
        "nft ",
        "netsh",
    ]

    def test_window_discovery_contains_no_firewall_literals(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("maintenance/ui/window_discovery.py").read_text()
        tree = ast.parse(src)
        literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        for pattern in self._FIREWALL_LITERALS:
            with self.subTest(pattern=pattern):
                matches = [s for s in literals if pattern in s]
                self.assertEqual(
                    matches, [],
                    f"window_discovery.py must not contain firewall literal '{pattern}': {matches}",
                )

    def test_remote_support_server_does_not_import_subprocess(self) -> None:
        import ast
        import pathlib
        src = pathlib.Path("maintenance/remote_support/server.py").read_text()
        tree = ast.parse(src)
        imported = [
            node.names[0].name if isinstance(node, ast.Import) else node.module
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        self.assertNotIn(
            "subprocess", imported,
            "remote_support/server.py must not import subprocess",
        )


class LanAddressPreferenceTests(unittest.TestCase):
    """_lan_address_key must rank physical LAN addresses before VPN tunnel IPs."""

    def _key(self, addr: str) -> int:
        from maintenance.ui.window_discovery import _lan_address_key
        return _lan_address_key(addr)

    def test_192_168_ranks_best(self) -> None:
        self.assertEqual(self._key("192.168.55.107"), 0)

    def test_172_16_ranks_second(self) -> None:
        self.assertEqual(self._key("172.16.0.1"), 1)

    def test_172_31_ranks_second(self) -> None:
        self.assertEqual(self._key("172.31.255.1"), 1)

    def test_10_ranks_third(self) -> None:
        self.assertEqual(self._key("10.2.0.2"), 2)

    def test_shared_address_space_ranks_fourth(self) -> None:
        # 100.64/10 covers Tailscale and other VPN overlay addresses
        self.assertEqual(self._key("100.85.0.1"), 3)

    def test_public_address_ranks_last(self) -> None:
        self.assertEqual(self._key("8.8.8.8"), 4)

    def test_lan_address_wins_over_vpn_when_mixed(self) -> None:
        addresses = ["10.2.0.2", "100.85.0.1", "192.168.55.107"]
        from maintenance.ui.window_discovery import _lan_address_key
        chosen = min(addresses, key=_lan_address_key)
        self.assertEqual(chosen, "192.168.55.107")

    def test_window_discovery_uses_lan_address_key_not_index_zero(self) -> None:
        import pathlib
        src = pathlib.Path("maintenance/ui/window_discovery.py").read_text()
        self.assertIn("_lan_address_key", src, "_lan_address_key must be used in window_discovery.py")
        self.assertNotIn("addresses[0]", src, "addresses[0] must not appear — use min(..., key=_lan_address_key)")


if __name__ == "__main__":
    unittest.main()
