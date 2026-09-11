"""Authenticated remote read contract tests (memory + loopback socket)."""

import json
import socket
import threading
import time
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

from maintenance.cluster import (
    ClusterDataError,
    node_snapshot_to_dict,
    process_action_result_from_dict,
    process_action_result_to_dict,
    resource_summary_to_dict,
    trusted_node_record,
)
from maintenance.components.temperature import temperature_sample_to_dict
from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    FileCandidate,
    ProcessActionResult,
    ProcessCandidate,
    ResourceSummary,
)
from maintenance.nodes import (
    NodeCapability,
    NodeId,
    NodePermission,
    NodeSnapshot,
    NodeStatus,
    ProcessActionKind,
    ProcessRef,
    ProcessTerminationRequest,
)
from maintenance.remote import (
    DEFAULT_FRESHNESS_SECONDS,
    MAX_ENVELOPE_BYTES,
    READ_CAPABILITIES,
    AuthenticatedNodeProvider,
    MemoryRemoteTransport,
    PeerGrant,
    RemoteAuthError,
    RemoteAuthorizationError,
    RemoteExecutionError,
    RemoteProtocolError,
    RemoteService,
    RemoteSocketServer,
    RemoteTransportError,
    RemoteUnavailableError,
    ReplayCache,
    SocketRemoteTransport,
    _recv_frame,
    _send_frame,
    build_trusted_transport,
    sign_request,
    sign_response,
    verify_request,
)
from tests.support.models import make_file_candidate, make_snapshot, make_summary
from tests.support.temperature import make_temperature_sample

SECRET = "a" * 64


