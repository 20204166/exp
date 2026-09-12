"""Agent 5 evidence test for SEC-20260912-002 (Mode D).

Independently re-verifies the decisive controls that decide this review:
the TLS pinning model (CERT_NONE client context + fingerprint pin), the
HMAC signature / freshness / replay boundary, and the discovery
lifecycle / node-identity fail-closed behavior. This test reconciles the
four opposing-agent counter-tests; it does not replace them.

Decisive controls and what a pass proves:

1. TLS context/pinning: the repo's ``client_context()`` deliberately uses
   CERT_NONE + check_hostname=False with a TLS 1.2 minimum, and server
   contexts also require TLS 1.2. A real loopback TLS handshake through
   the repo's own ``TLSRemoteTransport`` accepts the pinned fingerprint
   and rejects a wrong (MITM) fingerprint, and ``build_trusted_transport``
   refuses pin-less trusted records. Pass proves the pinning model
   authenticates the server end-to-end.
2. HMAC/replay: ``verify_request`` accepts a correctly signed fresh
   request and rejects a wrong-secret signature, an exact replay, and a
   timestamp outside the freshness window (past and future); a
   destructive operation replayed with a fresh nonce but a reused
   request_id is rejected before the process manager is reached a second
   time. Pass proves request authentication and replay protection hold.
3. Discovery lifecycle/identity: an attacker-controlled advertisement
   stays untrusted, capability-free, and non-selectable; a trusted peer's
   identity survives address/hostname changes while a fingerprint
   mismatch deselects and fails closed to the local node; a stopped
   discovery session drops late backend events. Pass proves the
   discovery trust boundary and identity stability hold.

What a fail would disprove: any of the above controls is broken or can
be bypassed, reopening the review's security question.

Run:
  PYTHONPATH=. .venv/bin/python \
    docs/security_reviews/poc/SEC-20260912-002/agent5_evidence.py -v
"""

from __future__ import annotations

import json
import ssl
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from maintenance.cluster import trusted_node_record
from maintenance.components.network_discovery import (
    SERVICE_TYPE,
    DiscoveryAdvertisement,
    NetworkDiscovery,
)
from maintenance.models import ProcessActionResult
from maintenance.nodes import (
    LOCAL_NODE_ID,
    DiscoveredNodeCandidate,
    NodeCapability,
    NodeId,
    NodeIdentityStatus,
    NodePermission,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
)
from maintenance.remote import (
    DEFAULT_FRESHNESS_SECONDS,
    AuthenticatedNodeProvider,
    RemoteAuthError,
    RemoteService,
    RemoteSocketServer,
    ReplayCache,
    TLSRemoteTransport,
    build_trusted_transport,
    sign_request,
    verify_request,
)
from maintenance.remote_security import (
    certificate_fingerprint,
    client_context,
    ensure_tls_material,
    server_context,
)
from tests.support.discovery import FakeBackend
from tests.support.nodes import make_local_context

SECRET = "a" * 64
OTHER_SECRET = "b" * 64


class TlsContextPinningEvidenceTests(unittest.TestCase):
    """The CERT_NONE + pin model must authenticate the server end-to-end."""

    def test_contexts_use_tls12_and_client_pins_by_fingerprint(self) -> None:
        client = client_context()
        self.assertFalse(client.check_hostname)
        self.assertEqual(client.verify_mode, ssl.CERT_NONE)
        self.assertEqual(client.minimum_version, ssl.TLSVersion.TLSv1_2)
        with tempfile.TemporaryDirectory() as directory:
            material = ensure_tls_material(Path(directory), "peer")
            server = server_context(material)
            self.assertEqual(server.minimum_version, ssl.TLSVersion.TLSv1_2)
            der = ssl.PEM_cert_to_DER_cert(
                material.certificate.read_text(encoding="ascii")
            )
            assert isinstance(der, bytes)
            self.assertEqual(material.fingerprint, certificate_fingerprint(der))

    def test_end_to_end_pinned_hello_over_repo_client_context_succeeds(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            material = ensure_tls_material(Path(directory), "peer")
            server = RemoteSocketServer(
                _hello_service(),
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
                    "127.0.0.1", port, expected_fingerprint=material.fingerprint
                ),
                clock=lambda: 100.0,
            )
            self.assertTrue(provider.hello()["ok"])

    def test_wrong_pinned_fingerprint_is_rejected(self) -> None:
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

    def test_build_trusted_transport_requires_pinned_fingerprint(self) -> None:
        record = trusted_node_record(
            node_id="manual-192.0.2.10:5000",
            display_name="Manual",
            hostname="192.0.2.10",
            host="192.0.2.10",
            port=5000,
        )
        with self.assertRaises(RemoteAuthError):
            build_trusted_transport(record)


