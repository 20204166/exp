"""Opposer 2 repository-truth counter-tests for SEC-20260912-002.

This is an independent, read-only PoC.  It checks that discovery metadata does
not authorize a peer and that the authenticated remote boundary binds grants,
operations, replay state, identity, and lifecycle state to the right node.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from typing import Any

from maintenance.components.network_discovery import (
    DiscoveryAdvertisement,
    NetworkDiscovery,
)
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
    node_operation_key,
)
from maintenance.remote import (
    PairingRequest,
    PeerGrant,
    RemoteAuthError,
    RemoteAuthorizationError,
    RemoteProtocolError,
    RemoteService,
    ReplayCache,
    sign_request,
)
from maintenance.remote_support.protocol import parse_hello_capabilities
from tests.support.discovery import FakeBackend
from tests.support.nodes import make_local_context

SECRET_A = "a" * 64
SECRET_B = "b" * 64


def _candidate(
    stable_id: str = "peer-a",
    *,
    compatible: bool = True,
    identity_fingerprint: str | None = "peer-a-fingerprint",
    address: str = "192.0.2.10",
) -> DiscoveredNodeCandidate:
    return DiscoveredNodeCandidate(
        stable_id=stable_id,
        hostname="peer.example",
        addresses=(address,),
        port=5000,
        service_name=f"{stable_id}._system-analyzer._tcp.local.",
        app_version="1.0",
        protocol_version="1" if compatible else "999",
        platform="Linux",
        connectable=True,
        compatible=compatible,
        last_seen=1.0,
        identity_fingerprint=identity_fingerprint,
        transport_fingerprint="tls:fingerprint",
    )


class DiscoveryAuthorizationTests(unittest.TestCase):
    def test_discovered_candidate_is_not_selectable_or_capable(self) -> None:
        registry = NodeRegistry()
        descriptor = registry.update_discovered(_candidate())

        self.assertIsNotNone(descriptor)
        assert descriptor is not None
        self.assertEqual(descriptor.trust, NodeTrustState.UNTRUSTED)
        self.assertEqual(descriptor.capabilities, frozenset())
        self.assertEqual(descriptor.permissions, frozenset())
        self.assertNotIn(descriptor, registry.selectable_descriptors())
        with self.assertRaises(ValueError):
            registry.select(NodeId("peer-a"))

    def test_pairing_and_promotion_reject_non_read_permissions(self) -> None:
        with self.assertRaises(RemoteAuthorizationError):
            PairingRequest(
                caller_node_id=NodeId("caller"),
                identity_fingerprint="identity",
                transport_fingerprint="tls",
                proposed_secret=SECRET_A,
                permissions=frozenset({NodePermission.CLEANUP}),
            )

        registry = NodeRegistry()
        registry.update_discovered(_candidate())
        registry.begin_pairing(NodeId("peer-a"))
        with self.assertRaises(ValueError):
            registry.promote_to_trusted(
                NodeId("peer-a"),
                capabilities=frozenset({NodeCapability.PROCESS_TERMINATION}),
            )

    def test_incompatible_candidate_cannot_enter_pairing(self) -> None:
        registry = NodeRegistry()
        registry.update_discovered(_candidate(compatible=False))

        with self.assertRaises(ValueError):
            registry.begin_pairing(NodeId("peer-a"))


class RemoteAuthorizationTests(unittest.TestCase):
    def test_grant_mode_binds_credential_to_claimed_caller(self) -> None:
        grants = {
            NodeId("caller-a"): PeerGrant(
                NodeId("caller-a"), SECRET_A, frozenset({NodePermission.DASHBOARD_READ})
            ),
            NodeId("caller-b"): PeerGrant(
                NodeId("caller-b"), SECRET_B, frozenset({NodePermission.DASHBOARD_READ})
            ),
        }
        service = _service(grants=grants)
        request = sign_request(
            node_id="target",
            caller_node_id="caller-b",
            op="hello",
            params={},
            request_id="caller-binding",
            nonce="nonce-a",
            timestamp=100.0,
            secret=SECRET_A,
        )

        with self.assertRaises(RemoteAuthError):
            service.handle(json.dumps(request))

    def test_missing_or_unknown_grant_caller_is_rejected(self) -> None:
        service = _service(
            grants={
                NodeId("caller-a"): PeerGrant(NodeId("caller-a"), SECRET_A, frozenset())
            }
        )
        for caller in (None, "caller-unknown"):
            with self.subTest(caller=caller), self.assertRaises(RemoteAuthError):
                request = sign_request(
                    node_id="target",
                    caller_node_id=caller,
                    op="hello",
                    params={},
                    request_id=f"missing-{caller}",
                    nonce=f"nonce-{caller}",
                    timestamp=100.0,
                    secret=SECRET_A,
                )
                service.handle(json.dumps(request))

    def test_unknown_operation_and_missing_permission_fail_closed(self) -> None:
        service = _service(
            capabilities=frozenset({NodeCapability.DASHBOARD_READ}),
            permissions=frozenset(),
        )
        unknown = sign_request(
            node_id="target",
            op="delete_everything",
            params={},
            request_id="unknown-op",
            nonce="unknown-op",
            timestamp=100.0,
            secret=SECRET_A,
        )
        with self.assertRaises(RemoteProtocolError):
            service.handle(json.dumps(unknown))

        denied = sign_request(
            node_id="target",
            op="hello",
            params={},
            request_id="missing-permission",
            nonce="missing-permission",
            timestamp=100.0,
            secret=SECRET_A,
        )
        response = json.loads(service.handle(json.dumps(denied)))
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "permission_denied")

    def test_unknown_capability_and_permission_are_not_granted(self) -> None:
        parsed = parse_hello_capabilities(
            {"capabilities": ["dashboard_read", "future_admin_capability"]}
        )
        self.assertEqual(parsed, frozenset({NodeCapability.DASHBOARD_READ}))
        with self.assertRaises(ValueError):
            PairingRequest(
                caller_node_id=NodeId("caller"),
                identity_fingerprint="identity",
                transport_fingerprint="tls",
                proposed_secret=SECRET_A,
                permissions=frozenset({NodePermission("future_permission")}),
            )


class ReplayIdentityLifecycleTests(unittest.TestCase):
    def test_replay_cache_rejects_nonce_and_request_id_reuse(self) -> None:
        cache = ReplayCache(clock=lambda: 100.0)
        self.assertTrue(cache.check_and_record("peer", "request", "nonce", 100.0))
        self.assertFalse(cache.check_and_record("peer", "request", "nonce", 100.0))
        self.assertTrue(cache.check_and_record_request_id("peer", "destructive", 100.0))
        self.assertFalse(
            cache.check_and_record_request_id("peer", "destructive", 100.0)
        )

    def test_stable_identity_survives_metadata_change_but_mismatch_deselects(
        self,
    ) -> None:
        registry = NodeRegistry(make_local_context())
        registry.update_discovered(_candidate())
        registry.begin_pairing(NodeId("peer-a"))
        registry.promote_to_trusted(NodeId("peer-a"))
        context = registry.context(NodeId("peer-a"))
        context.provider = object()
        context.scheduler = object()
        registry.select(NodeId("peer-a"))

        renamed = replace(_candidate(address="192.0.2.11"), hostname="renamed.example")
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

    def test_lifecycle_stop_drops_late_events_and_keys_are_node_qualified(self) -> None:
        events: list[tuple[str, Any]] = []
        holders: list[FakeBackend] = []

        def factory(listener: Any) -> FakeBackend:
            backend = FakeBackend(listener)
            holders.append(backend)
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
        holders[0].add(
            "late._system-analyzer._tcp.local.",
            {
                "properties": {"id": "late", "protocol_version": "1"},
                "port": 5000,
                "addresses": ["192.0.2.20"],
            },
        )
        self.assertEqual(discovery.peers(), ())
        self.assertEqual(events, [])
        self.assertNotEqual(
            node_operation_key(NodeId("peer-a"), "dashboard"),
            node_operation_key(NodeId("peer-b"), "dashboard"),
        )


def _service(
    *,
    capabilities: frozenset[NodeCapability] = frozenset(
        {NodeCapability.DASHBOARD_READ}
    ),
    permissions: frozenset[NodePermission] | None = None,
    grants: dict[NodeId, PeerGrant] | None = None,
) -> RemoteService:
    class Provider:
        def dashboard_snapshot(self) -> Any:
            raise AssertionError("counter-test must not execute provider")

    return RemoteService(
        node_id=NodeId("target"),
        display_name="Target",
        hostname="target.example",
        platform="Linux",
        status=NodeStatus.ONLINE,
        capabilities=capabilities,
        permissions=permissions,
        provider=Provider(),
        secret=SECRET_A,
        grants=grants,
        clock=lambda: 100.0,
    )


if __name__ == "__main__":
    unittest.main()
