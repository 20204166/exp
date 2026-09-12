"""Opposer 3 architecture/security counter-test for SEC-20260912-002.

Goal: verify that the suspected lifecycle, identity, and composition gaps do
not cross trust boundaries, do not fail open, and do not allow privilege
escalation or replay in the named discovery/remote surface.

This script imports repository code, runs only local loopback tests, and
asserts fail-closed behaviour. It does not edit app code or normal tests.
"""

from __future__ import annotations

import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maintenance.cluster import trusted_node_record
from maintenance.components.network_discovery import (
    DiscoveryAdvertisement,
    NetworkDiscovery,
)
from maintenance.models import DashboardSnapshot, ProcessActionResult
from maintenance.nodes import (
    LOCAL_NODE_ID,
    DiscoveredNodeCandidate,
    NodeCapability,
    NodeId,
    NodeIdentityStatus,
    NodePairingState,
    NodePermission,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
    generate_node_secret,
)
from maintenance.remote import (
    AuthenticatedNodeProvider,
    MemoryRemoteTransport,
    PairingRequest,
    RemoteAuthError,
    RemoteAuthorizationError,
    RemoteProtocolError,
    RemoteService,
    RemoteSocketServer,
    RemoteTransportError,
    TLSRemoteTransport,
    build_trusted_transport,
    sign_request,
)
from maintenance.remote_security import ensure_tls_material, server_context
from tests.support.discovery import FakeBackend
from tests.support.models import make_summary
from tests.support.nodes import make_local_context

SECRET = "a" * 64
SERVICE_TYPE = "_system-analyzer._tcp.local."


def _service(
    capabilities: frozenset[NodeCapability] = frozenset(
        {NodeCapability.DASHBOARD_READ}
    ),
    permissions: frozenset[NodePermission] | None = None,
) -> RemoteService:
    """Return a minimal RemoteService for loopback tests."""

    class FakeProvider:
        def dashboard_snapshot(self, cancel_event=None, progress_callback=None):
            return DashboardSnapshot(
                system_label="peer-host",
                scanned_at=datetime.now(timezone.utc),
                resources=(make_summary("cpu", "CPU", value="10%"),),
            )

    return RemoteService(
        node_id=NodeId("peer"),
        display_name="Peer",
        hostname="peer-host",
        platform="Linux",
        status=NodeStatus.ONLINE,
        capabilities=capabilities,
        permissions=permissions,
        provider=FakeProvider(),
        secret=SECRET,
    )


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_discovery_candidate_never_becomes_selectable() -> None:
    """A discovered candidate must remain untrusted and non-selectable."""

    local = make_local_context()
    registry = NodeRegistry(local)
    candidate = DiscoveredNodeCandidate(
        stable_id="peer-a",
        hostname="peer-a.local",
        addresses=("192.168.1.10",),
        port=5000,
        service_name=f"peer-a.{SERVICE_TYPE}",
        app_version="1.2.2.0",
        protocol_version="1",
        platform="Linux",
        connectable=True,
        compatible=True,
        last_seen=time.monotonic(),
        identity_fingerprint="aaaa:bbbb",
        transport_fingerprint="tls:aaaa:bbbb",
    )
    descriptor = registry.update_discovered(candidate)
    assert descriptor is not None
    _assert(
        descriptor.trust is NodeTrustState.UNTRUSTED,
        "candidate must remain untrusted",
    )
    _assert(
        descriptor.identity_status is NodeIdentityStatus.UNVERIFIED,
        "candidate identity must be unverified",
    )
    _assert(
        descriptor.capabilities == frozenset(),
        "candidate must have no capabilities",
    )
    _assert(
        registry.selectable_descriptors() == (local.descriptor,),
        "candidate must not be selectable",
    )
    try:
        registry.select(NodeId("peer-a"))
    except ValueError as error:
        _assert("not selectable" in str(error), "selection refusal must mention trust")
    else:
        raise AssertionError("selecting an untrusted candidate must raise")


def test_pairing_rejects_destructive_capabilities() -> None:
    """Read-only pairing flow must reject destructive permissions."""

    try:
        PairingRequest(
            caller_node_id=NodeId("caller"),
            identity_fingerprint="caller-id",
            transport_fingerprint="caller-tls",
            proposed_secret=generate_node_secret(),
            permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
        )
    except RemoteAuthorizationError as error:
        _assert("read-only" in str(error), "destructive pairing must be rejected")
    else:
        raise AssertionError("destructive pairing request must raise")