class HmacReplayEvidenceTests(unittest.TestCase):
    """Requests must be HMAC-authenticated, fresh, and replay-proof."""

    def test_valid_signature_verifies_and_wrong_secret_is_rejected(
        self,
    ) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r-valid",
            nonce="n-valid",
            timestamp=100.0,
            secret=SECRET,
        )
        request = verify_request(
            envelope,
            secret=SECRET,
            clock=lambda: 100.0,
            freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
            replay_cache=ReplayCache(clock=lambda: 100.0),
        )
        self.assertEqual(request.request_id, "r-valid")

        forged = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r-forged",
            nonce="n-forged",
            timestamp=100.0,
            secret=OTHER_SECRET,
        )
        with self.assertRaises(RemoteAuthError):
            verify_request(
                forged,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
                replay_cache=ReplayCache(clock=lambda: 100.0),
            )

    def test_exact_replay_is_rejected(self) -> None:
        cache = ReplayCache(clock=lambda: 100.0)
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r-replay",
            nonce="n-replay",
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

    def test_timestamp_outside_freshness_window_is_rejected(self) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r-stale",
            nonce="n-stale",
            timestamp=100.0,
            secret=SECRET,
        )
        for label, now in (
            ("past", 100.0 + DEFAULT_FRESHNESS_SECONDS + 1.0),
            ("future", 100.0 - DEFAULT_FRESHNESS_SECONDS - 1.0),
        ):
            with self.subTest(label), self.assertRaises(RemoteAuthError):
                verify_request(
                    envelope,
                    secret=SECRET,
                    clock=lambda now=now: now,
                    freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
                    replay_cache=ReplayCache(clock=lambda now=now: now),
                )

    def test_destructive_replay_with_fresh_nonce_never_reaches_manager(
        self,
    ) -> None:
        manager = _RecordingProcessManager()
        service = RemoteService(
            node_id=NodeId("peer"),
            display_name="Peer",
            hostname="peer-host",
            platform="Linux",
            status=NodeStatus.ONLINE,
            capabilities=frozenset({NodeCapability.PROCESS_TERMINATION}),
            permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
            provider=_UnusedProvider(),
            process_manager=manager,
            secret=SECRET,
            clock=lambda: 100.0,
        )
        params = {
            "processes": [{"pid": 42, "create_time": 10.5}],
            "action": "request_quit",
        }
        first = sign_request(
            node_id="peer",
            op="process_request_quit",
            params=params,
            request_id="same-id",
            nonce="nonce-one",
            timestamp=100.0,
            secret=SECRET,
        )
        response = json.loads(service.handle(json.dumps(first)))
        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(manager.calls), 1)

        second = dict(first)
        second["nonce"] = "nonce-two"
        second["sig"] = sign_request(
            node_id="peer",
            op="process_request_quit",
            params=params,
            request_id="same-id",
            nonce="nonce-two",
            timestamp=100.0,
            secret=SECRET,
        )["sig"]
        with self.assertRaises(RemoteAuthError):
            service.handle(json.dumps(second))
        self.assertEqual(len(manager.calls), 1)


# __AGENT5_PART3__


def _candidate(
    stable_id: str = "peer-a",
    *,
    hostname: str = "peer.example",
    address: str = "192.0.2.10",
    identity_fingerprint: str | None = "peer-a-identity",
) -> DiscoveredNodeCandidate:
    return DiscoveredNodeCandidate(
        stable_id=stable_id,
        hostname=hostname,
        addresses=(address,),
        port=5000,
        service_name=f"{stable_id}.{SERVICE_TYPE}",
        app_version="1.0",
        protocol_version="1",
        platform="Linux",
        connectable=True,
        compatible=True,
        last_seen=100.0,
        identity_fingerprint=identity_fingerprint,
        transport_fingerprint="tls:fingerprint",
    )


