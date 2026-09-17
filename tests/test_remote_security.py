"""TLS material and pinned peer transport tests."""

import json
import ssl
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from maintenance.cluster import (
    ClusterState,
    ClusterStore,
    PeerGrantRecord,
    PendingPairing,
)
from maintenance.nodes import NodeId, NodePermission
from maintenance.remote import (
    AuthenticatedNodeProvider,
    CapabilityElevationRequest,
    MemoryRemoteTransport,
    RemoteAuthError,
    RemoteSocketServer,
    TLSRemoteTransport,
)
from maintenance.remote_security import (
    certificate_fingerprint,
    ensure_tls_material,
    server_context,
)
from maintenance.remote_support.protocol import (
    PairingControlRequest,
    RemoteProtocolError,
    validate_pairing_control_request,
)
from maintenance.remote_support.server import (
    _handle_elevation_request,
    _handle_pair_abort,
    _handle_pair_confirm,
    _handle_pairing_request,
)
from maintenance.ui import window_discovery as ui_window_discovery
from tests.test_remote_contract import SECRET, _service


def _pairing_state(
    *, pending_pairings: tuple[PendingPairing, ...] | None = None
) -> ClusterState:
    pending = (
        pending_pairings
        if pending_pairings is not None
        else (
            PendingPairing(
                "tx-1",
                "caller",
                "caller-id",
                "caller-tls",
                "b" * 64,
                frozenset({NodePermission.DASHBOARD_READ}),
                time.time() + 300.0,
            ),
        )
    )
    return ClusterState(
        peer_grants=(
            PeerGrantRecord(
                "caller", "a" * 64, frozenset({NodePermission.DASHBOARD_READ})
            ),
        )
        if pending_pairings is not None
        else (),
        pending_pairings=pending,
    )


def _pairing_controller(state: ClusterState, *, save_result: bool = True) -> Any:
    controller: Any = type("Controller", (), {})()
    controller._cluster_state = state
    controller.master = object()
    controller._submit_ui = lambda callback: callback()

    def save(updated: ClusterState) -> bool:
        if save_result:
            controller._cluster_state = updated
        return save_result

    controller._save_cluster_state = save
    return controller


def _control_request(
    pending: PendingPairing, *, operation: str
) -> PairingControlRequest:
    return PairingControlRequest(
        operation=operation,
        transaction_id=pending.transaction_id,
        caller_node_id=NodeId(pending.caller_node_id),
        identity_fingerprint=pending.identity_fingerprint,
        transport_fingerprint=pending.transport_fingerprint,
        secret=pending.secret,
        permissions=pending.permissions,
        expires_at=pending.expires_at,
    )