def test_tls_pin_blocks_wrong_certificate() -> None:
    """Wrong pinned cert is rejected before HMAC is even attempted."""

    with tempfile.TemporaryDirectory() as directory:
        material = ensure_tls_material(Path(directory), "peer")
        server = RemoteSocketServer(
            _service(),
            host="127.0.0.1",
            ssl_context=server_context(material),
        )
        server.start()
        try:
            port = server.bound_port
            assert port is not None
            provider = AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret=SECRET,
                transport=TLSRemoteTransport(
                    "127.0.0.1",
                    port,
                    expected_fingerprint="0" * 79,
                ),
            )
            try:
                provider.hello()
            except RemoteAuthError:
                return
            raise AssertionError("wrong pinned cert must raise RemoteAuthError")
        finally:
            server.stop()


def test_hmac_blocks_wrong_secret_despite_correct_tls() -> None:
    """Correct TLS pin with wrong secret is rejected at the HMAC layer."""

    with tempfile.TemporaryDirectory() as directory:
        material = ensure_tls_material(Path(directory), "peer")
        server = RemoteSocketServer(
            _service(),
            host="127.0.0.1",
            ssl_context=server_context(material),
        )
        server.start()
        try:
            port = server.bound_port
            assert port is not None
            provider = AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret="b" * 64,
                transport=TLSRemoteTransport(
                    "127.0.0.1",
                    port,
                    expected_fingerprint=material.fingerprint,
                ),
            )
            try:
                provider.hello()
            except (RemoteAuthError, RemoteProtocolError, RemoteTransportError):
                return
            raise AssertionError("wrong secret must raise auth/protocol error")
        finally:
            server.stop()


def test_replay_with_fresh_nonce_still_rejected_for_destructive() -> None:
    """Destructive request_id reuse is rejected even with a fresh nonce."""

    class FakeProcessManager:
        def request_quit(self, pids, create_times):
            return ProcessActionResult(len(pids), tuple(pids), (), ())

    service = RemoteService(
        node_id=NodeId("peer"),
        display_name="Peer",
        hostname="peer-host",
        platform="Linux",
        status=NodeStatus.ONLINE,
        capabilities=frozenset(
            {NodeCapability.DASHBOARD_READ, NodeCapability.PROCESS_TERMINATION}
        ),
        permissions=frozenset(
            {NodePermission.DASHBOARD_READ, NodePermission.PROCESS_TERMINATION}
        ),
        provider=_service()._provider,
        process_manager=FakeProcessManager(),
        secret=SECRET,
    )
    params = {"processes": [{"pid": 42, "create_time": 10.5}], "action": "request_quit"}
    first = sign_request(
        node_id="peer",
        op="process_request_quit",
        params=params,
        request_id="same-id",
        nonce="nonce-one",
        timestamp=time.time(),
        secret=SECRET,
    )
    second = dict(first)
    second["nonce"] = "nonce-two"
    second["sig"] = sign_request(
        node_id="peer",
        op="process_request_quit",
        params=params,
        request_id="same-id",
        nonce="nonce-two",
        timestamp=first["ts"],
        secret=SECRET,
    )["sig"]

    service.handle(json.dumps(first))
    try:
        service.handle(json.dumps(second))
    except RemoteAuthError as error:
        _assert("already been used" in str(error), "replay must be rejected")
        return
    raise AssertionError("destructive replay must raise RemoteAuthError")


def test_identity_mismatch_deselects_and_blocks_connection() -> None:
    """A trusted peer whose fingerprint changes becomes non-selectable."""

    local = make_local_context()
    registry = NodeRegistry(local)
    candidate = DiscoveredNodeCandidate(
        stable_id="peer-a",
        hostname="peer-a.local",
        addresses=("192.168.1.10",),
        port=5000,
        service_name=f"peer-a.{SERVICE_TYPE}",
        app_version="1.2.2.0",
        protocol_version="1",
        platform="Linux",
        connectable=True,
        compatible=True,
        last_seen=time.monotonic(),
        identity_fingerprint="aaaa:bbbb",
        transport_fingerprint="tls:aaaa:bbbb",
    )
    registry.update_discovered(candidate)
    registry.begin_pairing(NodeId("peer-a"))
    descriptor = registry.promote_to_trusted(
        NodeId("peer-a"),
        capabilities=frozenset({NodeCapability.DASHBOARD_READ}),
    )
    _assert(descriptor.trust is NodeTrustState.TRUSTED, "peer must be trusted")

    # Impersonator reuses stable_id but presents a different identity fingerprint.
    attacker = DiscoveredNodeCandidate(
        stable_id="peer-a",
        hostname="attacker.local",
        addresses=("192.168.1.66",),
        port=5000,
        service_name=f"peer-a.{SERVICE_TYPE}",
        app_version="1.2.2.0",
        protocol_version="1",
        platform="Linux",
        connectable=True,
        compatible=True,
        last_seen=time.monotonic(),
        identity_fingerprint="cccc:dddd",
        transport_fingerprint="tls:aaaa:bbbb",
    )
    updated = registry.update_discovered(attacker)
    assert updated is not None
    _assert(
        updated.identity_status is NodeIdentityStatus.MISMATCH,
        "mismatched fingerprint must mark identity as MISMATCH",
    )
    _assert(
        registry.pairing_state(NodeId("peer-a")) is NodePairingState.IDENTITY_CHANGED,
        "mismatch must move pairing state to IDENTITY_CHANGED",
    )
    _assert(
        registry.selectable_descriptors() == (local.descriptor,),
        "mismatched peer must not remain selectable",
    )


