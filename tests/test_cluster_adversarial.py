import json
import tempfile
import unittest
from pathlib import Path

from maintenance.components.cluster_roles import ClusterRole
from maintenance.components.cluster_storage import (
    ResourceSnapshot,
    SnapshotBatch,
    StandbyBuffer,
)
from maintenance.nodes import NodeCapability, NodeId, NodePermission, NodeStatus
from maintenance.remote import (
    RemoteAuthorizationError,
    RemoteService,
    sign_request,
)

SECRET = "a" * 64


class ClusterAdversarialTests(unittest.TestCase):
    def test_stale_fencing_token_cannot_invoke_role_handler(self) -> None:
        calls: list[str] = []

        def handler(request):
            calls.append(request.op)
            return {"ok": True}

        service = RemoteService(
            node_id=NodeId("worker"),
            display_name="Worker",
            hostname="worker",
            platform="Linux",
            status=NodeStatus.ONLINE,
            capabilities=frozenset({NodeCapability.REMOTE_MANAGEMENT}),
            permissions=frozenset({NodePermission.REMOTE_MANAGEMENT}),
            provider=object(),
            secret=SECRET,
            expected_caller_id=NodeId("coord"),
            cluster_id="cluster",
            coordinator_epoch=2,
            fencing_token="current",
            role_handler=handler,
        )
        envelope = sign_request(
            node_id="worker",
            caller_node_id="coord",
            op="pause_worker",
            params={
                "target_node_id": "worker",
                "cluster_id": "cluster",
                "epoch": 1,
                "fencing_token": "old",
            },
            request_id="one",
            nonce="one",
            timestamp=service._clock(),
            secret=SECRET,
        )
        with self.assertRaises(RemoteAuthorizationError):
            service.handle(json.dumps(envelope))
        self.assertEqual(calls, [])

    def test_standby_overflow_discards_oldest_and_never_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StandbyBuffer(Path(directory) / "standby.db", max_bytes=10)
            payload = (ResourceSnapshot(NodeId("worker"), "cpu", "x", 1.0, 1.0, 1.0),)
            first = SnapshotBatch("one", NodeId("coord"), 1, 1, 100.0, payload, 8)
            second = SnapshotBatch("two", NodeId("coord"), 1, 2, 101.0, payload, 8)
            self.assertTrue(store.append(first, now=101.0))
            self.assertTrue(store.append(second, now=101.0))
            self.assertEqual(store.batch_ids(), ("two",))
            self.assertFalse(store.append(second, now=101.0))

    def test_role_enum_does_not_treat_subcoordinator_as_coordinator(self) -> None:
        self.assertNotEqual(ClusterRole.SUBCOORDINATOR, ClusterRole.COORDINATOR)