class TrustedTransportTests(unittest.TestCase):
    def test_build_trusted_transport_requires_persisted_tls_pin(self) -> None:
        record = trusted_node_record(
            node_id="peer-a",
            display_name="Peer A",
            hostname="peer-a",
            host="192.0.2.10",
            port=5000,
            transport_fingerprint="aa",
        )
        transport_cls = Mock()

        build_trusted_transport(record, transport_cls=transport_cls)

        transport_cls.assert_called_once_with(
            "192.0.2.10", 5000, expected_fingerprint="aa"
        )

    def test_invalidated_provider_rejects_requests_idempotently(self) -> None:
        transport = Mock()
        provider = AuthenticatedNodeProvider(
            node_id=NodeId("peer-a"),
            secret=SECRET,
            transport=transport,
        )

        provider.invalidate()
        provider.invalidate()

        with self.assertRaises(RemoteAuthError):
            provider.hello()
        transport.request.assert_not_called()

    def test_build_trusted_transport_rejects_incomplete_trust_record(self) -> None:
        record = trusted_node_record(
            node_id="peer-a",
            display_name="Peer A",
            hostname="peer-a",
            host="192.0.2.10",
            port=5000,
            transport_fingerprint="aa",
        )
        for invalid in (
            replace(record, host=""),
            replace(record, port=None),
            replace(record, transport_fingerprint=None),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(RemoteAuthError):
                build_trusted_transport(invalid, transport_cls=Mock)


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


class FakeProvider:
    def dashboard_snapshot(
        self,
        cancel_event=None,
        progress_callback=None,
    ) -> DashboardSnapshot:
        return make_snapshot(
            make_summary(
                "cpu",
                "CPU",
                value="10%",
                subtitle="running",
                percent=10.0,
                details=("CPU: 10%",),
                capability=CapabilityState.SUPPORTED,
                temperatures=(make_temperature_sample("cpu", 45.0),),
            ),
            system_label="peer-host",
            scanned_at=_now(),
        )

    def component_summary(self, key, cancel_event=None) -> ResourceSummary:
        return make_summary(
            key,
            key.upper(),
            value="5%",
            subtitle="ok",
            percent=5.0,
            details=(f"{key.upper()}: 5%",),
            capability=CapabilityState.SUPPORTED,
            temperatures=(make_temperature_sample(key, 45.0),),
        )

    def process_candidates(self, cancel_event=None) -> list[ProcessCandidate]:
        return [ProcessCandidate(1, "app", 100, 1.0, 2.0, "Active", "user", True, 1.5)]

    def storage_candidates(
        self,
        progress_callback=None,
        cancel_event=None,
    ) -> list[FileCandidate]:
        return [make_file_candidate(Path("/tmp/x"), modified_at=_now(), reason="reason")]


def _service(
    provider=None,
    capabilities=READ_CAPABILITIES,
    secret=SECRET,
    permissions=None,
) -> RemoteService:
    return RemoteService(
        node_id=NodeId("peer"),
        display_name="Peer",
        hostname="peer-host",
        platform="Linux",
        status=NodeStatus.ONLINE,
        capabilities=frozenset(capabilities),
        provider=provider or FakeProvider(),
        secret=secret,
        app_version="1.2.4.0",
        permissions=permissions,
    )


def _client(service, secret=SECRET) -> AuthenticatedNodeProvider:
    return AuthenticatedNodeProvider(
        node_id=NodeId("peer"),
        secret=secret,
        transport=MemoryRemoteTransport(service),
    )


class SigningAndVerificationTests(unittest.TestCase):
    def test_signed_request_verifies(self) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
            timestamp=100.0,
            secret=SECRET,
        )
        request = verify_request(
            envelope,
            secret=SECRET,
            clock=lambda: 100.0,
            freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
            replay_cache=ReplayCache(),
        )
        self.assertEqual(request.op, "hello")

    def test_tampered_signature_is_rejected(self) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
            timestamp=100.0,
            secret=SECRET,
        )
        envelope["params"] = {"key": "evil"}
        with self.assertRaises(RemoteAuthError):
            verify_request(
                envelope,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
                replay_cache=ReplayCache(),
            )

    def test_wrong_secret_is_rejected(self) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
            timestamp=100.0,
            secret="b" * 64,
        )
        with self.assertRaises(RemoteAuthError):
            verify_request(
                envelope,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
                replay_cache=ReplayCache(),
            )

    def test_replayed_request_is_rejected(self) -> None:
        cache = ReplayCache(clock=lambda: 100.0)
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
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

    def test_stale_timestamp_is_rejected(self) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
            timestamp=10.0,
            secret=SECRET,
        )
        with self.assertRaises(RemoteAuthError):
            verify_request(
                envelope,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
                replay_cache=ReplayCache(),
            )

    def test_unknown_request_fields_are_rejected(self) -> None:
        envelope = sign_request(
            node_id="peer",
            op="hello",
            params={},
            request_id="r1",
            nonce="n1",
            timestamp=100.0,
            secret=SECRET,
        )
        envelope["unexpected"] = True
        with self.assertRaises(RemoteProtocolError):
            verify_request(
                envelope,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
                replay_cache=ReplayCache(),
            )


