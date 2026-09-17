"""Tests for RemoteSocketServer port contract and PEER_SERVICE_DEFAULT_PORT."""

import unittest
from typing import Any


class PeerServicePortTests(unittest.TestCase):
    def test_default_port_constant_exists(self) -> None:
        from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT
        self.assertIsInstance(PEER_SERVICE_DEFAULT_PORT, int)
        self.assertGreater(PEER_SERVICE_DEFAULT_PORT, 1023)
        self.assertLess(PEER_SERVICE_DEFAULT_PORT, 32768)  # below Linux ephemeral range

    def test_default_port_re_exported_from_remote(self) -> None:
        from maintenance import remote
        self.assertTrue(hasattr(remote, "PEER_SERVICE_DEFAULT_PORT"))
        from maintenance.remote import PEER_SERVICE_DEFAULT_PORT
        from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT as src
        self.assertEqual(PEER_SERVICE_DEFAULT_PORT, src)

    def test_default_port_value(self) -> None:
        from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT
        self.assertEqual(PEER_SERVICE_DEFAULT_PORT, 27321)


class RemoteSocketServerPreferredPortTests(unittest.TestCase):
    def _make_server(self, *, preferred_port: int = 0) -> "Any":
        from unittest.mock import MagicMock

        from maintenance.remote_support.server import RemoteSocketServer
        service = MagicMock()
        return RemoteSocketServer(service, host="127.0.0.1", preferred_port=preferred_port)

    def test_preferred_port_honored_is_none_before_start(self) -> None:
        server = self._make_server(preferred_port=27321)
        self.assertIsNone(server.preferred_port_honored)

    def test_server_binds_preferred_port_when_free(self) -> None:
        import socket

        from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", PEER_SERVICE_DEFAULT_PORT))
            except OSError:
                self.skipTest(f"port {PEER_SERVICE_DEFAULT_PORT} already in use")
        server = self._make_server(preferred_port=PEER_SERVICE_DEFAULT_PORT)
        try:
            server.start()
            self.assertEqual(server.bound_port, PEER_SERVICE_DEFAULT_PORT)
            self.assertTrue(server.preferred_port_honored)
        finally:
            server.stop()

    def test_server_falls_back_to_ephemeral_when_preferred_busy(self) -> None:
        import socket
        from unittest.mock import MagicMock

        from maintenance.remote_support.server import (
            PEER_SERVICE_DEFAULT_PORT,
            RemoteSocketServer,
        )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                blocker.bind(("127.0.0.1", PEER_SERVICE_DEFAULT_PORT))
                blocker.listen(1)
            except OSError:
                self.skipTest("could not acquire port 27321 as blocker")
            service = MagicMock()
            server = RemoteSocketServer(service, host="127.0.0.1", preferred_port=PEER_SERVICE_DEFAULT_PORT)
            try:
                server.start()
                self.assertIsNotNone(server.bound_port)
                self.assertNotEqual(server.bound_port, PEER_SERVICE_DEFAULT_PORT)
                self.assertFalse(server.preferred_port_honored)
            finally:
                server.stop()

    def test_no_preferred_port_uses_ephemeral(self) -> None:
        server = self._make_server(preferred_port=0)
        try:
            server.start()
            self.assertIsNotNone(server.bound_port)
            self.assertIsNone(server.preferred_port_honored)
        finally:
            server.stop()


class StartPeerListenerPortTests(unittest.TestCase):
    def test_start_peer_listener_passes_preferred_port(self) -> None:
        import inspect

        from maintenance.ui import window_discovery
        src = inspect.getsource(window_discovery.start_peer_listener)
        self.assertIn("PEER_SERVICE_DEFAULT_PORT", src,
            "start_peer_listener must pass PEER_SERVICE_DEFAULT_PORT as preferred_port")
        self.assertIn("preferred_port", src,
            "start_peer_listener must use preferred_port keyword")


class ListenerEndpointDiagnosticsTests(unittest.TestCase):
    def test_listener_endpoint_includes_preferred_honored(self) -> None:
        import inspect

        from maintenance.ui import window_discovery
        src = inspect.getsource(window_discovery.listener_endpoint)
        self.assertIn("preferred_port_honored", src,
            "listener_endpoint must include preferred_port_honored in its return value")

    def test_listener_endpoint_not_connectable_when_no_server(self) -> None:
        from maintenance.ui.window_discovery import listener_endpoint
        controller = type("C", (), {"__dict__": {}})()
        result = listener_endpoint(controller)
        self.assertFalse(result[0])
        self.assertIsNone(result[1])


class PortContractIntegrityTests(unittest.TestCase):
    """bound_port == preferred when honored; port constant not duplicated as literal."""

    def test_bound_port_equals_preferred_when_honored(self) -> None:
        import socket
        from unittest.mock import MagicMock

        from maintenance.remote_support.server import (
            PEER_SERVICE_DEFAULT_PORT,
            RemoteSocketServer,
        )

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", PEER_SERVICE_DEFAULT_PORT))
            except OSError:
                self.skipTest(f"port {PEER_SERVICE_DEFAULT_PORT} already in use")

        service = MagicMock()
        server = RemoteSocketServer(
            service, host="127.0.0.1", preferred_port=PEER_SERVICE_DEFAULT_PORT
        )
        try:
            server.start()
            self.assertEqual(server.bound_port, PEER_SERVICE_DEFAULT_PORT)
            self.assertTrue(server.preferred_port_honored)
        finally:
            server.stop()

    def test_no_duplicate_port_literal_outside_canonical_owner(self) -> None:
        import pathlib
        py_files = list(pathlib.Path("maintenance").rglob("*.py"))
        py_files += list(pathlib.Path("tests").rglob("*.py"))
        if pathlib.Path("window.py").exists():
            py_files.append(pathlib.Path("window.py"))
        matches = [
            str(f) for f in py_files
            if "27321" in f.read_text()
            and "remote_support/server.py" not in str(f)
            and "test_remote_server.py" not in str(f)
        ]
        self.assertEqual(
            matches, [],
            f"Literal 27321 found outside canonical owner: {matches}. "
            "Import PEER_SERVICE_DEFAULT_PORT instead.",
        )

    def test_window_discovery_imports_constant_not_literal(self) -> None:
        import pathlib
        src = pathlib.Path("maintenance/ui/window_discovery.py").read_text()
        self.assertIn(
            "PEER_SERVICE_DEFAULT_PORT", src,
            "window_discovery.py must import PEER_SERVICE_DEFAULT_PORT",
        )
        self.assertNotIn(
            "27321", src,
            "window_discovery.py must not contain the literal 27321 — import the constant",
        )
