import base64
import json
import math
import tempfile
import unittest
from pathlib import Path

from maintenance.cluster import (
    ClusterDataError,
    ClusterState,
    ClusterStore,
    InviteExpiredError,
    decode_invite_blob,
    encode_invite_blob,
)
from maintenance.components.cluster_roles import CapabilityGrant, ClusterRole
from maintenance.nodes import NodeId, NodePermission


class ClusterRolePersistenceTests(unittest.TestCase):
    def test_local_state_round_trips_role_and_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ClusterStore(Path(directory) / "cluster.json")
            state = ClusterState.create_local(local_node_id="coord")
            store.save(state)
            restored = store.load()
        self.assertEqual(restored.local_node_id, "coord")
        self.assertIn(ClusterRole.COORDINATOR, restored.local_assignment.roles)
        assert restored.coordinator_epoch is not None
        self.assertEqual(restored.coordinator_epoch.epoch, 1)

    def test_v1_state_gets_safe_local_coordinator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            path.write_text(
                '{"schema_version": 1, "local_node_id": "legacy", '
                '"trusted_nodes": [], "peer_grants": []}',
                encoding="utf-8",
            )
            state = ClusterStore(path).load()
        self.assertIn(ClusterRole.COORDINATOR, state.local_assignment.roles)

    def test_has_active_job_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            store = ClusterStore(path)
            state = ClusterState.create_local(local_node_id="coord")
            assignment = state.local_assignment
            idle = type(assignment)(
                assignment.roles,
                node_id=assignment.node_id,
                paused=assignment.paused,
                revoked=assignment.revoked,
                has_active_job=False,
            )
            state.role_assignments = (idle,)
            store.save(state)
            loaded = store.load()
        self.assertFalse(loaded.local_assignment.has_active_job)

    def test_has_active_job_defaults_true_for_old_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            payload = {
                "schema_version": 2,
                "local_node_id": "worker",
                "trusted_nodes": [],
                "peer_grants": [],
                "role_assignments": [{"node_id": "worker", "roles": ["worker"]}],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = ClusterStore(path).load()
        self.assertTrue(loaded.local_assignment.has_active_job)

    def test_has_active_job_false_and_paused_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            store = ClusterStore(path)
            state = ClusterState.create_local(local_node_id="worker")
            idle = type(state.local_assignment)(
                frozenset({ClusterRole.WORKER}),
                node_id=NodeId("worker"),
                paused=True,
                has_active_job=False,
            )
            state.role_assignments = (idle,)
            store.save(state)
            loaded = store.load()
        assignment = loaded.local_assignment
        self.assertTrue(assignment.paused)
        self.assertFalse(assignment.has_active_job)

    def test_non_bool_has_active_job_defaults_true(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            payload = {
                "schema_version": 2,
                "local_node_id": "worker",
                "trusted_nodes": [],
                "peer_grants": [],
                "role_assignments": [
                    {"node_id": "worker", "roles": ["worker"], "has_active_job": "yes"}
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = ClusterStore(path).load()
        self.assertTrue(loaded.local_assignment.has_active_job)

    def test_revoked_with_no_active_job_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            store = ClusterStore(path)
            state = ClusterState.create_local(local_node_id="coord")
            revoked_idle = type(state.local_assignment)(
                frozenset({ClusterRole.WORKER}),
                node_id=NodeId("peer"),
                revoked=True,
                has_active_job=False,
            )
            state.role_assignments = (
                state.local_assignment,
                revoked_idle,
            )
            store.save(state)
            loaded = store.load()
        peer = next(
            item for item in loaded.role_assignments if item.node_id == NodeId("peer")
        )
        self.assertTrue(peer.revoked)
        self.assertFalse(peer.has_active_job)

    def test_coordinator_assignment_persists_active_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            store = ClusterStore(path)
            state = ClusterState.create_local(local_node_id="coord")
            store.save(state)
            loaded = store.load()
        self.assertTrue(loaded.local_assignment.has_active_job)

    def test_expired_invite_is_consumed_and_rejected(self) -> None:
        state = ClusterState.create_local(local_node_id="coord")
        invite = state.create_invite(now=100.0, ttl_seconds=60.0)
        with self.assertRaises(InviteExpiredError):
            state.consume_invite(invite.token, now=160.1)

    def test_create_invite_binds_the_issuing_cluster_fence(self) -> None:
        state = ClusterState.create_local(local_node_id="coord")
        invite = state.create_invite(now=100.0)
        assert state.coordinator_epoch is not None
        self.assertEqual(invite.cluster_id, state.cluster_id)
        self.assertEqual(
            invite.coordinator_id, state.coordinator_epoch.coordinator_id.value
        )
        self.assertEqual(invite.epoch, state.coordinator_epoch.epoch)
        self.assertEqual(invite.fencing_token, state.coordinator_epoch.fencing_token)

    def test_create_invite_requires_a_coordinator_epoch(self) -> None:
        state = ClusterState(local_node_id="coord")
        with self.assertRaises(ValueError):
            state.create_invite(now=100.0)

    def test_invite_blob_round_trips(self) -> None:
        state = ClusterState.create_local(local_node_id="coord")
        invite = state.create_invite(now=100.0)
        blob = encode_invite_blob(invite)
        decoded = decode_invite_blob(blob)
        self.assertEqual(decoded.token, invite.token)
        self.assertEqual(decoded.cluster_id, invite.cluster_id)
        self.assertEqual(decoded.coordinator_id, invite.coordinator_id)
        self.assertEqual(decoded.epoch, invite.epoch)
        self.assertEqual(decoded.fencing_token, invite.fencing_token)
        self.assertEqual(decoded.expires_at, invite.expires_at)
        self.assertEqual(decoded.target_node_id, invite.target_node_id)

    def test_decode_invite_blob_rejects_garbage(self) -> None:
        with self.assertRaises(ClusterDataError):
            decode_invite_blob("not-base64-json")

    def test_decode_invite_blob_rejects_missing_fence_fields(self) -> None:
        blob = base64.urlsafe_b64encode(
            json.dumps({"token": "abc", "expires_at": 1.0}).encode("utf-8")
        ).decode("ascii")
        with self.assertRaises(ClusterDataError):
            decode_invite_blob(blob)

    def test_invite_without_persisted_fence_fields_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            payload = {
                "schema_version": 2,
                "local_node_id": "coord",
                "trusted_nodes": [],
                "peer_grants": [],
                "active_invites": [
                    {
                        "token_hash": "ab" * 32,
                        "target_node_id": "worker",
                        "expires_at": 9999999999.0,
                    }
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            state = ClusterStore(path).load()
        self.assertEqual(len(state.active_invites), 1)
        self.assertEqual(state.active_invites[0].cluster_id, "")
        self.assertEqual(state.active_invites[0].epoch, 0)

    def test_non_finite_invite_expiry_is_skipped_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            payload = {
                "schema_version": 2,
                "local_node_id": "coord",
                "trusted_nodes": [],
                "peer_grants": [],
                "active_invites": [
                    {
                        "token_hash": "ab" * 32,
                        "target_node_id": "worker",
                        "expires_at": float("nan"),
                    }
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            state = ClusterStore(path).load()
        self.assertEqual(state.active_invites, ())

    def test_duplicate_active_coordinators_collapse_to_one_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            payload = {
                "schema_version": 2,
                "local_node_id": "coord",
                "trusted_nodes": [],
                "peer_grants": [],
                "role_assignments": [
                    {"node_id": "coord", "roles": ["coordinator", "worker"]},
                    {"node_id": "other", "roles": ["coordinator", "worker"]},
                    {"node_id": "peer", "roles": ["worker"]},
                ],
                "coordinator_epoch": {
                    "epoch": 1,
                    "coordinator_id": "coord",
                    "fencing_token": "t",
                    "issued_at": 100.0,
                    "lease_expires_at": 220.0,
                },
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            state = ClusterStore(path).load()
        active_coordinators = [
            item
            for item in state.role_assignments
            if ClusterRole.COORDINATOR in item.roles and not item.revoked
        ]
        self.assertEqual(len(active_coordinators), 1)
        node_id = active_coordinators[0].node_id
        assert node_id is not None
        self.assertEqual(node_id.value, "coord")
        self.assertIn(ClusterRole.WORKER, active_coordinators[0].roles)

    def test_duplicate_active_subcoordinators_collapse_to_one_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            payload = {
                "schema_version": 2,
                "local_node_id": "coord",
                "trusted_nodes": [],
                "peer_grants": [],
                "role_assignments": [
                    {"node_id": "first", "roles": ["subcoordinator"]},
                    {"node_id": "second", "roles": ["subcoordinator"]},
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            state = ClusterStore(path).load()

        active_subcoordinators = [
            item
            for item in state.role_assignments
            if ClusterRole.SUBCOORDINATOR in item.roles and not item.revoked
        ]
        self.assertEqual(len(active_subcoordinators), 1)
        node_id = active_subcoordinators[0].node_id
        assert node_id is not None
        self.assertEqual(node_id.value, "first")

    def test_non_finite_epoch_lease_is_rejected_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            payload = {
                "schema_version": 2,
                "local_node_id": "coord",
                "trusted_nodes": [],
                "peer_grants": [],
                "role_assignments": [
                    {"node_id": "coord", "roles": ["coordinator", "worker"]}
                ],
                "coordinator_epoch": {
                    "epoch": 1,
                    "coordinator_id": "coord",
                    "fencing_token": "t",
                    "issued_at": 100.0,
                    "lease_expires_at": math.inf,
                },
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            state = ClusterStore(path).load()
        self.assertIsNotNone(state.coordinator_epoch)
        assert state.coordinator_epoch is not None
        self.assertTrue(math.isfinite(state.coordinator_epoch.lease_expires_at))
        self.assertIn(ClusterRole.COORDINATOR, state.local_assignment.roles)

    def test_capability_grant_round_trips(self) -> None:
        grant = CapabilityGrant(
            NodeId("sub"),
            NodeId("worker"),
            frozenset({NodePermission.COMPONENT_READ, NodePermission.CLEANUP}),
            10.0,
            100.0,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            store = ClusterStore(path)
            store.save(ClusterState(capability_grants=(grant,)))
            loaded = store.load()
        self.assertEqual(loaded.capability_grants, (grant,))

    def test_malformed_capability_grants_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "local_node_id": "coord",
                        "capability_grants": [
                            {
                                "subject": "sub",
                                "target": "worker",
                                "permissions": [],
                                "issued_at": 10.0,
                                "expires_at": 100.0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            loaded = ClusterStore(path).load()
        self.assertEqual(loaded.capability_grants, ())