class RemoteServiceRoundTripTests(unittest.TestCase):
    def test_signed_dashboard_drops_invalid_samples_and_preserves_resources(self) -> None:
        class ThermalProvider(FakeProvider):
            def dashboard_snapshot(self, cancel_event=None, progress_callback=None):
                dashboard = super().dashboard_snapshot(cancel_event, progress_callback)
                return DashboardSnapshot(
                    system_label=dashboard.system_label,
                    scanned_at=dashboard.scanned_at,
                    resources=(
                        dashboard.get("cpu"),
                        make_summary(
                            "storage",
                            "Storage",
                            value="38°C",
                            subtitle="healthy",
                            capability=CapabilityState.SUPPORTED,
                            temperatures=(make_temperature_sample("storage", 38.0),),
                        ),
                    ),
                )

        service = _service(provider=ThermalProvider())
        memory_transport = MemoryRemoteTransport(service)

        class InvalidSampleTransport:
            def __init__(self) -> None:
                self._dashboard_requests = 0

            def request(self, envelope_text: str, cancel_event=None) -> str:
                response = json.loads(memory_transport.request(envelope_text, cancel_event))
                request = json.loads(envelope_text)
                if request["op"] != "dashboard_snapshot" or self._dashboard_requests:
                    return json.dumps(response)
                self._dashboard_requests += 1
                snapshot = response["payload"]["snapshot"]
                resources = snapshot["dashboard"]["resources"]
                cpu = next(resource for resource in resources if resource["key"] == "cpu")
                valid = temperature_sample_to_dict(make_temperature_sample("cpu", 45.0))
                samples = [
                    valid,
                    {**valid, "value_celsius": 0.1},
                    {**valid, "value_celsius": 249.9},
                    {**valid, "value_celsius": 0},
                    {**valid, "value_celsius": 250},
                    {**valid, "value_celsius": float("nan")},
                    {**valid, "value_celsius": float("inf")},
                    {**valid, "value_celsius": float("-inf")},
                    {**valid, "value_celsius": 10**1000},
                    {**valid, "value_celsius": -1000},
                    {**valid, "value_celsius": "45"},
                    {key: value for key, value in valid.items() if key != "sensor_id"},
                    {key: value for key, value in valid.items() if key != "sensor_name"},
                ]
                cpu["temperatures"] = samples
                response = sign_response(
                    node_id=response["node_id"],
                    request_id=response["request_id"],
                    status=response["status"],
                    payload=response["payload"],
                    timestamp=response["ts"],
                    secret=SECRET,
                    error=response["error"],
                )
                return json.dumps(response)

        client = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            secret=SECRET,
            transport=InvalidSampleTransport(),
        )

        first = client.dashboard_snapshot()
        cpu = first.get("cpu")
        storage = first.get("storage")
        self.assertEqual(
            tuple(sample.value_celsius for sample in cpu.temperatures),
            (45.0, 0.1, 249.9),
        )
        self.assertEqual(storage.title, "Storage")
        self.assertEqual(storage.temperatures[0].value_celsius, 38.0)

        second = client.dashboard_snapshot()
        self.assertEqual(second.get("cpu").temperatures[0].value_celsius, 45.0)

    def test_remote_cleanup_rejects_arbitrary_path(self) -> None:
        request = sign_request(
            node_id="peer",
            op="cleanup",
            params={"path": "/etc/passwd"},
            request_id="arbitrary-path",
            nonce="arbitrary-path-nonce",
            timestamp=time.time(),
            secret=SECRET,
        )

        with self.assertRaises(RemoteProtocolError):
            _service().handle(json.dumps(request))

    def test_process_action_requires_matching_allowlisted_kind(self) -> None:
        request = sign_request(
            node_id="peer",
            op="process_request_quit",
            params={"processes": [{"pid": 42}], "action": "kill"},
            request_id="bad-action",
            nonce="bad-action-nonce",
            timestamp=time.time(),
            secret=SECRET,
        )
        service = _service(
            capabilities=frozenset({NodeCapability.PROCESS_TERMINATION}),
            permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
        )
        with self.assertRaises(RemoteProtocolError):
            service.handle(json.dumps(request))

    def test_process_action_requires_create_time(self) -> None:
        request = sign_request(
            node_id="peer",
            op="process_request_quit",
            params={"processes": [{"pid": 42}], "action": "request_quit"},
            request_id="missing-create-time",
            nonce="missing-create-time-nonce",
            timestamp=time.time(),
            secret=SECRET,
        )
        service = _service(
            capabilities=frozenset({NodeCapability.PROCESS_TERMINATION}),
            permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
        )
        with self.assertRaises(RemoteProtocolError):
            service.handle(json.dumps(request))

    def test_same_destructive_request_id_is_rejected_with_fresh_nonce(self) -> None:
        class FakeProcessManager:
            def request_quit(self, pids, create_times):
                return ProcessActionResult(len(pids), tuple(pids), (), ())

        service = RemoteService(
            node_id=NodeId("peer"),
            display_name="Peer",
            hostname="peer-host",
            platform="Linux",
            status=NodeStatus.ONLINE,
            capabilities=frozenset({NodeCapability.PROCESS_TERMINATION}),
            permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
            provider=FakeProvider(),
            process_manager=FakeProcessManager(),
            secret=SECRET,
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
        with self.assertRaises(RemoteAuthError):
            service.handle(json.dumps(second))

    def test_offline_target_denies_before_manager(self) -> None:
        class Manager:
            def terminate(self, _request):
                raise AssertionError("offline target must not invoke the manager")

        service = RemoteService(
            node_id=NodeId("peer"),
            display_name="Peer",
            hostname="peer-host",
            platform="Linux",
            status=NodeStatus.OFFLINE,
            capabilities=frozenset({NodeCapability.PROCESS_TERMINATION}),
            permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
            provider=FakeProvider(),
            process_manager=Manager(),
            secret=SECRET,
        )
        with self.assertRaises(RemoteUnavailableError):
            _client(service).request_quit([{"pid": 42, "create_time": 10.5}])

    def test_typed_request_rejects_a_different_target(self) -> None:
        request = ProcessTerminationRequest(
            target_node_id=NodeId("other"),
            processes=(ProcessRef(NodeId("other"), 42, 10.5),),
            action=ProcessActionKind.REQUEST_QUIT,
        )
        with self.assertRaises(RemoteAuthError):
            _client(_service()).terminate(request)

    def test_inner_snapshot_target_mismatch_is_rejected(self) -> None:
        class WrongSnapshotTransport:
            def request(self, envelope_text: str) -> str:
                envelope = json.loads(envelope_text)
                snapshot = NodeSnapshot(
                    node_id=NodeId("other"),
                    display_name="Other",
                    hostname="other-host",
                    platform="Linux",
                    status=NodeStatus.ONLINE,
                    capabilities=frozenset(),
                    scanned_at=_now(),
                    dashboard=FakeProvider().dashboard_snapshot(),
                )
                return json.dumps(
                    sign_response(
                        node_id="peer",
                        request_id=envelope["request_id"],
                        status="ok",
                        payload={"snapshot": node_snapshot_to_dict(snapshot)},
                        timestamp=time.time(),
                        secret=SECRET,
                    )
                )

        client = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            secret=SECRET,
            transport=WrongSnapshotTransport(),
        )

        with self.assertRaises(RemoteAuthError):
            client.node_snapshot()

    def test_hello_returns_ok(self) -> None:
        client = _client(_service())
        result = client.hello()
        self.assertTrue(result["ok"])
        self.assertEqual(result["node_id"], "peer")

    def test_dashboard_snapshot_round_trip(self) -> None:
        client = _client(_service())
        snapshot = client.dashboard_snapshot()
        self.assertEqual(snapshot.system_label, "peer-host")
        self.assertEqual(snapshot.get("cpu").value, "10%")

    def test_node_snapshot_round_trip_preserves_target_metadata(self) -> None:
        client = _client(_service())
        snapshot = client.node_snapshot()
        self.assertIsInstance(snapshot, NodeSnapshot)
        self.assertEqual(snapshot.node_id, NodeId("peer"))
        self.assertEqual(snapshot.display_name, "Peer")
        dashboard = snapshot.dashboard
        self.assertIsNotNone(dashboard)
        assert dashboard is not None
        self.assertEqual(dashboard.get("cpu").value, "10%")

    def test_component_summary_round_trip(self) -> None:
        client = _client(_service())
        resource = client.component_summary("cpu")
        self.assertEqual(resource.title, "CPU")
        self.assertEqual(resource.temperatures[0].value_celsius, 45.0)

    def test_component_summary_rejects_wrong_target_metadata(self) -> None:
        class WrongTargetTransport:
            def request(self, envelope_text: str) -> str:
                envelope = json.loads(envelope_text)
                resource = FakeProvider().component_summary("cpu")
                return json.dumps(
                    sign_response(
                        node_id="peer",
                        request_id=envelope["request_id"],
                        status="ok",
                        payload={
                            "node_id": "other",
                            "resource": resource_summary_to_dict(resource),
                        },
                        timestamp=100.0,
                        secret=SECRET,
                    )
                )

        client = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            secret=SECRET,
            transport=WrongTargetTransport(),
            clock=lambda: 100.0,
        )
        with self.assertRaises(RemoteAuthError):
            client.component_summary("cpu")

    def test_process_candidates_round_trip(self) -> None:
        client = _client(_service())
        processes = client.process_candidates()
        self.assertEqual(len(processes), 1)
        self.assertEqual(processes[0].name, "app")

    def test_storage_candidates_round_trip(self) -> None:
        client = _client(_service())
        files = client.storage_candidates()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, Path("/tmp/x"))

    def test_wrong_client_secret_is_rejected(self) -> None:
        service = _service()
        client = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            secret="b" * 64,
            transport=MemoryRemoteTransport(service),
        )
        with self.assertRaises(RemoteAuthError):
            client.hello()

    def test_response_from_wrong_node_is_rejected(self) -> None:
        class WrongNodeTransport:
            def request(self, envelope_text: str) -> str:
                envelope = json.loads(envelope_text)
                return json.dumps(
                    sign_response(
                        node_id="other",
                        request_id=envelope["request_id"],
                        status="ok",
                        payload={"ok": True},
                        timestamp=100.0,
                        secret=SECRET,
                    )
                )

        client = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            secret=SECRET,
            transport=WrongNodeTransport(),
        )
        with self.assertRaises(RemoteAuthError):
            client.hello()

    def test_unauthorized_operation_is_rejected(self) -> None:
        service = _service(capabilities=frozenset({NodeCapability.DASHBOARD_READ}))
        client = _client(service)
        with self.assertRaises(RemoteAuthorizationError):
            client.component_summary("cpu")

    def test_permission_is_enforced_below_the_ui(self) -> None:
        service = _service(
            capabilities=READ_CAPABILITIES,
        )
        service = RemoteService(
            node_id=NodeId("peer"),
            display_name="Peer",
            hostname="peer-host",
            platform="Linux",
            status=NodeStatus.ONLINE,
            capabilities=READ_CAPABILITIES,
            permissions=frozenset({NodePermission.DASHBOARD_READ}),
            provider=FakeProvider(),
            secret=SECRET,
        )
        client = _client(service)
        with self.assertRaises(RemoteAuthorizationError):
            client.process_candidates()

    def test_process_action_is_target_bound_and_permission_checked(self) -> None:
        class FakeProcessManager:
            def request_quit(self, pids, create_times):
                self.called = (pids, create_times)
                return ProcessActionResult(1, (pids[0],), (), ())

        manager = FakeProcessManager()
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
            provider=FakeProvider(),
            process_manager=manager,
            secret=SECRET,
        )
        client = _client(service)
        result = client.request_quit([{"pid": 42, "create_time": 10.5}])
        self.assertEqual(result.stopped, (42,))
        self.assertEqual(manager.called, ([42], {42: 10.5}))

    def test_target_can_bind_authenticated_secret_to_caller_identity(self) -> None:
        service = RemoteService(
            node_id=NodeId("target"),
            expected_caller_id=NodeId("caller"),
            display_name="Target",
            hostname="target-host",
            platform="Linux",
            status=NodeStatus.ONLINE,
            capabilities=frozenset({NodeCapability.DASHBOARD_READ}),
            permissions=frozenset({NodePermission.DASHBOARD_READ}),
            provider=FakeProvider(),
            secret=SECRET,
        )
        request = sign_request(
            node_id="target",
            caller_node_id="wrong-caller",
            op="hello",
            params={},
            request_id="caller-test",
            nonce="caller-test-nonce",
            timestamp=time.time(),
            secret=SECRET,
        )
        with self.assertRaises(RemoteAuthError):
            service.handle(json.dumps(request))

    def test_target_grants_are_per_caller_and_sign_denials(self) -> None:
        service = RemoteService(
            node_id=NodeId("target"),
            display_name="Target",
            hostname="target-host",
            platform="Linux",
            status=NodeStatus.ONLINE,
            capabilities=READ_CAPABILITIES,
            provider=FakeProvider(),
            secret=SECRET,
            grants={
                NodeId("caller-a"): PeerGrant(
                    NodeId("caller-a"),
                    SECRET,
                    frozenset({NodePermission.DASHBOARD_READ}),
                ),
                NodeId("caller-b"): PeerGrant(
                    NodeId("caller-b"),
                    "b" * 64,
                    frozenset({NodePermission.PROCESS_REVIEW}),
                ),
            },
        )
        client = AuthenticatedNodeProvider(
            node_id=NodeId("target"),
            caller_node_id=NodeId("caller-a"),
            secret=SECRET,
            transport=MemoryRemoteTransport(service),
        )
        with self.assertRaises(RemoteAuthorizationError):
            client.process_candidates()

    def test_two_installations_require_target_owned_grant_before_activation(
        self,
    ) -> None:
        target = _service()
        caller_secret = "c" * 64
        caller = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            caller_node_id=NodeId("caller"),
            secret=caller_secret,
            transport=MemoryRemoteTransport(target),
        )

        with self.assertRaises(RemoteAuthError):
            caller.hello()

        target.update_grants(
            {
                NodeId("caller"): PeerGrant(
                    caller_node_id=NodeId("caller"),
                    secret=caller_secret,
                    permissions=frozenset({NodePermission.DASHBOARD_READ}),
                )
            }
        )

        self.assertTrue(caller.hello()["ok"])

    def test_unknown_operation_is_rejected(self) -> None:
        service = _service()
        with self.assertRaises(RemoteProtocolError):
            service.handle('{"v": "1"}')

    def test_request_for_a_different_target_identity_is_rejected(self) -> None:
        service = _service()
        request = sign_request(
            node_id="other-target",
            op="hello",
            params={},
            request_id="target-test",
            nonce="target-test-nonce",
            timestamp=time.time(),
            secret=SECRET,
        )
        with self.assertRaises(RemoteAuthError):
            service.handle(json.dumps(request))

    def test_response_with_non_object_payload_is_rejected(self) -> None:
        from maintenance.remote import verify_response

        response = sign_response(
            node_id="peer",
            request_id="payload-test",
            status="ok",
            payload=cast(Any, ["not", "an", "object"]),
            timestamp=100.0,
            secret=SECRET,
        )
        with self.assertRaises(RemoteProtocolError):
            verify_response(
                response,
                secret=SECRET,
                clock=lambda: 100.0,
                freshness_seconds=DEFAULT_FRESHNESS_SECONDS,
            )

    def test_malformed_remote_json_is_rejected_as_protocol_error(self) -> None:
        class MalformedTransport:
            def request(self, _envelope_text: str) -> str:
                return "not-json"

        client = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            secret=SECRET,
            transport=MalformedTransport(),
        )
        with self.assertRaises(RemoteProtocolError):
            client.hello()

    def test_execution_failure_returns_signed_error(self) -> None:
        class BoomProvider(FakeProvider):
            def process_candidates(self, cancel_event=None):
                raise RuntimeError("boom")

        service = _service(provider=BoomProvider())
        client = _client(service)
        with self.assertRaises(RemoteExecutionError):
            client.process_candidates()

    def test_read_only_noop_helpers(self) -> None:
        client = _client(_service())
        client.reset_component_sample("cpu")
        client.stop_background_workers()

    def test_cancelled_request_raises_before_send(self) -> None:
        import threading

        client = _client(_service())
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(RemoteExecutionError):
            client.dashboard_snapshot(cancel_event=cancel)


