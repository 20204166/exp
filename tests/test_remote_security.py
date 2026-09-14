"""TLS material and pinned peer transport tests."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from maintenance.nodes import NodeId, NodePermission
from maintenance.remote import (
    AuthenticatedNodeProvider,
    CapabilityElevationRequest,
    RemoteAuthError,
    RemoteSocketServer,
    TLSRemoteTransport,
)
from maintenance.remote_security import ensure_tls_material, server_context
from maintenance.remote_support.server import _handle_elevation_request
from tests.test_remote_contract import SECRET, _service


class RemoteSecurityTests(unittest.TestCase):
    def test_elevation_request_allows_only_explicit_target_approval(self) -> None:
        request = CapabilityElevationRequest(
            caller_node_id=NodeId("caller"),
            identity_fingerprint="caller-id",
            transport_fingerprint="caller-tls",
            current_secret="a" * 64,
            proposed_secret="b" * 64,
            permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
        )
        self.assertEqual(
            request.permissions, frozenset({NodePermission.PROCESS_TERMINATION})
        )

    def test_elevation_request_rejects_empty_permissions(self) -> None:
        with self.assertRaises(ValueError):
            CapabilityElevationRequest(
                caller_node_id=NodeId("caller"),
                identity_fingerprint="caller-id",
                transport_fingerprint="caller-tls",
                current_secret="a" * 64,
                proposed_secret="b" * 64,
                permissions=frozenset(),
            )

    def test_elevation_handler_requires_explicit_approval(self) -> None:
        raw = {
            "op": "elevation_request",
            "caller_node_id": "caller",
            "identity_fingerprint": "caller-id",
            "transport_fingerprint": "caller-tls",
            "current_secret": "a" * 64,
            "secret": "b" * 64,
            "permissions": [NodePermission.CLEANUP.value],
        }
        denied = _handle_elevation_request(raw, lambda _request: False)
        approved = _handle_elevation_request(raw, lambda _request: True)
        self.assertFalse(json.loads(denied)["approved"])
        self.assertTrue(json.loads(approved)["approved"])

    def test_elevation_request_carries_the_existing_pairing_credential(self) -> None:
        request = CapabilityElevationRequest(
            caller_node_id=NodeId("caller"),
            identity_fingerprint="caller-id",
            transport_fingerprint="caller-tls",
            current_secret="a" * 64,
            proposed_secret="b" * 64,
            permissions=frozenset({NodePermission.CLEANUP}),
        )
        self.assertNotEqual(request.current_secret, request.proposed_secret)

    def test_tls_generation_forwards_no_window_creation_flag(self) -> None:
        observed: dict[str, object] = {}
        real_run = subprocess.run

        def capture_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            observed.update(kwargs)
            return real_run(*args, **kwargs)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("maintenance.remote_security.subprocess.run", capture_run),
        ):
            ensure_tls_material(Path(directory), "peer")

        expected = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        self.assertEqual(observed.get("creationflags"), expected)

    def test_material_is_reused_with_stable_fingerprint_and_private_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            first = ensure_tls_material(path, "peer")
            second = ensure_tls_material(path, "peer")

            self.assertEqual(first, second)
            self.assertEqual(first.private_key.stat().st_mode & 0o777, 0o600)

    def test_pinned_tls_socket_completes_authenticated_hello(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            material = ensure_tls_material(Path(directory), "peer")
            server = RemoteSocketServer(
                _service(),
                host="127.0.0.1",
                ssl_context=server_context(material),
            )
            server.start()
            self.addCleanup(server.stop)
            port = server.bound_port
            assert port is not None
            provider = AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret=SECRET,
                transport=TLSRemoteTransport(
                    "127.0.0.1",
                    port,
                    expected_fingerprint=material.fingerprint,
                ),
            )

            self.assertTrue(provider.hello()["ok"])

    def test_wrong_pinned_certificate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            material = ensure_tls_material(Path(directory), "peer")
            server = RemoteSocketServer(
                _service(),
                host="127.0.0.1",
                ssl_context=server_context(material),
            )
            server.start()
            self.addCleanup(server.stop)
            port = server.bound_port
            assert port is not None
            provider = AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret=SECRET,
                transport=TLSRemoteTransport(
                    "127.0.0.1", port, expected_fingerprint="0" * 79
                ),
            )

            with self.assertRaises(RemoteAuthError):
                provider.hello()

    def test_pairing_request_requires_target_handler_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            material = ensure_tls_material(Path(directory), "peer")
            server = RemoteSocketServer(
                _service(),
                host="127.0.0.1",
                ssl_context=server_context(material),
                pairing_handler=lambda _request: True,
            )
            server.start()
            self.addCleanup(server.stop)
            port = server.bound_port
            assert port is not None
            transport = TLSRemoteTransport(
                "127.0.0.1",
                port,
                expected_fingerprint=material.fingerprint,
            )

            self.assertTrue(
                AuthenticatedNodeProvider.request_pairing(
                    transport=transport,
                    caller_node_id=NodeId("caller"),
                    identity_fingerprint="caller-id",
                    transport_fingerprint="caller-tls",
                    proposed_secret="b" * 64,
                    permissions=frozenset({NodePermission.DASHBOARD_READ}),
                )
            )

    def test_pairing_request_rejects_destructive_permissions(self) -> None:
        with self.assertRaises(ValueError):
            from maintenance.remote import PairingRequest

            PairingRequest(
                caller_node_id=NodeId("caller"),
                identity_fingerprint="caller-id",
                transport_fingerprint="caller-tls",
                proposed_secret="b" * 64,
                permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
            )


if __name__ == "__main__":
    unittest.main()
