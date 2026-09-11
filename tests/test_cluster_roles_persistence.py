import json
import math
import tempfile
import unittest
from pathlib import Path

from maintenance.cluster import ClusterState, ClusterStore, InviteExpiredError
from maintenance.components.cluster_roles import ClusterRole


class ClusterRolePersistenceTests(unittest.TestCase):
    def test_local_state_round_trips_role_and_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ClusterStore(Path(directory) / "cluster.json")
            state = ClusterState.create_local(local_node_id="coord")
            store.save(state)
            restored = store.load()
        self.assertEqual(restored.local_node_id, "coord")
        self.assertIn(ClusterRole.COORDINATOR, restored.local_assignment.roles)
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

    def test_expired_invite_is_consumed_and_rejected(self) -> None:
        state = ClusterState.create_local(local_node_id="coord")
        invite = state.create_invite(now=100.0, ttl_seconds=60.0)
        with self.assertRaises(InviteExpiredError):
            state.consume_invite(invite.token, now=160.1)

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
        self.assertEqual(active_coordinators[0].node_id.value, "coord")
        self.assertIn(ClusterRole.WORKER, active_coordinators[0].roles)

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