class SocketTransportTests(unittest.TestCase):
    def test_frame_helpers_handle_fragmented_header_and_body(self) -> None:
        class FragmentedSocket:
            def __init__(self, chunks):
                self.chunks = list(chunks)
                self.sent = []

            def recv(self, _length):
                chunk = self.chunks.pop(0)
                if len(chunk) <= _length:
                    return chunk
                self.chunks.insert(0, chunk[_length:])
                return chunk[:_length]

            def sendall(self, payload):
                self.sent.append(payload)

        sender = FragmentedSocket([])
        _send_frame(sender, b"hello", max_bytes=10)
        wire = sender.sent[0]
        receiver = FragmentedSocket([wire[:1], wire[1:3], wire[3:5], wire[5:]])

        self.assertEqual(
            _recv_frame(
                receiver,
                max_bytes=10,
                closed_message="connection closed before request",
            ),
            b"hello",
        )

    def test_frame_helpers_reject_oversized_payloads(self) -> None:
        from maintenance.remote import RemoteTransportError

        sender = type("Sender", (), {"sendall": lambda self, _payload: None})()
        with self.assertRaises(RemoteTransportError):
            _send_frame(sender, b"1234", max_bytes=3)

        receiver = type(
            "Receiver",
            (),
            {"recv": lambda self, _length: b"\x00\x00\x00\x04"},
        )()
        with self.assertRaises(RemoteTransportError):
            _recv_frame(
                receiver,
                max_bytes=3,
                closed_message="connection closed before request",
            )

    def test_frame_receive_cancellation_is_checked_after_timeout(self) -> None:
        cancel_event = threading.Event()

        class TimeoutThenCancelSocket:
            def recv(self, _length):
                cancel_event.set()
                raise TimeoutError

        with self.assertRaises(RemoteExecutionError):
            _recv_frame(
                TimeoutThenCancelSocket(),
                max_bytes=10,
                closed_message="connection closed before response",
                cancel_event=cancel_event,
            )

    def test_loopback_socket_round_trip(self) -> None:
        service = _service()
        server = RemoteSocketServer(service)
        server.start()
        try:
            port = server.bound_port
            self.assertIsNotNone(port)
            assert port is not None
            client = AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret=SECRET,
                transport=SocketRemoteTransport("127.0.0.1", port, timeout=10),
            )
            result = client.hello()
            self.assertTrue(result["ok"])
            snapshot = client.dashboard_snapshot()
            self.assertEqual(snapshot.get("cpu").value, "10%")
        finally:
            server.stop()

    def test_socket_server_bounds_concurrent_handlers_and_rejects_excess(self) -> None:
        entered = threading.Event()
        both_entered = threading.Event()
        release = threading.Event()
        state_lock = threading.Lock()
        active = 0
        maximum = 0

        class BlockingProvider(FakeProvider):
            def dashboard_snapshot(self, cancel_event=None, progress_callback=None):
                nonlocal active, maximum
                with state_lock:
                    active += 1
                    maximum = max(maximum, active)
                    entered.set()
                    if active == 2:
                        both_entered.set()
                release.wait(2)
                with state_lock:
                    active -= 1
                return super().dashboard_snapshot(cancel_event, progress_callback)

        server = RemoteSocketServer(
            _service(provider=BlockingProvider()),
            timeout=2,
            max_active_handlers=2,
        )
        server.start()
        workers: list[threading.Thread] = []
        errors: list[BaseException] = []
        try:
            port = server.bound_port
            assert port is not None

            def run_client(index: int) -> None:
                try:
                    request = json.dumps(
                        sign_request(
                            node_id="peer",
                            op="dashboard_snapshot",
                            params={},
                            request_id=f"bounded-request-{index}",
                            nonce=f"bounded-nonce-{index}",
                            timestamp=time.time(),
                            secret=SECRET,
                        )
                    ).encode("utf-8")
                    with socket.create_connection(
                        ("127.0.0.1", port), timeout=2
                    ) as sock:
                        _send_frame(sock, request, max_bytes=MAX_ENVELOPE_BYTES)
                        _recv_frame(
                            sock,
                            max_bytes=MAX_ENVELOPE_BYTES,
                            closed_message="connection closed before response",
                        )
                except Exception as error:  # noqa: BLE001 - report worker failures.
                    errors.append(error)

            for index in range(2):
                worker = threading.Thread(target=run_client, args=(index,))
                workers.append(worker)
                worker.start()
            self.assertTrue(entered.wait(1))
            self.assertTrue(both_entered.wait(1))
            request = json.dumps(
                sign_request(
                    node_id="peer",
                    op="dashboard_snapshot",
                    params={},
                    request_id="bounded-request-excess",
                    nonce="bounded-nonce-excess",
                    timestamp=time.time(),
                    secret=SECRET,
                )
            ).encode("utf-8")
            with socket.create_connection(("127.0.0.1", port), timeout=2) as excess:
                _send_frame(excess, request, max_bytes=MAX_ENVELOPE_BYTES)
                excess.settimeout(1)
                try:
                    received = excess.recv(1)
                except ConnectionResetError:
                    received = b""
                self.assertEqual(received, b"")
            with state_lock:
                self.assertEqual(maximum, 2)
        finally:
            release.set()
            for worker in workers:
                worker.join(2)
            server.stop()
        self.assertFalse(errors)

    def test_socket_server_shutdown_releases_handler_permits(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        class BlockingProvider(FakeProvider):
            def dashboard_snapshot(self, cancel_event=None, progress_callback=None):
                entered.set()
                release.wait(2)
                return super().dashboard_snapshot(cancel_event, progress_callback)

        server = RemoteSocketServer(
            _service(provider=BlockingProvider()),
            timeout=2,
            max_active_handlers=1,
        )
        server.start()
        port = server.bound_port
        assert port is not None
        worker = threading.Thread(
            target=lambda: AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret=SECRET,
                transport=SocketRemoteTransport("127.0.0.1", port, timeout=2),
            ).dashboard_snapshot()
        )
        worker.start()
        self.assertTrue(entered.wait(1))
        try:
            server.stop()
        finally:
            release.set()
            worker.join(2)
        self.assertIsNotNone(server._admission)
        assert server._admission is not None
        self.assertEqual(server._admission._value, 1)

    def test_connection_refused_maps_to_transport_error(self) -> None:
        from maintenance.remote import RemoteTransportError

        client = AuthenticatedNodeProvider(
            node_id=NodeId("peer"),
            secret=SECRET,
            transport=SocketRemoteTransport("127.0.0.1", _free_port(), timeout=2),
        )
        with self.assertRaises(RemoteTransportError):
            client.hello()

    def test_wrong_secret_over_socket_is_rejected(self) -> None:
        service = _service()
        server = RemoteSocketServer(service)
        server.start()
        try:
            port = server.bound_port
            assert port is not None
            client = AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret="b" * 64,
                transport=SocketRemoteTransport("127.0.0.1", port, timeout=10),
            )
            with self.assertRaises((RemoteAuthError, RemoteTransportError)):
                client.hello()
        finally:
            server.stop()


