"""Authenticated remote read contract tests (memory + loopback socket)."""

import json
import socket
import unittest
from datetime import datetime, timezone
from pathlib import Path

from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    FileCandidate,
    ProcessCandidate,
    ResourceSummary,
)
from maintenance.nodes import (
    NodeCapability,
    NodeId,
    NodeStatus,
)
from maintenance.remote import (
    DEFAULT_FRESHNESS_SECONDS,
    READ_CAPABILITIES,
    AuthenticatedNodeProvider,
    MemoryRemoteTransport,
    RemoteAuthError,
    RemoteAuthorizationError,
    RemoteExecutionError,
    RemoteProtocolError,
    RemoteService,
    RemoteSocketServer,
    RemoteTransportError,
    ReplayCache,
    SocketRemoteTransport,
    sign_request,
    sign_response,
    verify_request,
)

SECRET = "a" * 64


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


class FakeProvider:
    def dashboard_snapshot(
        self,
        cancel_event=None,
        progress_callback=None,
    ) -> DashboardSnapshot:
        return DashboardSnapshot(
            system_label="peer-host",
            scanned_at=_now(),
            resources=(
                ResourceSummary(
                    "cpu",
                    "CPU",
                    "10%",
                    "running",
                    10.0,
                    ("CPU: 10%",),
                    False,
                    False,
                    CapabilityState.SUPPORTED,
                ),
            ),
        )

    def component_summary(self, key, cancel_event=None) -> ResourceSummary:
        return ResourceSummary(
            key,
            key.upper(),
            "5%",
            "ok",
            5.0,
            (f"{key.upper()}: 5%",),
            False,
            False,
            CapabilityState.SUPPORTED,
        )

    def process_candidates(self, cancel_event=None) -> list[ProcessCandidate]:
        return [ProcessCandidate(1, "app", 100, 1.0, 2.0, "Active", "user", True, 1.5)]

    def storage_candidates(
        self,
        progress_callback=None,
        cancel_event=None,
    ) -> list[FileCandidate]:
        return [FileCandidate(Path("/tmp/x"), 10, _now(), "reason")]


def _service(
    provider=None,
    capabilities=READ_CAPABILITIES,
    secret=SECRET,
) -> RemoteService:
    return RemoteService(
        node_id=NodeId("peer"),
        display_name="Peer",
        hostname="peer-host",
        platform="Linux",
        status=NodeStatus.ONLINE,
        capabilities=frozenset(capabilities),
        provider=provider or FakeProvider(),
        secret=secret,
        app_version="1.2.4.0",
    )


def _client(service, secret=SECRET) -> AuthenticatedNodeProvider:
    return AuthenticatedNodeProvider(
        node_id=NodeId("peer"),
        secret=secret,
        transport=MemoryRemoteTransport(service),
    )


class SigningAndVerificationTests(unittest.TestCase):
    def test_signed_request_verifies(self) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
            timestamp=100.0,
            secret=SECRET,
        )
        request = verify_request(
            envelope,
            secret=SECRET,
            clock=lambda: 100.0,
            freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
            replay_cache=ReplayCache(),
        )
        self.assertEqual(request.op, "hello")

    def test_tampered_signature_is_rejected(self) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
            timestamp=100.0,
            secret=SECRET,
        )
        envelope["params"] = {"key": "evil"}
        with self.assertRaises(RemoteAuthError):
            verify_request(
                envelope,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
                replay_cache=ReplayCache(),
            )

    def test_wrong_secret_is_rejected(self) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
            timestamp=100.0,
            secret="b" * 64,
        )
        with self.assertRaises(RemoteAuthError):
            verify_request(
                envelope,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
                replay_cache=ReplayCache(),
            )

    def test_replayed_request_is_rejected(self) -> None:
        cache = ReplayCache(clock=lambda: 100.0)
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
            timestamp=100.0,
            secret=SECRET,
        )
        verify_request(
            envelope,
            secret=SECRET,
            clock=lambda: 100.0,
            freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
            replay_cache=cache,
        )
        with self.assertRaises(RemoteAuthError):
            verify_request(
                envelope,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
                replay_cache=cache,
            )

    def test_stale_timestamp_is_rejected(self) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
            timestamp=10.0,
            secret=SECRET,
        )
        with self.assertRaises(RemoteAuthError):
            verify_request(
                envelope,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
                replay_cache=ReplayCache(),
            )


