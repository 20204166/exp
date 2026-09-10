"""TLS material and pinned peer transport tests."""

import tempfile
import unittest
from pathlib import Path

from maintenance.nodes import NodeId, NodePermission
from maintenance.remote import (
    AuthenticatedNodeProvider,
    RemoteAuthError,
    RemoteSocketServer,
    TLSRemoteTransport,
)
from maintenance.remote_security import ensure_tls_material, server_context
from tests.test_remote_contract import SECRET, _service


class RemoteSecurityTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