class RemoteSecurityTests(unittest.TestCase):
    def test_old_cluster_json_preserves_active_grants_and_defaults_pending(
        self,
    ) -> None:
        legacy = {
            "schema_version": 1,
            "local_node_id": "legacy-local",
            "trusted_nodes": [],
            "peer_grants": [
                {
                    "caller_node_id": "legacy-peer",
                    "secret": "a" * 64,
                    "permissions": [NodePermission.DASHBOARD_READ.value],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cluster.json"
            path.write_text(json.dumps(legacy))
            state = ClusterStore(path).load()

        grant = state.grant("legacy-peer")
        self.assertIsNotNone(grant)
        assert grant is not None
        self.assertEqual(grant.secret, "a" * 64)
        self.assertEqual(state.pending_pairings, ())

    def test_malformed_pairing_permissions_are_denied(self) -> None:
        raw = {
            "op": "pair_request",
            "caller_node_id": "caller",
            "identity_fingerprint": "caller-id",
            "transport_fingerprint": "caller-tls",
            "secret": "b" * 64,
            "permissions": ["not-a-permission"],
        }

        response = json.loads(_handle_pairing_request(raw, lambda _request: True))

        self.assertFalse(response["approved"])

    def test_transactional_pairing_request_is_accepted_by_current_target(self) -> None:
        raw = {
            "op": "pair_request",
            "pairing_mode": "transactional",
            "caller_node_id": "caller",
            "identity_fingerprint": "caller-id",
            "transport_fingerprint": "caller-tls",
            "secret": "b" * 64,
            "permissions": [NodePermission.DASHBOARD_READ.value],
        }

        response = json.loads(
            _handle_pairing_request(
                raw,
                lambda _request: {
                    "approved": True,
                    "transaction_id": "tx-1",
                },
            )
        )

        self.assertEqual(response["transaction_id"], "tx-1")

    def test_legacy_pairing_request_shape_is_rejected_by_current_target(self) -> None:
        raw = {
            "op": "pair_request",
            "caller_node_id": "caller",
            "identity_fingerprint": "caller-id",
            "transport_fingerprint": "caller-tls",
            "secret": "b" * 64,
            "permissions": [NodePermission.DASHBOARD_READ.value],
        }

        response = json.loads(_handle_pairing_request(raw, lambda _request: True))

        self.assertFalse(response["approved"])

    def test_unknown_pairing_mode_is_rejected_by_current_target(self) -> None:
        raw = {
            "op": "pair_request",
            "pairing_mode": "legacy",
            "caller_node_id": "caller",
            "identity_fingerprint": "caller-id",
            "transport_fingerprint": "caller-tls",
            "secret": "b" * 64,
            "permissions": [NodePermission.DASHBOARD_READ.value],
        }

        response = json.loads(_handle_pairing_request(raw, lambda _request: True))

        self.assertFalse(response["approved"])

    def test_duplicate_transaction_ids_cannot_cross_callers(self) -> None:
        first = PendingPairing(
            "shared-tx",
            "caller-a",
            "id-a",
            "tls-a",
            "a" * 64,
            frozenset({NodePermission.DASHBOARD_READ}),
            time.time() + 300,
        )
        second = PendingPairing(
            "shared-tx",
            "caller-b",
            "id-b",
            "tls-b",
            "b" * 64,
            frozenset({NodePermission.DASHBOARD_READ}),
            time.time() + 300,
        )
        controller = _pairing_controller(ClusterState(pending_pairings=(first, second)))

        self.assertFalse(
            ui_window_discovery.handle_pairing_confirm(
                controller, _control_request(second, operation="pair_confirm")
            )
        )
        self.assertEqual(
            controller._cluster_state.pending_pairings,
            (first, second),
        )
        self.assertTrue(
            ui_window_discovery.handle_pairing_confirm(
                controller, _control_request(first, operation="pair_confirm")
            )
        )
        self.assertEqual(controller._cluster_state.grant("caller-a").secret, "a" * 64)

    def test_target_pairing_control_handlers_promote_and_abort_exact_pending_record(
        self,
    ) -> None:
        state = _pairing_state()
        controller = _pairing_controller(state)
        pending = state.pending_pairings[0]
        confirm = _control_request(pending, operation="pair_confirm")

        self.assertTrue(ui_window_discovery.handle_pairing_confirm(controller, confirm))
        self.assertEqual(controller._cluster_state.pending_pairings, ())
        self.assertEqual(
            controller._cluster_state.grant("caller").secret, pending.secret
        )
        self.assertTrue(ui_window_discovery.handle_pairing_confirm(controller, confirm))

        other = _pairing_state(pending_pairings=_pairing_state().pending_pairings)
        other_controller = _pairing_controller(other)
        self.assertTrue(
            ui_window_discovery.handle_pairing_abort(
                other_controller,
                _control_request(other.pending_pairings[0], operation="pair_abort"),
            )
        )
        self.assertEqual(len(other_controller._cluster_state.peer_grants), 1)
        self.assertFalse(
            ui_window_discovery.handle_pairing_abort(
                other_controller,
                _control_request(other.pending_pairings[0], operation="pair_abort"),
            )
        )

    def test_confirm_replay_succeeds_after_target_restart_without_changing_grant(
        self,
    ) -> None:
        state = _pairing_state()
        pending = state.pending_pairings[0]
        confirm = _control_request(pending, operation="pair_confirm")
        first_controller = _pairing_controller(state)

        self.assertTrue(
            ui_window_discovery.handle_pairing_confirm(first_controller, confirm)
        )
        completed_grant = first_controller._cluster_state.grant("caller")
        assert completed_grant is not None

        with tempfile.TemporaryDirectory() as directory:
            store = ClusterStore(Path(directory) / "cluster.json")
            store.save(first_controller._cluster_state)
            restored_controller = _pairing_controller(store.load())

            self.assertTrue(
                ui_window_discovery.handle_pairing_confirm(restored_controller, confirm)
            )

        self.assertEqual(
            restored_controller._cluster_state.grant("caller"), completed_grant
        )

    def test_confirm_without_pending_or_matching_active_grant_is_rejected(self) -> None:
        state = ClusterState()
        controller = _pairing_controller(state)
        request = PairingControlRequest(
            operation="pair_confirm",
            transaction_id="unknown-transaction",
            caller_node_id=NodeId("caller"),
            identity_fingerprint="caller-id",
            transport_fingerprint="caller-tls",
            secret="a" * 64,
            permissions=frozenset({NodePermission.DASHBOARD_READ}),
            expires_at=time.time() + 300.0,
        )

        self.assertFalse(
            ui_window_discovery.handle_pairing_confirm(controller, request)
        )
        self.assertEqual(controller._cluster_state.peer_grants, state.peer_grants)

    def test_target_confirm_save_failure_preserves_pending_and_active_grant(
        self,
    ) -> None:
        state = _pairing_state(pending_pairings=_pairing_state().pending_pairings)
        original_grant = state.peer_grants
        controller = _pairing_controller(state, save_result=False)

        self.assertFalse(
            ui_window_discovery.handle_pairing_confirm(
                controller,
                _control_request(state.pending_pairings[0], operation="pair_confirm"),
            )
        )
        self.assertEqual(
            controller._cluster_state.pending_pairings, state.pending_pairings
        )
        self.assertEqual(controller._cluster_state.peer_grants, original_grant)

    def test_concurrent_confirm_and_abort_have_one_winning_transition(self) -> None:
        state = _pairing_state()
        controller = _pairing_controller(state)
        pending = state.pending_pairings[0]
        confirm = _control_request(pending, operation="pair_confirm")
        abort = _control_request(pending, operation="pair_abort")
        interleave = threading.Barrier(2)
        original_save = controller._save_cluster_state

        def save(updated: ClusterState) -> bool:
            if updated.pending_pairings != state.pending_pairings:
                try:
                    interleave.wait(timeout=1.0)
                except threading.BrokenBarrierError:
                    pass
            return original_save(updated)

        controller._save_cluster_state = save
        results: dict[str, bool] = {}
        errors: list[BaseException] = []

        def run(operation: PairingControlRequest) -> None:
            try:
                results[operation.operation] = (
                    ui_window_discovery.handle_pairing_confirm
                    if operation.operation == "pair_confirm"
                    else ui_window_discovery.handle_pairing_abort
                )(controller, operation)
            except Exception as error:  # noqa: BLE001 - propagate thread failures.
                errors.append(error)

        threads = [
            threading.Thread(target=run, args=(confirm,)),
            threading.Thread(target=run, args=(abort,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2.0)

        self.assertEqual(errors, [])
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(sum(results.values()), 1)
        self.assertEqual(controller._cluster_state.pending_pairings, ())
        self.assertEqual(
            controller._cluster_state.grant("caller") is not None,
            results["pair_confirm"],
        )

    def test_target_confirm_rejects_binding_mismatch_and_expiry(self) -> None:
        state = _pairing_state()
        controller = _pairing_controller(state)
        pending = state.pending_pairings[0]

        self.assertFalse(
            ui_window_discovery.handle_pairing_confirm(
                controller,
                PairingControlRequest(
                    operation="pair_confirm",
                    transaction_id=pending.transaction_id,
                    caller_node_id=NodeId("caller"),
                    identity_fingerprint="wrong-id",
                    transport_fingerprint=pending.transport_fingerprint,
                    secret=pending.secret,
                    permissions=pending.permissions,
                    expires_at=pending.expires_at,
                ),
            )
        )
        self.assertEqual(controller._cluster_state.peer_grants, ())

        expired = PendingPairing(
            pending.transaction_id,
            pending.caller_node_id,
            pending.identity_fingerprint,
            pending.transport_fingerprint,
            pending.secret,
            pending.permissions,
            time.time() - 1.0,
        )
        expired_controller = _pairing_controller(
            _pairing_state(pending_pairings=(expired,))
        )
        self.assertFalse(
            ui_window_discovery.handle_pairing_confirm(
                expired_controller, _control_request(expired, operation="pair_confirm")
            )
        )
        self.assertEqual(len(expired_controller._cluster_state.peer_grants), 1)

    def test_expired_confirm_pruning_is_persisted(self) -> None:
        pending = PendingPairing(
            "tx-expired",
            "caller",
            "caller-id",
            "caller-tls",
            "b" * 64,
            frozenset({NodePermission.DASHBOARD_READ}),
            time.time() - 1.0,
        )
        with tempfile.TemporaryDirectory() as directory:
            store = ClusterStore(Path(directory) / "cluster.json")
            state = ClusterState(pending_pairings=(pending,))
            store.save(state)
            controller = _pairing_controller(state)

            def save(updated: ClusterState) -> bool:
                controller._cluster_state = updated
                store.save(updated)
                return True

            controller._save_cluster_state = save

            self.assertFalse(
                ui_window_discovery.handle_pairing_confirm(
                    controller, _control_request(pending, operation="pair_confirm")
                )
            )
            persisted = json.loads((Path(directory) / "cluster.json").read_text())

        self.assertEqual(persisted["pending_pairings"], [])

    def test_late_target_approval_does_not_persist_after_wait_expires(self) -> None:
        from maintenance.remote import PairingRequest

        class ExpiredWaitEvent:
            def wait(self, _timeout: float) -> bool:
                return False

            def set(self) -> None:
                pass

        state = _pairing_state(pending_pairings=())
        controller: Any = type("Controller", (), {})()
        controller._cluster_state = state
        controller.master = object()

        def submit_ui(callback: Any) -> None:
            controller.callback = callback

        def save(updated: ClusterState) -> bool:
            controller._cluster_state = updated
            return True

        controller._submit_ui = submit_ui
        controller._save_cluster_state = save
        request = PairingRequest(
            NodeId("late-caller"),
            "late-id",
            "late-tls",
            "c" * 64,
            frozenset({NodePermission.DASHBOARD_READ}),
        )

        with (
            patch.object(ui_window_discovery.threading, "Event", ExpiredWaitEvent),
            patch("window.messagebox.askyesno", return_value=True),
        ):
            response = ui_window_discovery.handle_pairing_request(controller, request)
            controller.callback()

        self.assertEqual(response, {"approved": False})
        self.assertEqual(controller._cluster_state.pending_pairings, ())

    def test_identical_approved_pairing_requests_reuse_live_transaction(self) -> None:
        from maintenance.remote import PairingRequest

        state = _pairing_state(pending_pairings=())
        controller = _pairing_controller(state)
        request = PairingRequest(
            NodeId("same-caller"),
            "same-id",
            "same-tls",
            "d" * 64,
            frozenset({NodePermission.DASHBOARD_READ}),
        )

        with patch("window.messagebox.askyesno", return_value=True) as approval:
            first = ui_window_discovery.handle_pairing_request(controller, request)
            second = ui_window_discovery.handle_pairing_request(controller, request)

        self.assertTrue(first["approved"])
        self.assertTrue(second["approved"])
        self.assertEqual(first["transaction_id"], second["transaction_id"])
        self.assertEqual(len(controller._cluster_state.pending_pairings), 1)
        self.assertEqual(approval.call_count, 2)

    def test_cancelled_pairing_request_does_not_dispatch_memory_transport(self) -> None:
        class Service:
            def __init__(self) -> None:
                self.calls = 0

            def handle(self, _envelope: str) -> str:
                self.calls += 1
                return json.dumps({"approved": False})

        service = Service()
        cancel_event = threading.Event()
        cancel_event.set()

        result = AuthenticatedNodeProvider.request_pairing(
            transport=MemoryRemoteTransport(service),
            caller_node_id=NodeId("caller"),
            identity_fingerprint="caller-id",
            transport_fingerprint="caller-tls",
            proposed_secret="a" * 64,
            permissions=frozenset({NodePermission.DASHBOARD_READ}),
            cancel_event=cancel_event,
        )

        self.assertFalse(result)
        self.assertEqual(service.calls, 0)

    def test_target_pairing_approval_returns_pending_transaction_without_grant(
        self,
    ) -> None:
        from maintenance.remote import PairingRequest

        state = _pairing_state(pending_pairings=())
        controller = _pairing_controller(state)
        request = PairingRequest(
            caller_node_id=NodeId("new-caller"),
            identity_fingerprint="new-id",
            transport_fingerprint="new-tls",
            proposed_secret="c" * 64,
            permissions=frozenset({NodePermission.DASHBOARD_READ}),
        )
        with patch("window.messagebox.askyesno", return_value=True):
            response = ui_window_discovery.handle_pairing_request(controller, request)

        self.assertTrue(response["approved"])
        self.assertIsNone(controller._cluster_state.grant("new-caller"))
        self.assertEqual(len(controller._cluster_state.pending_pairings), 1)
        self.assertEqual(
            response["transaction_id"],
            controller._cluster_state.pending_pairings[0].transaction_id,
        )

    def test_pairing_control_requires_exact_transaction_binding(self) -> None:
        raw = {
            "op": "pair_confirm",
            "transaction_id": "tx-1",
            "caller_node_id": "caller",
            "identity_fingerprint": "caller-id",
            "transport_fingerprint": "caller-tls",
            "secret": "b" * 64,
            "permissions": [NodePermission.DASHBOARD_READ.value],
            "expires_at": 101.0,
        }

        request = validate_pairing_control_request(raw, clock=lambda: 100.0)

        self.assertEqual(request.transaction_id, "tx-1")
        with self.assertRaises(RemoteProtocolError):
            validate_pairing_control_request(
                {**raw, "unexpected": True}, clock=lambda: 100.0
            )

    def test_pairing_control_rejects_expired_or_invalid_transaction(self) -> None:
        raw = {
            "op": "pair_abort",
            "transaction_id": "tx-1",
            "caller_node_id": "caller",
            "identity_fingerprint": "caller-id",
            "transport_fingerprint": "caller-tls",
            "secret": "b" * 64,
            "permissions": [],
            "expires_at": 100.0,
        }

        for expires_at in (99.0, 100.0, float("inf")):
            with (
                self.subTest(expires_at=expires_at),
                self.assertRaises(RemoteProtocolError),
            ):
                validate_pairing_control_request(
                    {**raw, "expires_at": expires_at}, clock=lambda: 100.0
                )

    def test_pairing_control_dispatch_returns_structured_result(self) -> None:
        raw = {
            "op": "pair_confirm",
            "transaction_id": "tx-1",
            "caller_node_id": "caller",
            "identity_fingerprint": "caller-id",
            "transport_fingerprint": "caller-tls",
            "secret": "b" * 64,
            "permissions": [NodePermission.DASHBOARD_READ.value],
            "expires_at": 101.0,
        }

        response = json.loads(
            _handle_pair_confirm(raw, lambda _request: True, clock=lambda: 100.0)
        )

        self.assertTrue(response["approved"])
        self.assertIsNone(response["error"])

        denied = json.loads(
            _handle_pair_abort(
                raw | {"op": "pair_abort"}, lambda _: False, clock=lambda: 100.0
            )
        )
        self.assertFalse(denied["approved"])
        self.assertEqual(denied["error"], "denied")

    def test_pairing_control_passes_cancellation_to_transport(self) -> None:
        cancel_event = threading.Event()

        class Transport:
            def request(self, _envelope: str, received_event: object) -> str:
                self.received_event = received_event
                return json.dumps({"approved": True})

        transport = Transport()
        response = transport.request("pair_confirm", cancel_event)

        self.assertEqual(json.loads(response)["approved"], True)
        self.assertIs(transport.received_event, cancel_event)

    def test_elevation_request_allows_only_explicit_target_approval(self) -> None:
        request = CapabilityElevationRequest(
            caller_node_id=NodeId("caller"),
            identity_fingerprint="caller-id",
            transport_fingerprint="caller-tls",
            current_secret="a" * 64,
            proposed_secret="b" * 64,
            permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
        )
        self.assertEqual(
            request.permissions, frozenset({NodePermission.PROCESS_TERMINATION})
        )

    def test_elevation_request_rejects_empty_permissions(self) -> None:
        with self.assertRaises(ValueError):
            CapabilityElevationRequest(
                caller_node_id=NodeId("caller"),
                identity_fingerprint="caller-id",
                transport_fingerprint="caller-tls",
                current_secret="a" * 64,
                proposed_secret="b" * 64,
                permissions=frozenset(),
            )

    def test_elevation_handler_requires_explicit_approval(self) -> None:
        raw = {
            "op": "elevation_request",
            "caller_node_id": "caller",
            "identity_fingerprint": "caller-id",
            "transport_fingerprint": "caller-tls",
            "current_secret": "a" * 64,
            "secret": "b" * 64,
            "permissions": [NodePermission.CLEANUP.value],
        }
        denied = _handle_elevation_request(raw, lambda _request: False)
        approved = _handle_elevation_request(raw, lambda _request: True)
        self.assertFalse(json.loads(denied)["approved"])
        self.assertTrue(json.loads(approved)["approved"])

    def test_elevation_request_carries_the_existing_pairing_credential(self) -> None:
        request = CapabilityElevationRequest(
            caller_node_id=NodeId("caller"),
            identity_fingerprint="caller-id",
            transport_fingerprint="caller-tls",
            current_secret="a" * 64,
            proposed_secret="b" * 64,
            permissions=frozenset({NodePermission.CLEANUP}),
        )
        self.assertNotEqual(request.current_secret, request.proposed_secret)

    def test_generation_does_not_require_openssl_on_path(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "subprocess.run",
                side_effect=FileNotFoundError("openssl not found"),
            ),
        ):
            material = ensure_tls_material(Path(directory), "peer")
            self.assertIsNotNone(material.fingerprint)
            self.assertTrue(material.certificate.exists())
            self.assertTrue(material.private_key.exists())

    def test_generated_certificate_is_valid_pem_loadable_by_ssl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            material = ensure_tls_material(Path(directory), "peer")
            pem_text = material.certificate.read_text(encoding="ascii")
            der = ssl.PEM_cert_to_DER_cert(pem_text)
            self.assertGreater(len(der), 0)

    def test_fingerprint_computed_from_der_bytes_not_pem_text_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            material = ensure_tls_material(Path(directory), "peer")
            pem_text = material.certificate.read_text(encoding="ascii")
            pem_crlf = pem_text.replace("\n", "\r\n")
            der_from_crlf = ssl.PEM_cert_to_DER_cert(pem_crlf)
            recomputed = certificate_fingerprint(der_from_crlf)
            self.assertEqual(recomputed, material.fingerprint)

    def test_partial_state_missing_key_triggers_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            ensure_tls_material(path, "peer")
            (path / "peer-tls.key").unlink()
            second = ensure_tls_material(path, "peer")
            self.assertIsNotNone(second.fingerprint)
            self.assertTrue(second.private_key.exists())
            self.assertTrue(second.certificate.exists())

    def test_partial_state_missing_cert_triggers_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            ensure_tls_material(path, "peer")
            (path / "peer-tls.crt").unlink()
            second = ensure_tls_material(path, "peer")
            self.assertIsNotNone(second.fingerprint)
            self.assertTrue(second.certificate.exists())

    def test_material_is_reused_with_stable_fingerprint_and_private_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            first = ensure_tls_material(path, "peer")
            second = ensure_tls_material(path, "peer")

            self.assertEqual(first, second)
            self.assertEqual(first.private_key.stat().st_mode & 0o777, 0o600)

    def test_pinned_tls_socket_completes_authenticated_hello(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            material = ensure_tls_material(Path(directory), "peer")
            server = RemoteSocketServer(
                _service(),
                host="127.0.0.1",
                ssl_context=server_context(material),
            )
            server.start()
            self.addCleanup(server.stop)
            port = server.bound_port
            assert port is not None
            provider = AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret=SECRET,
                transport=TLSRemoteTransport(
                    "127.0.0.1",
                    port,
                    expected_fingerprint=material.fingerprint,
                ),
            )

            self.assertTrue(provider.hello()["ok"])

    def test_wrong_pinned_certificate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            material = ensure_tls_material(Path(directory), "peer")
            server = RemoteSocketServer(
                _service(),
                host="127.0.0.1",
                ssl_context=server_context(material),
            )
            server.start()
            self.addCleanup(server.stop)
            port = server.bound_port
            assert port is not None
            provider = AuthenticatedNodeProvider(
                node_id=NodeId("peer"),
                secret=SECRET,
                transport=TLSRemoteTransport(
                    "127.0.0.1", port, expected_fingerprint="0" * 79
                ),
            )

            with self.assertRaises(RemoteAuthError):
                provider.hello()

    def test_pairing_request_requires_target_handler_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            material = ensure_tls_material(Path(directory), "peer")
            server = RemoteSocketServer(
                _service(),
                host="127.0.0.1",
                ssl_context=server_context(material),
                pairing_handler=lambda _request: True,
            )
            server.start()
            self.addCleanup(server.stop)
            port = server.bound_port
            assert port is not None
            transport = TLSRemoteTransport(
                "127.0.0.1",
                port,
                expected_fingerprint=material.fingerprint,
            )

            self.assertFalse(
                AuthenticatedNodeProvider.request_pairing(
                    transport=transport,
                    caller_node_id=NodeId("caller"),
                    identity_fingerprint="caller-id",
                    transport_fingerprint="caller-tls",
                    proposed_secret="b" * 64,
                    permissions=frozenset({NodePermission.DASHBOARD_READ}),
                )
            )

    def test_pairing_request_passes_cancellation_to_transport(self) -> None:
        cancel_event = threading.Event()

        class Transport:
            def request(self, _envelope: str, received_event: object) -> str:
                self.received_event = received_event
                return json.dumps({"approved": True})

        transport = Transport()
        self.assertFalse(
            AuthenticatedNodeProvider.request_pairing(
                transport=transport,
                caller_node_id=NodeId("caller"),
                identity_fingerprint="caller-id",
                transport_fingerprint="caller-tls",
                proposed_secret="b" * 64,
                permissions=frozenset({NodePermission.DASHBOARD_READ}),
                cancel_event=cancel_event,
            )
        )
        self.assertIs(transport.received_event, cancel_event)

    def test_pairing_request_requires_transactional_response(self) -> None:
        observed: dict[str, Any] = {}

        class Transport:
            def request(self, envelope: str) -> str:
                observed.update(json.loads(envelope))
                return json.dumps({"approved": True})

        result = AuthenticatedNodeProvider.request_pairing(
            transport=Transport(),
            caller_node_id=NodeId("caller"),
            identity_fingerprint="caller-id",
            transport_fingerprint="caller-tls",
            proposed_secret="b" * 64,
            permissions=frozenset({NodePermission.DASHBOARD_READ}),
        )

        self.assertFalse(result)
        self.assertEqual(observed["pairing_mode"], "transactional")

    def test_pairing_request_rejects_destructive_permissions(self) -> None:
        with self.assertRaises(ValueError):
            from maintenance.remote import PairingRequest

            PairingRequest(
                caller_node_id=NodeId("caller"),
                identity_fingerprint="caller-id",
                transport_fingerprint="caller-tls",
                proposed_secret="b" * 64,
                permissions=frozenset({NodePermission.PROCESS_TERMINATION}),
            )


if __name__ == "__main__":
    unittest.main()
