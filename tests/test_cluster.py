"""Cluster data-contract and trusted-node store tests."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from maintenance.cluster import (
    ClusterDataError,
    ClusterSaveError,
    ClusterState,
    ClusterStore,
    dashboard_snapshot_from_dict,
    dashboard_snapshot_to_dict,
    file_candidate_from_dict,
    file_candidate_to_dict,
    is_node_snapshot_compatible,
    node_snapshot_envelope,
    node_snapshot_from_dict,
    node_snapshot_to_dict,
    parse_node_snapshot_envelope,
    process_candidate_from_dict,
    process_candidate_to_dict,
    resource_summary_from_dict,
    resource_summary_to_dict,
    trusted_node_record,
)
from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    FileCandidate,
    ProcessCandidate,
    ResourceSummary,
)
from maintenance.nodes import (
    NODE_SNAPSHOT_SCHEMA_VERSION,
    NodeCapability,
    NodeId,
    NodeSnapshot,
    NodeStatus,
)
from tests.support.temperature import make_temperature_sample

NOW = datetime.now(timezone.utc).astimezone()


def _summary(key: str = "cpu") -> ResourceSummary:
    return ResourceSummary(
        key=key,
        title=key.upper(),
        value="10%",
        subtitle="running",
        percent=10.0,
        details=(f"{key.upper()}: 10%",),
        actionable=False,
        failed=False,
        capability=CapabilityState.SUPPORTED,
    )


def _dashboard() -> DashboardSnapshot:
    return DashboardSnapshot(
        system_label="peer-host",
        scanned_at=NOW,
        resources=(_summary("cpu"), _summary("memory")),
    )


def _snapshot() -> NodeSnapshot:
    return NodeSnapshot(
        node_id=NodeId("peer"),
        display_name="Peer",
        hostname="peer-host",
        platform="Linux",
        status=NodeStatus.ONLINE,
        capabilities=frozenset({NodeCapability.DASHBOARD_READ}),
        scanned_at=NOW,
        dashboard=_dashboard(),
    )


class ResourceSummaryCodecTests(unittest.TestCase):
    def test_round_trip_preserves_summary(self) -> None:
        original = _summary("cpu")
        decoded = resource_summary_from_dict(resource_summary_to_dict(original))
        self.assertEqual(decoded, original)

    def test_round_trip_preserves_temperatures(self) -> None:
        original = ResourceSummary(
            key="cpu",
            title="CPU",
            value="10%",
            subtitle="running",
            percent=10.0,
            details=("CPU: 45°C",),
            actionable=False,
            failed=False,
            capability=CapabilityState.SUPPORTED,
            temperatures=(make_temperature_sample("cpu", 45.0),),
        )
        decoded = resource_summary_from_dict(resource_summary_to_dict(original))
        self.assertEqual(decoded, original)

    def test_missing_key_is_rejected(self) -> None:
        with self.assertRaises(ClusterDataError):
            resource_summary_from_dict({"title": "x"})


class DashboardCodecTests(unittest.TestCase):
    def test_round_trip_preserves_dashboard(self) -> None:
        original = _dashboard()
        decoded = dashboard_snapshot_from_dict(dashboard_snapshot_to_dict(original))
        self.assertEqual(decoded, original)

    def test_invalid_resources_are_rejected(self) -> None:
        payload = dashboard_snapshot_to_dict(_dashboard())
        payload["resources"] = "nope"
        with self.assertRaises(ClusterDataError):
            dashboard_snapshot_from_dict(payload)


class NodeSnapshotCodecTests(unittest.TestCase):
    def test_round_trip_preserves_snapshot(self) -> None:
        original = _snapshot()
        decoded = node_snapshot_from_dict(node_snapshot_to_dict(original))
        self.assertEqual(decoded, original)

    def test_envelope_round_trip(self) -> None:
        original = _snapshot()
        decoded = parse_node_snapshot_envelope(node_snapshot_envelope(original))
        self.assertEqual(decoded, original)

    def test_unsupported_schema_is_rejected(self) -> None:
        payload = node_snapshot_to_dict(_snapshot())
        payload["schema_version"] = NODE_SNAPSHOT_SCHEMA_VERSION + 1
        with self.assertRaises(ClusterDataError):
            node_snapshot_from_dict(payload)

    def test_tampered_payload_is_rejected(self) -> None:
        payload = node_snapshot_to_dict(_snapshot())
        payload["status"] = "bogus"
        with self.assertRaises(ClusterDataError):
            node_snapshot_from_dict(payload)

    def test_compatibility_matches_schema_version(self) -> None:
        self.assertTrue(is_node_snapshot_compatible(NODE_SNAPSHOT_SCHEMA_VERSION))
        self.assertFalse(is_node_snapshot_compatible("2"))

    def test_is_stale_detects_age(self) -> None:
        fresh = _snapshot()
        self.assertFalse(fresh.is_stale(now=NOW, max_age=timedelta(seconds=60)))
        self.assertTrue(
            fresh.is_stale(
                now=NOW + timedelta(seconds=120), max_age=timedelta(seconds=60)
            )
        )


class ProcessAndFileCodecTests(unittest.TestCase):
    def test_process_candidate_round_trip(self) -> None:
        original = ProcessCandidate(
            1, "app", 100, 1.0, 2.0, "Active", "user", True, 1.5
        )
        decoded = process_candidate_from_dict(process_candidate_to_dict(original))
        self.assertEqual(decoded, original)

    def test_file_candidate_round_trip(self) -> None:
        original = FileCandidate(Path("/tmp/x"), 10, NOW, "reason")
        decoded = file_candidate_from_dict(file_candidate_to_dict(original))
        self.assertEqual(decoded, original)


class ClusterStoreTests(unittest.TestCase):
    def _store(self) -> tuple[ClusterStore, Path]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "cluster.json"
        return ClusterStore(path), path

    def test_missing_file_loads_defaults(self) -> None:
        store, _path = self._store()
        state = store.load()
        self.assertTrue(state.discovery_enabled)
        self.assertEqual(state.trusted_nodes, ())

    def test_save_and_load_round_trip(self) -> None:
        store, path = self._store()
        record = trusted_node_record(
            node_id="peer",
            display_name="Peer",
            hostname="peer-host",
            host="192.168.1.10",
            port=5000,
            capabilities=frozenset({NodeCapability.DASHBOARD_READ}),
            color="emerald",
        )
        state = ClusterState(discovery_enabled=False, trusted_nodes=(record,))
        store.save(state)
        loaded = ClusterStore(path).load()
        self.assertFalse(loaded.discovery_enabled)
        self.assertEqual(len(loaded.trusted_nodes), 1)
        restored = loaded.trusted_nodes[0]
        self.assertEqual(restored.node_id, "peer")
        self.assertEqual(restored.display_name, "Peer")
        self.assertEqual(restored.host, "192.168.1.10")
        self.assertEqual(restored.port, 5000)
        self.assertEqual(restored.color, "emerald")
        self.assertEqual(restored.capabilities, {NodeCapability.DASHBOARD_READ})
        self.assertEqual(restored.secret, record.secret)

    def test_malformed_file_falls_back_to_defaults(self) -> None:
        store, path = self._store()
        path.write_text("not json", encoding="utf-8")
        state = store.load()
        self.assertTrue(state.discovery_enabled)
        self.assertEqual(state.trusted_nodes, ())

    def test_unsupported_schema_falls_back_to_defaults(self) -> None:
        store, path = self._store()
        path.write_text('{"schema_version": 99}', encoding="utf-8")
        state = store.load()
        self.assertTrue(state.discovery_enabled)

    def test_record_without_secret_is_dropped(self) -> None:
        store, path = self._store()
        path.write_text(
            '{"schema_version": 1, "discovery_enabled": true, "trusted_nodes": '
            '[{"node_id": "peer", "display_name": "P", "hostname": "h", "host": "h"}]}',
            encoding="utf-8",
        )
        state = store.load()
        self.assertEqual(state.trusted_nodes, ())

    def test_save_failure_raises(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        store = ClusterStore(base / "cluster.json")
        store.save(ClusterState())
        # Turn the parent directory into a file so a later save cannot mkdir it.
        parent = base / "cluster.json"
        parent.unlink()
        parent.write_text("x", encoding="utf-8")
        store = ClusterStore(parent / "nested.json")
        with self.assertRaises(ClusterSaveError):
            store.save(ClusterState(discovery_enabled=False))

    def test_trusted_node_record_generates_a_secret(self) -> None:
        record = trusted_node_record(
            node_id="a", display_name="A", hostname="a", host="a"
        )
        self.assertEqual(len(record.secret), 64)

    def test_cluster_state_record_lookup(self) -> None:
        record = trusted_node_record(
            node_id="a", display_name="A", hostname="a", host="a"
        )
        state = ClusterState(trusted_nodes=(record,))
        self.assertIs(state.record("a"), record)
        self.assertIsNone(state.record("missing"))


if __name__ == "__main__":
    unittest.main()