def test_discovery_lifecycle_ignores_late_events_after_stop() -> None:
    """Transport callbacks arriving after stop() must not mutate peer state."""

    events: list[tuple[str, Any]] = []
    backend_holder: list[FakeBackend] = []

    def factory(listener: Any) -> FakeBackend:
        backend = FakeBackend(listener)
        backend_holder.append(backend)
        return backend

    discovery = NetworkDiscovery(
        NodeId(LOCAL_NODE_ID),
        advertisement=DiscoveryAdvertisement(
            stable_id=LOCAL_NODE_ID,
            display_name="This System",
            hostname="host1",
            app_version="1.2.2.0",
            protocol_version="1",
            platform="Linux",
            connectable=False,
            port=None,
        ),
        backend_factory=factory,
        on_event=lambda kind, payload: events.append((kind, payload)),
    )
    discovery.start()
    backend = backend_holder[0]
    discovery.stop()
    backend.add(
        f"late.{SERVICE_TYPE}",
        {
            "properties": {
                "id": "late",
                "name": "late",
                "app_version": "1.2.2.0",
                "protocol_version": "1",
                "connectable": "false",
            },
            "port": 5000,
            "addresses": ["192.168.1.99"],
        },
    )
    _assert(discovery.peers() == (), "late events after stop must not add peers")
    _assert(events == [], "late events after stop must not emit lifecycle events")


def test_capability_permission_independence() -> None:
    """A node with a capability but no matching permission is denied."""

    service = _service(
        capabilities=frozenset(
            {
                NodeCapability.DASHBOARD_READ,
                NodeCapability.PROCESS_REVIEW,
            }
        ),
        permissions=frozenset({NodePermission.DASHBOARD_READ}),
    )
    client = AuthenticatedNodeProvider(
        node_id=NodeId("peer"),
        secret=SECRET,
        transport=MemoryRemoteTransport(service),
    )
    # hello uses DASHBOARD_READ permission, which is granted.
    _assert(client.hello()["ok"] is True, "hello should succeed")
    # process_candidates requires PROCESS_REVIEW permission, which is missing.
    try:
        client.process_candidates()
    except RemoteAuthorizationError:
        return
    raise AssertionError("missing permission must raise RemoteAuthorizationError")


def test_unknown_operation_fails_closed() -> None:
    """An unknown operation is rejected before any provider is touched."""

    service = _service()
    request = sign_request(
        node_id="peer",
        op="cleanup",
        params={"path": "/etc/passwd"},
        request_id="unknown-op",
        nonce="unknown-op-nonce",
        timestamp=time.time(),
        secret=SECRET,
    )
    try:
        service.handle(json.dumps(request))
    except RemoteProtocolError:
        return
    raise AssertionError("unknown operation must raise RemoteProtocolError")


def test_build_trusted_transport_rejects_missing_pin() -> None:
    """A trusted-node record without a pinned fingerprint cannot be used."""

    record = trusted_node_record(
        node_id="peer-a",
        display_name="Peer A",
        hostname="peer-a",
        host="192.0.2.10",
        port=5000,
        transport_fingerprint=None,
    )
    try:
        build_trusted_transport(record)
    except RemoteAuthError as error:
        _assert("pinned TLS fingerprint" in str(error), "missing pin must be rejected")
        return
    raise AssertionError("missing transport fingerprint must raise RemoteAuthError")


def main() -> None:
    tests = [
        test_discovery_candidate_never_becomes_selectable,
        test_pairing_rejects_destructive_capabilities,
        test_tls_pin_blocks_wrong_certificate,
        test_hmac_blocks_wrong_secret_despite_correct_tls,
        test_replay_with_fresh_nonce_still_rejected_for_destructive,
        test_identity_mismatch_deselects_and_blocks_connection,
        test_discovery_lifecycle_ignores_late_events_after_stop,
        test_capability_permission_independence,
        test_unknown_operation_fails_closed,
        test_build_trusted_transport_rejects_missing_pin,
    ]
    passed = 0
    failed: list[tuple[str, BaseException]] = []
    for test in tests:
        try:
            test()
            passed += 1
            print(f"PASS: {test.__name__}")
        except Exception as error:  # noqa: BLE001 - test harness
            failed.append((test.__name__, error))
            print(f"FAIL: {test.__name__}: {error}")
    print(f"\n{passed}/{len(tests)} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
