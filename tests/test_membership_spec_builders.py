"""Membership field derivation tests for trusted_node_specs() and cluster_node_specs().

These tests lock in the canonical rule:

    A peer is a cluster member iff ClusterState.role_assignments contains a
    current (non-revoked) assignment for that node.

Membership must NOT be derived from trust state, connection status,
descriptor.role, or any discovery metadata.

Rules under test:
    §2  PAIR does not imply membership.
    §4  JOIN creates membership in both coordinator and worker specs.
    §10 Revoked assignment -> is_cluster_member=False.
    §11 Role comes from role_assignments; descriptor.role is fallback only.
    §20 Connection state does not mutate membership.
    §21 remove_connection does not mutate canonical role_assignments.
"""

import time
import unittest
from dataclasses import replace
from typing import Any
from unittest.mock import Mock

from maintenance.cluster import ClusterState, trusted_node_record
from maintenance.components.cluster_roles import (
    ClusterRole,
    CoordinatorEpoch,
    RoleAssignment,
)
from maintenance.nodes import (
    NodeContext,
    NodeId,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
)
from maintenance.ui import window_node_actions
from maintenance.ui.window_supports import node_specs
from tests.support.nodes import make_local_context, make_remote_context
from tests.support.scheduling import DeferredRunner
from tests.test_window_nodes import _make_window, _trusted_context

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _registry_with_trusted_peer(peer_id: str = "peer-a") -> tuple[NodeRegistry, NodeContext]:
    """Return a registry containing a local node and one trusted remote peer."""
    registry = NodeRegistry()
    local = make_local_context()
    registry.register_context(local)
    peer = make_remote_context(
        peer_id,
        trust=NodeTrustState.TRUSTED,
        status=NodeStatus.ONLINE,
        display_name=f"Peer {peer_id}",
        hostname=peer_id,
    )
    registry.register_context(peer)
    return registry, peer


def _solo_cluster_state(local_id: str = "local") -> ClusterState:
    """Return a solo coordinator state — no workers enrolled yet."""
    return ClusterState.create_local(local_node_id=local_id)


def _cluster_state_with_worker(
    local_id: str = "local",
    worker_id: str = "peer-a",
    *,
    revoked: bool = False,
) -> ClusterState:
    """Return a coordinator state that includes worker_id in role_assignments."""
    state = ClusterState.create_local(local_node_id=local_id)
    state = replace(
        state,
        role_assignments=state.role_assignments + (
            RoleAssignment(
                frozenset({ClusterRole.WORKER}),
                node_id=NodeId(worker_id),
                revoked=revoked,
            ),
        ),
        trusted_nodes=(
            trusted_node_record(
                node_id=worker_id,
                display_name=f"Peer {worker_id}",
                hostname=worker_id,
                host="192.0.2.10",
                port=5000,
            ),
        ),
    )
    return state


def _cluster_state_with_coordinator_peer(
    local_id: str = "local",
    coordinator_peer_id: str = "peer-a",
) -> ClusterState:
    """Return a coordinator state that includes a peer with COORDINATOR+WORKER roles."""
    state = ClusterState.create_local(local_node_id=local_id)
    state = replace(
        state,
        role_assignments=state.role_assignments + (
            RoleAssignment(
                frozenset({ClusterRole.COORDINATOR, ClusterRole.WORKER}),
                node_id=NodeId(coordinator_peer_id),
            ),
        ),
        trusted_nodes=(
            trusted_node_record(
                node_id=coordinator_peer_id,
                display_name=f"Peer {coordinator_peer_id}",
                hostname=coordinator_peer_id,
                host="192.0.2.10",
                port=5000,
            ),
        ),
    )
    return state


# ---------------------------------------------------------------------------
# §2  PAIR only — is_cluster_member must be False
# ---------------------------------------------------------------------------