class DiscoveryIdentityEvidenceTests(unittest.TestCase):
    def test_discovery_is_untrusted_and_non_selectable(self) -> None:
        registry = NodeRegistry(make_local_context())
        descriptor = registry.update_discovered(_candidate())

        self.assertIsNotNone(descriptor)
        assert descriptor is not None
        self.assertEqual(descriptor.trust, NodeTrustState.UNTRUSTED)
        self.assertEqual(descriptor.capabilities, frozenset())
        self.assertNotIn(descriptor, registry.selectable_descriptors())
        with self.assertRaises(ValueError):
            registry.select(NodeId("peer-a"))

    def test_identity_survives_address_change_and_mismatch_fails_closed(self) -> None:
        registry = NodeRegistry(make_local_context())
        registry.update_discovered(_candidate())
        registry.begin_pairing(NodeId("peer-a"))
        registry.promote_to_trusted(NodeId("peer-a"))
        context = registry.context(NodeId("peer-a"))
        context.provider = object()
        context.scheduler = object()
        registry.select(NodeId("peer-a"))

        renamed = replace(_candidate(hostname="renamed.example", address="192.0.2.11"))
        updated = registry.update_discovered(renamed)
        assert updated is not None
        self.assertEqual(updated.id, NodeId("peer-a"))
        self.assertEqual(updated.identity_status, NodeIdentityStatus.VERIFIED)
        self.assertEqual(registry.selected_id(), NodeId("peer-a"))

        mismatch = replace(renamed, identity_fingerprint="different")
        updated = registry.update_discovered(mismatch)
        assert updated is not None
        self.assertEqual(updated.identity_status, NodeIdentityStatus.MISMATCH)
        self.assertEqual(registry.selected_id(), NodeId(LOCAL_NODE_ID))
        self.assertNotIn(updated, registry.selectable_descriptors())

    def test_stop_drops_late_backend_events(self) -> None:
        events: list[tuple[str, Any]] = []
        backends: list[FakeBackend] = []

        def factory(listener: Any) -> FakeBackend:
            backend = FakeBackend(listener)
            backends.append(backend)
            return backend

        discovery = NetworkDiscovery(
            NodeId(LOCAL_NODE_ID),
            advertisement=DiscoveryAdvertisement(
                stable_id=LOCAL_NODE_ID,
                display_name="local",
                hostname="localhost",
                app_version="1.0",
            ),
            backend_factory=factory,
            on_event=lambda kind, payload: events.append((kind, payload)),
        )
        self.assertTrue(discovery.start())
        discovery.stop()
        backends[0].add(
            f"late.{SERVICE_TYPE}",
            {"properties": {"id": "late", "protocol_version": "1"}, "port": 5000},
        )
        self.assertEqual(discovery.peers(), ())
        self.assertEqual(events, [])


class _RecordingProcessManager:
    def __init__(self) -> None:
        self.calls: list[tuple[list[int], dict[int, float]]] = []

    def request_quit(
        self, pids: list[int], create_times: dict[int, float]
    ) -> ProcessActionResult:
        self.calls.append((pids, create_times))
        return ProcessActionResult(len(pids), tuple(pids), (), ())


class _UnusedProvider:
    def dashboard_snapshot(self) -> Any:
        raise AssertionError("evidence test must not execute the provider")


def _service() -> RemoteService:
    return RemoteService(
        node_id=NodeId("peer"),
        display_name="Peer",
        hostname="peer-host",
        platform="Linux",
        status=NodeStatus.ONLINE,
        capabilities=frozenset({NodeCapability.PROCESS_TERMINATION}),
        permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
        provider=_UnusedProvider(),
        process_manager=_RecordingProcessManager(),
        secret=SECRET,
        clock=lambda: 100.0,
    )


def _hello_service() -> RemoteService:
    return RemoteService(
        node_id=NodeId("peer"),
        display_name="Peer",
        hostname="peer-host",
        platform="Linux",
        status=NodeStatus.ONLINE,
        capabilities=frozenset({NodeCapability.DASHBOARD_READ}),
        permissions=frozenset({NodePermission.DASHBOARD_READ}),
        provider=_UnusedProvider(),
        secret=SECRET,
        clock=lambda: 100.0,
    )


if __name__ == "__main__":
    unittest.main()
