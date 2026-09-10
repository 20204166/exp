"""Mixed-version wire and persisted-record compatibility matrix."""

import json
import tempfile
import unittest
from pathlib import Path

from maintenance.cluster import (
    ClusterStore,
    node_snapshot_from_dict,
    process_candidate_from_dict,
)
from maintenance.nodes import NodeCapability, NodeId
from maintenance.remote import (
    REMOTE_PROTOCOL_VERSION,
    RemoteAuthError,
    RemoteProtocolError,
    parse_hello_capabilities,
    sign_response,
    validate_hello_payload,
    verify_response,
)

SECRET = "a" * 64


class RemoteCompatibilityTests(unittest.TestCase):
    def test_new_client_reads_old_peer_additive_process_and_thermal_fields(
        self,
    ) -> None:
        process = process_candidate_from_dict(
            {
                "pid": 7,
                "name": "old-app",
                "memory_bytes": 10,
                "memory_percent": 1.0,
                "cpu_percent": 2.0,
                "activity": "Active",
                "username": "user",
                "action_allowed": True,
                "create_time": 3.0,
            }
        )
        self.assertEqual(process.name, "old-app")
        summary = {
            "key": "cpu",
            "title": "CPU",
            "value": "10%",
            "subtitle": "running",
            "percent": 10.0,
            "details": ["CPU: 10%"],
            "actionable": False,
            "failed": False,
        }
        from maintenance.cluster import resource_summary_from_dict

        self.assertEqual(resource_summary_from_dict(summary).temperatures, ())

    def test_old_client_reads_new_peer_unknown_payload_fields(self) -> None:
        payload = {
            "schema_version": 1,
            "node_id": "peer",
            "display_name": "Peer",
            "hostname": "peer-host",
            "platform": "Linux",
            "status": "online",
            "capabilities": ["dashboard_read"],
            "scanned_at": "2026-09-10T00:00:00+00:00",
            "future_read_metadata": {"revision": 2},
        }
        self.assertEqual(node_snapshot_from_dict(payload).node_id, NodeId("peer"))

    def test_absent_capabilities_do_not_grant_anything(self) -> None:
        self.assertEqual(parse_hello_capabilities({}), frozenset())

    def test_unknown_capability_is_not_fabricated(self) -> None:
        hello = {"capabilities": ["dashboard_read", "future_action"]}
        self.assertEqual(
            parse_hello_capabilities(hello),
            frozenset({NodeCapability.DASHBOARD_READ}),
        )

    def test_unknown_privileged_operation_fails_closed(self) -> None:
        from maintenance.remote import validate_operation_params

        with self.assertRaises(RemoteProtocolError):
            validate_operation_params("future_privileged_action", {})

    def test_unsupported_protocol_version_is_rejected(self) -> None:
        with self.assertRaises(RemoteProtocolError):
            validate_hello_payload(
                {
                    "ok": True,
                    "node_id": "peer",
                    "identity_fingerprint": "fingerprint",
                    "protocol_version": "2",
                }
            )

    def test_missing_or_malformed_security_identity_fails_closed(self) -> None:
        base = {
            "ok": True,
            "node_id": "peer",
            "protocol_version": REMOTE_PROTOCOL_VERSION,
        }
        with self.assertRaises(RemoteAuthError):
            validate_hello_payload(base)
        with self.assertRaises(RemoteAuthError):
            validate_hello_payload({**base, "identity_fingerprint": 42})

    def test_unknown_response_envelope_fields_are_rejected(self) -> None:
        response = sign_response(
            node_id="peer",
            request_id="request",
            status="ok",
            payload={"ok": True, "future_read_metadata": True},
            timestamp=100.0,
            secret=SECRET,
        )
        response["future_envelope_field"] = True
        with self.assertRaises(RemoteProtocolError):
            verify_response(
                response,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=60.0,
            )

    def test_missing_permissions_and_malformed_permissions_deny(self) -> None:
        record = {
            "node_id": "peer",
            "display_name": "Peer",
            "hostname": "peer-host",
            "host": "",
            "secret": SECRET,
            "capabilities": ["dashboard_read", "future_capability"],
            "future_read_metadata": "ignored",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            path.write_text(
                json.dumps({"schema_version": 1, "trusted_nodes": [record]}),
                encoding="utf-8",
            )
            loaded = ClusterStore(path).load().trusted_nodes[0]
        self.assertEqual(loaded.permissions, frozenset())
        self.assertEqual(loaded.capabilities, {NodeCapability.DASHBOARD_READ})
        self.assertEqual(loaded.host, "")

        record["permissions"] = ["dashboard_read", "future_privileged_permission"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            path.write_text(
                json.dumps({"schema_version": 1, "trusted_nodes": [record]}),
                encoding="utf-8",
            )
            self.assertEqual(
                ClusterStore(path).load().trusted_nodes[0].permissions,
                frozenset(),
            )


if __name__ == "__main__":
    unittest.main()
