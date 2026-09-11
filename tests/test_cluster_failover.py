import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from maintenance.cluster import ClusterState, ClusterStore
from maintenance.components.cluster_roles import ClusterRole, CoordinatorEpoch, RoleAssignment
from maintenance.components.coordinator import AppCoordinator
from maintenance.components.peer_connection import PeerConnectionManager
from maintenance.components.cluster_storage import (
    CoordinatorTimeline,
    ResourceSnapshot,
    SnapshotBatch,
)
from maintenance.nodes import (
    ConnectionState,
    NodeContext,
    NodeDescriptor,
    NodeId,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
    local_node_descriptor,
)


class ClusterFailoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.clock = 100.0
        self.registry = NodeRegistry(
            NodeContext(
                descriptor=local_node_descriptor(),
                provider=Mock(),
                process_manager=Mock(),
                file_manager=Mock(),
                scheduler=Mock(),
                coordinator=Mock(),
            )
        )
        self.peer = NodeContext(
            descriptor=NodeDescriptor(
                id=NodeId("coord"),
                display_name="Coordinator",
                hostname="coord",
                is_local=False,
                trust=NodeTrustState.TRUSTED,
                status=NodeStatus.ONLINE,
                capabilities=frozenset(),
            ),
            provider=None,
            process_manager=None,
            file_manager=None,
            scheduler=None,
            coordinator=None,
        )
        self.peer.connection = ConnectionState.online(now=100.0)
        self.registry.register_context(self.peer)
        self.store = ClusterStore(self.root / "cluster.json")
        self.manager = PeerConnectionManager(
            registry=self.registry,
            coordinator=AppCoordinator(runner=lambda worker: None),
            connect=Mock(),
            clock=lambda: self.clock,
            cluster_store=self.store,
        )

    def state(self) -> ClusterState:
        return ClusterState(
            local_node_id="sub",
            cluster_id="cluster",
            role_assignments=(
                RoleAssignment(frozenset({ClusterRole.COORDINATOR}), NodeId("coord")),
                RoleAssignment(frozenset({ClusterRole.SUBCOORDINATOR}), NodeId("sub")),
            ),
            coordinator_epoch=CoordinatorEpoch(7, NodeId("coord"), "old", 0.0, 100.0),
        )

    def test_heartbeat_renewal_is_persisted(self) -> None:
        state = self.state()
        self.store.save(state)

        renewed = self.manager.renew_cluster_lease(
            state,
            coordinator_id=NodeId("coord"),
            fencing_token="old",
            now=99.0,
        )

        self.assertEqual(renewed.coordinator_epoch.lease_expires_at, 219.0)
        self.assertEqual(self.store.load().coordinator_epoch.issued_at, 99.0)

    def test_stale_heartbeat_epoch_is_rejected(self) -> None:
        state = self.state()
        stale = CoordinatorEpoch(6, NodeId("coord"), "old", 0.0, 100.0)

        self.assertFalse(
            self.manager.record_heartbeat(
                NodeId("coord"),
                now=99.0,
                epoch=stale,
                fencing_token="old",
                role_state=state,
            )
        )
        self.assertEqual(state.coordinator_epoch.epoch, 7)

    def test_subcoordinator_promotes_once_and_persists_new_epoch(self) -> None:
        state = self.state()
        self.store.save(state)

        decision = self.manager.promote_if_due(state, now=220.1)

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.epoch.epoch, 8)
        self.assertIn(ClusterRole.COORDINATOR, state.local_assignment.roles)
        self.assertEqual(self.store.load().coordinator_epoch.epoch, 8)
        self.assertIsNone(self.manager.promote_if_due(state, now=221.0))

    def test_promotion_imports_only_the_valid_standby_epoch(self) -> None:
        state = self.state()
        standby = CoordinatorTimeline(self.root / "standby.db", max_bytes=1024)
        timeline = CoordinatorTimeline(self.root / "history.db", max_bytes=1024)
        payload = (ResourceSnapshot(NodeId("worker"), "cpu", "10%", 10.0, 10.0, 100.0),)
        standby.append(
            SnapshotBatch("valid", NodeId("coord"), 7, 1, 100.0, payload, 20, "cluster"),
            now=100.0,
        )
        standby.append(
            SnapshotBatch("stale", NodeId("coord"), 6, 2, 101.0, payload, 20, "cluster"),
            now=101.0,
        )
        manager = PeerConnectionManager(
            registry=self.registry,
            coordinator=AppCoordinator(runner=lambda worker: None),
            connect=Mock(),
            clock=lambda: self.clock,
            cluster_store=self.store,
            timeline=timeline,
            standby=standby,
        )

        manager.promote_if_due(state, now=220.1)

        self.assertEqual(timeline.batch_ids(), ("valid",))

    def test_returning_former_coordinator_is_fenced_to_worker(self) -> None:
        state = self.state()
        self.manager.promote_if_due(state, now=220.1)
        state.role_assignments = (
            RoleAssignment(frozenset({ClusterRole.COORDINATOR}), NodeId("coord")),
        )
        state.coordinator_epoch = CoordinatorEpoch(8, NodeId("sub"), "new", 220.1, 340.1)

        self.manager.rejoin_as_worker(state, NodeId("coord"), 8)

        self.assertEqual(
            state.role_assignments[0].roles, frozenset({ClusterRole.WORKER})
        )

    def test_stale_returning_epoch_is_rejected_without_mutation(self) -> None:
        state = self.state()
        state.coordinator_epoch = CoordinatorEpoch(8, NodeId("sub"), "new", 0.0, 100.0)

        with self.assertRaises(ValueError):
            self.manager.rejoin_as_worker(state, NodeId("coord"), 7)
        self.assertIn(ClusterRole.COORDINATOR, state.role_assignments[0].roles)

    def test_timeline_rejects_wrong_cluster_epoch_and_sequence(self) -> None:
        timeline = CoordinatorTimeline(self.root / "timeline.db", max_bytes=1024)
        batch = SnapshotBatch(
            "one", NodeId("coord"), 7, 1, 100.0,
            (ResourceSnapshot(NodeId("worker"), "cpu", "10%", 10.0, 10.0, 100.0),),
            20,
            "cluster",
        )
        with self.assertRaises(ValueError):
            timeline.import_batch(batch, cluster_id="other", expected_epoch=7)
        with self.assertRaises(ValueError):
            timeline.import_batch(batch, cluster_id="cluster", expected_epoch=8)
        self.assertTrue(timeline.import_batch(batch, cluster_id="cluster", expected_epoch=7))
        with self.assertRaises(ValueError):
            timeline.import_batch(
                SnapshotBatch(
                    "two", NodeId("coord"), 7, 0, 101.0, batch.payload, 20, "cluster"
                ),
                cluster_id="cluster",
                expected_epoch=7,
            )


if __name__ == "__main__":
    unittest.main()