class PairOnlyMembershipTests(unittest.TestCase):
    """Pair establishes trust only; it must not set is_cluster_member=True."""

    def test_trusted_node_specs_pair_only_is_not_cluster_member(self) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        state = _solo_cluster_state("local")
        # Confirm there's no assignment for peer-a
        self.assertFalse(
            any(a.node_id == NodeId("peer-a") for a in state.role_assignments)
        )

        specs = node_specs.trusted_node_specs(registry, state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        self.assertEqual(len(peer_specs), 1)
        self.assertFalse(peer_specs[0].is_cluster_member)

    def test_trusted_node_specs_pair_only_role_defaults_to_worker_but_not_member(self) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        state = _solo_cluster_state("local")

        specs = node_specs.trusted_node_specs(registry, state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        # role field defaults to "worker" for display fallback, but membership is False
        self.assertEqual(peer_specs[0].role, "worker")
        self.assertFalse(peer_specs[0].is_cluster_member)

    def test_cluster_node_specs_pair_only_is_not_cluster_member(self) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        state = _solo_cluster_state("local")

        specs = node_specs.cluster_node_specs(registry, cluster_state=state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        self.assertEqual(len(peer_specs), 1)
        self.assertFalse(peer_specs[0].is_cluster_member)


# ---------------------------------------------------------------------------
# §4  JOIN creates membership
# ---------------------------------------------------------------------------

class JoinCreatesMembershipTests(unittest.TestCase):
    """After join, role_assignments contains the worker — specs must reflect it."""

    def test_trusted_node_specs_active_worker_is_cluster_member(self) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        state = _cluster_state_with_worker("local", "peer-a")

        specs = node_specs.trusted_node_specs(registry, state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        self.assertEqual(len(peer_specs), 1)
        self.assertTrue(peer_specs[0].is_cluster_member)
        self.assertEqual(peer_specs[0].role, "worker")

    def test_trusted_node_specs_coordinator_peer_is_cluster_member(self) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        state = _cluster_state_with_coordinator_peer("local", "peer-a")

        specs = node_specs.trusted_node_specs(registry, state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        self.assertTrue(peer_specs[0].is_cluster_member)
        self.assertEqual(peer_specs[0].role, "coordinator")

    def test_cluster_node_specs_active_worker_is_cluster_member(self) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        state = _cluster_state_with_worker("local", "peer-a")

        specs = node_specs.cluster_node_specs(registry, cluster_state=state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        self.assertTrue(peer_specs[0].is_cluster_member)
        self.assertEqual(peer_specs[0].role, "worker")

    def test_cluster_node_specs_coordinator_peer_role_from_assignments(self) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        state = _cluster_state_with_coordinator_peer("local", "peer-a")

        specs = node_specs.cluster_node_specs(registry, cluster_state=state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        self.assertTrue(peer_specs[0].is_cluster_member)
        self.assertEqual(peer_specs[0].role, "coordinator")

    def test_join_refreshes_both_nodes_and_cluster_pages(self) -> None:
        runner = DeferredRunner()
        peer_ctx = _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer")
        window = _make_window(peer_ctx, start_discovery=False)
        blob = _remote_invite_blob("peer-a")
        window._cluster_state = ClusterState(
            local_node_id="local",
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.0.2.10",
                    port=5000,
                    secret="secret",
                    transport_fingerprint="tls-pin",
                ),
            ),
            role_assignments=(
                RoleAssignment(
                    frozenset({ClusterRole.COORDINATOR, ClusterRole.WORKER}),
                    node_id=NodeId("local"),
                ),
            ),
            coordinator_epoch=CoordinatorEpoch(
                epoch=1,
                coordinator_id=NodeId("local"),
                fencing_token="t",
                issued_at=time.time(),
                lease_expires_at=time.time() + 300.0,
            ),
            cluster_id="local-cluster",
        )
        window._coordinator = _make_coordinator(runner)
        provider = Mock()
        provider.consume_invite.return_value = {
            "target_node_id": "local",
            "expires_at": time.time() + 300.0,
            "cluster_id": "remote-cluster",
            "coordinator_id": "peer-a",
            "epoch": 3,
            "fencing_token": "fence-token",
        }
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._nodes_error = Mock()
        window._nodes_status = Mock()
        saved_states: list[ClusterState] = []

        def save(s: ClusterState) -> bool:
            saved_states.append(s)
            window._cluster_state = s
            return True

        window._save_cluster_state = Mock(side_effect=save)

        window_node_actions.join_cluster_via_invite(
            window, "peer-a", blob,
            provider_cls=Mock(return_value=provider), transport_cls=Mock,
        )
        runner.run_next()

        window._nodes_error.assert_not_called()
        window._refresh_nodes_page.assert_called()
        window._refresh_cluster_page.assert_called()


def _remote_invite_blob(coordinator_id: str = "peer-a") -> str:
    remote_state = ClusterState.create_local(local_node_id=coordinator_id)
    invite = remote_state.create_invite(target_node_id="local")
    from maintenance.cluster import encode_invite_blob
    return encode_invite_blob(invite)


def _make_coordinator(runner: DeferredRunner) -> Any:
    from maintenance.components.coordinator import AppCoordinator
    return AppCoordinator(runner=runner, deliver=lambda cb: cb())


# ---------------------------------------------------------------------------
# §10  Revoked assignment -> is_cluster_member=False
# ---------------------------------------------------------------------------

class RevokedAssignmentMembershipTests(unittest.TestCase):
    """Historical/revoked assignments must never yield is_cluster_member=True."""

    def test_trusted_node_specs_revoked_is_not_cluster_member(self) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        state = _cluster_state_with_worker("local", "peer-a", revoked=True)

        specs = node_specs.trusted_node_specs(registry, state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        self.assertEqual(len(peer_specs), 1)
        self.assertFalse(peer_specs[0].is_cluster_member)

    def test_cluster_node_specs_revoked_is_not_cluster_member(self) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        state = _cluster_state_with_worker("local", "peer-a", revoked=True)

        specs = node_specs.cluster_node_specs(registry, cluster_state=state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        self.assertFalse(peer_specs[0].is_cluster_member)

    def test_trusted_node_specs_revoked_role_is_fallback_worker(self) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        # Revoked coordinator assignment — must not show coordinator membership
        state = ClusterState.create_local(local_node_id="local")
        state = replace(
            state,
            role_assignments=state.role_assignments + (
                RoleAssignment(
                    frozenset({ClusterRole.COORDINATOR, ClusterRole.WORKER}),
                    node_id=NodeId("peer-a"),
                    revoked=True,
                ),
            ),
        )

        specs = node_specs.trusted_node_specs(registry, state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        self.assertFalse(peer_specs[0].is_cluster_member)


# ---------------------------------------------------------------------------
# §11  Role source: role_assignments wins over descriptor.role
# ---------------------------------------------------------------------------

class RoleSourceTests(unittest.TestCase):
    """The canonical role for a member comes from role_assignments, not descriptor."""

    def test_cluster_node_specs_coordinator_assignment_wins_over_descriptor_worker(
        self,
    ) -> None:
        registry, peer = _registry_with_trusted_peer("peer-a")
        # Descriptor says "worker" (the discovery default)
        self.assertEqual(peer.descriptor.role, "worker")
        state = _cluster_state_with_coordinator_peer("local", "peer-a")

        specs = node_specs.cluster_node_specs(registry, cluster_state=state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        # Canonical role from role_assignments must win
        self.assertEqual(peer_specs[0].role, "coordinator")
        self.assertTrue(peer_specs[0].is_cluster_member)

    def test_cluster_node_specs_non_member_falls_back_to_descriptor_role(self) -> None:
        registry, peer = _registry_with_trusted_peer("peer-a")
        # No assignment in cluster state
        state = _solo_cluster_state("local")

        specs = node_specs.cluster_node_specs(registry, cluster_state=state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        # Fallback to descriptor.role is acceptable for non-members
        self.assertEqual(peer_specs[0].role, peer.descriptor.role)
        # But membership must remain False regardless of descriptor.role
        self.assertFalse(peer_specs[0].is_cluster_member)

    def test_cluster_node_specs_revoked_coordinator_falls_back_to_descriptor(
        self,
    ) -> None:
        registry, _peer = _registry_with_trusted_peer("peer-a")
        state = ClusterState.create_local(local_node_id="local")
        state = replace(
            state,
            role_assignments=state.role_assignments + (
                RoleAssignment(
                    frozenset({ClusterRole.COORDINATOR, ClusterRole.WORKER}),
                    node_id=NodeId("peer-a"),
                    revoked=True,
                ),
            ),
        )

        specs = node_specs.cluster_node_specs(registry, cluster_state=state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        # Revoked -> fallback to descriptor; not marked as member
        self.assertFalse(peer_specs[0].is_cluster_member)


# ---------------------------------------------------------------------------
# §20  Connection loss does not mutate membership
# ---------------------------------------------------------------------------

class ConnectionVsMembershipTests(unittest.TestCase):
    """Disconnecting a worker must not change role_assignments or is_cluster_member."""

    def test_remove_connection_does_not_mutate_role_assignments(self) -> None:
        runner = DeferredRunner()
        peer_ctx = _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer")
        window = _make_window(peer_ctx, start_discovery=False)

        state = _cluster_state_with_worker("local", "peer-a")
        window._cluster_state = state

        def save(s: ClusterState) -> bool:
            window._cluster_state = s
            return True

        window._save_cluster_state = Mock(side_effect=save)
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._nodes_error = Mock()
        window._cancel_node_operations = Mock()
        window._cancel_peer_connection = Mock()
        window._invalidate_node_render_targets = Mock()
        window._sync_selected_context_mirrors = Mock()
        window._render_selected_node = Mock()
        window._coordinator = _make_coordinator(runner)

        original_assignments = window._cluster_state.role_assignments

        window_node_actions.remove_connection_node(
            window, "peer-a",
            messagebox_module=Mock(askyesno=Mock(return_value=True)),
            provider_cls=Mock(return_value=Mock(remove_connection=Mock(return_value={"ok": True}))),
            transport_cls=Mock,
        )
        runner.run_next()

        # role_assignments must NOT have been mutated by remove_connection
        self.assertEqual(
            window._cluster_state.role_assignments, original_assignments,
            "remove_connection must not mutate role_assignments",
        )

    def test_membership_persists_in_spec_after_node_goes_offline(self) -> None:
        registry, peer = _registry_with_trusted_peer("peer-a")
        state = _cluster_state_with_worker("local", "peer-a")

        # Simulate online
        online_specs = node_specs.trusted_node_specs(registry, state)
        peer_online = next(s for s in online_specs if s.node_id == "peer-a")
        self.assertTrue(peer_online.is_cluster_member)

        # Simulate offline — only connection_status changes, not role_assignments
        from maintenance.nodes import NodeConnectionStatus
        peer.connection = replace(
            peer.connection, status=NodeConnectionStatus.OFFLINE
        )

        offline_specs = node_specs.trusted_node_specs(registry, state)
        peer_offline = next(s for s in offline_specs if s.node_id == "peer-a")

        # Membership must persist; only status changes
        self.assertTrue(peer_offline.is_cluster_member)
        self.assertEqual(peer_offline.role, "worker")
        self.assertEqual(peer_offline.connection_status, "offline")

    def test_membership_persists_in_cluster_spec_after_node_goes_offline(self) -> None:
        registry, peer = _registry_with_trusted_peer("peer-a")
        state = _cluster_state_with_worker("local", "peer-a")

        from maintenance.nodes import NodeConnectionStatus
        peer.connection = replace(
            peer.connection, status=NodeConnectionStatus.OFFLINE
        )

        specs = node_specs.cluster_node_specs(registry, cluster_state=state)
        peer_specs = [s for s in specs if s.node_id == "peer-a"]

        self.assertTrue(peer_specs[0].is_cluster_member)
        self.assertEqual(peer_specs[0].role, "worker")