class RemoteServiceRoundTripTests(unittest.TestCase):
    def test_hello_returns_ok(self) -> None:
        client = _client(_service())
        result = client.hello()
        self.assertTrue(result["ok"])
        self.assertEqual(result["node_id"], "peer")

    def test_dashboard_snapshot_round_trip(self) -> None:
        client = _client(_service())
        snapshot = client.dashboard_snapshot()
        self.assertEqual(snapshot.system_label, "peer-host")
        self.assertEqual(snapshot.get("cpu").value, "10%")

    def test_component_summary_round_trip(self) -> None:
        client = _client(_service())
        resource = client.component_summary("cpu")
        self.assertEqual(resource.title, "CPU")

    def test_process_candidates_round_trip(self) -> None:
        client = _client(_service())
        processes = client.process_candidates()
        self.assertEqual(len(processes), 1)
        self.assertEqual(processes[0].name, "app")

    def test_storage_candidates_round_trip(self) -> None:
        client = _client(_service())
        files = client.storage_candidates()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, Path("/tmp/x"))

    def test_wrong_client_secret_is_rejected(self) -> None:
        service = _service()
        client = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            secret="b" * 64,
            transport=MemoryRemoteTransport(service),
        )
        with self.assertRaises(RemoteAuthError):
            client.hello()

    def test_response_from_wrong_node_is_rejected(self) -> None:
        class WrongNodeTransport:
            def request(self, envelope_text: str) -> str:
                envelope = json.loads(envelope_text)
                return json.dumps(
                    sign_response(
                        node_id="other",
                        request_id=envelope["request_id"],
                        status="ok",
                        payload={"ok": True},
                        timestamp=100.0,
                        secret=SECRET,
                    )
                )

        client = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            secret=SECRET,
            transport=WrongNodeTransport(),
        )
        with self.assertRaises(RemoteAuthError):
            client.hello()

    def test_unauthorized_operation_is_rejected(self) -> None:
        service = _service(capabilities=frozenset({NodeCapability.DASHBOARD_READ}))
        client = _client(service)
        with self.assertRaises(RemoteAuthorizationError):
            client.component_summary("cpu")

    def test_unknown_operation_is_rejected(self) -> None:
        service = _service()
        with self.assertRaises(RemoteProtocolError):
            service.handle('{"v": "1"}')

    def test_execution_failure_returns_signed_error(self) -> None:
        class BoomProvider(FakeProvider):
            def process_candidates(self, cancel_event=None):
                raise RuntimeError("boom")

        service = _service(provider=BoomProvider())
        client = _client(service)
        with self.assertRaises(RemoteExecutionError):
            client.process_candidates()

    def test_read_only_noop_helpers(self) -> None:
        client = _client(_service())
        client.reset_component_sample("cpu")
        client.stop_background_workers()

    def test_cancelled_request_raises_before_send(self) -> None:
        import threading

        client = _client(_service())
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(RemoteExecutionError):
            client.dashboard_snapshot(cancel_event=cancel)


class SocketTransportTests(unittest.TestCase):
    def test_loopback_socket_round_trip(self) -> None:
        service = _service()
        server = RemoteSocketServer(service)
        server.start()
        try:
            port = server.bound_port
            self.assertIsNotNone(port)
            assert port is not None
            client = AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret=SECRET,
                transport=SocketRemoteTransport("127.0.0.1", port, timeout=10),
            )
            result = client.hello()
            self.assertTrue(result["ok"])
            snapshot = client.dashboard_snapshot()
            self.assertEqual(snapshot.get("cpu").value, "10%")
        finally:
            server.stop()

    def test_connection_refused_maps_to_transport_error(self) -> None:
        from maintenance.remote import RemoteTransportError

        client = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            secret=SECRET,
            transport=SocketRemoteTransport("127.0.0.1", _free_port(), timeout=2),
        )
        with self.assertRaises(RemoteTransportError):
            client.hello()

    def test_wrong_secret_over_socket_is_rejected(self) -> None:
        service = _service()
        server = RemoteSocketServer(service)
        server.start()
        try:
            port = server.bound_port
            assert port is not None
            client = AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret="b" * 64,
                transport=SocketRemoteTransport("127.0.0.1", port, timeout=10),
            )
            with self.assertRaises((RemoteAuthError, RemoteTransportError)):
                client.hello()
        finally:
            server.stop()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    unittest.main()