class ProcessActionCodecTests(unittest.TestCase):
    def test_process_action_codec_round_trip(self) -> None:
        result = ProcessActionResult(3, (42,), (43,), ("denied",))

        self.assertEqual(
            process_action_result_from_dict(process_action_result_to_dict(result)),
            result,
        )

    def test_process_action_codec_rejects_missing_or_non_object_payload(self) -> None:
        payloads: tuple[object, ...] = (None, [], {"requested": 1})
        for payload in payloads:
            with self.assertRaises(ClusterDataError):
                process_action_result_from_dict(payload)

    def test_process_action_codec_rejects_coercion_and_invariant_violations(
        self,
    ) -> None:
        payloads: tuple[object, ...] = (
            {"requested": True, "stopped": [], "force_required": [], "errors": []},
            {"requested": 1, "stopped": ["42"], "force_required": [], "errors": []},
            {"requested": -1, "stopped": [], "force_required": [], "errors": []},
            {"requested": 1, "stopped": [42, 42], "force_required": [], "errors": []},
            {"requested": 1, "stopped": [42], "force_required": [42], "errors": []},
            {"requested": 0, "stopped": [42], "force_required": [], "errors": []},
            {"requested": 1, "stopped": [], "force_required": [], "errors": [42]},
        )
        for payload in payloads:
            with self.assertRaises(ClusterDataError):
                process_action_result_from_dict(payload)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    unittest.main()
