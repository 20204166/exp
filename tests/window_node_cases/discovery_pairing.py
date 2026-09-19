"""Window discovery and pairing test cases."""

import threading
import time
import unittest
from dataclasses import replace
from typing import Any
from unittest.mock import Mock, patch

from maintenance.cluster import ClusterState, PeerGrantRecord, trusted_node_record
from maintenance.components.cluster_roles import ClusterRole, RoleAssignment
from maintenance.components.coordinator import AppCoordinator, ComponentRefreshScheduler
from maintenance.components.network_discovery import NetworkDiscovery
from maintenance.nodes import (
    LOCAL_NODE_ID,
    READ_PERMISSIONS,
    DiscoveredNodeCandidate,
    NodeId,
    NodeIdentityStatus,
    NodeRegistry,
    node_identity_fingerprint,
    node_operation_key,
)
from maintenance.ui import window_node_actions
from tests.support.scheduling import DeferredRunner
from tests.test_window_nodes import (
    _candidate,
    _make_window,
    _trusted_context,
)


# Preserve the extracted case bodies exactly as they were in the facade.
# fmt: off
class WindowDiscoveryIntegrationTests(unittest.TestCase):
    def test_migrated_local_identity_uses_matching_fingerprint(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState(local_node_id="node-persisted")
        window._node_registry = NodeRegistry()
        window._component_scheduler = ComponentRefreshScheduler()

        window._build_local_node_context()

        descriptor = window._node_registry.selected_context().descriptor
        self.assertEqual(descriptor.id, NodeId("node-persisted"))
        self.assertEqual(
            descriptor.identity_fingerprint,
            node_identity_fingerprint("node-persisted"),
        )

    def test_start_discovery_registers_local_advertisement(self) -> None:
        with patch(
            "window.NetworkDiscovery",
            side_effect=lambda *args, **kwargs: Mock(spec=NetworkDiscovery),
        ) as factory:
            _make_window()
        factory.assert_called_once()
        _, kwargs = factory.call_args
        self.assertEqual(kwargs["advertisement"].stable_id, LOCAL_NODE_ID)
        self.assertFalse(kwargs["advertisement"].connectable)

    def test_manual_host_records_are_preserved_in_cluster_state(self) -> None:
        from maintenance.remote_support.protocol import READ_CAPABILITIES
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()

        hostname_record = trusted_node_record(
            node_id="manual-lab-box.local",
            display_name="Lab Box",
            hostname="lab-box.local",
            host="lab-box.local",
            port=None,
            capabilities=READ_CAPABILITIES,
            permissions=READ_PERMISSIONS,
        )
        ip_record = trusted_node_record(
            node_id="manual-192.168.1.20:5000",
            display_name="IP Box",
            hostname="192.168.1.20",
            host="192.168.1.20",
            port=5000,
            capabilities=READ_CAPABILITIES,
            permissions=READ_PERMISSIONS,
        )
        window._cluster_state = replace(
            window._cluster_state,
            trusted_nodes=(hostname_record, ip_record),
        )

        self.assertIsNotNone(window._cluster_state.record("manual-lab-box.local"))
        self.assertIsNotNone(window._cluster_state.record("manual-192.168.1.20:5000"))
        self.assertEqual(hostname_record.host, "lab-box.local")
        self.assertEqual(ip_record.host, "192.168.1.20")

    def test_discovered_candidate_never_becomes_selectable(self) -> None:
        window = _make_window()
        window._on_discovered_candidate(_candidate("peer-a"))
        self.assertNotIn(
            NodeId("peer-a"),
            {d.id for d in window._node_registry.selectable_descriptors()},
        )

    def test_reject_discovered_node_clears_only_the_candidate(self) -> None:
        window = _make_window()
        window._on_discovered_candidate(_candidate("peer-a"))

        window._reject_discovered_node("peer-a")

        self.assertEqual(window._node_registry.discovered_candidates(), ())
        self.assertEqual(window._selected_node_id, NodeId(LOCAL_NODE_ID))

    def test_discovered_lost_removes_candidate(self) -> None:
        window = _make_window()
        window._on_discovered_candidate(_candidate("peer-a"))
        window._on_discovered_lost("peer-a")
        self.assertEqual(window._node_registry.discovered_candidates(), ())

    def test_discovery_presentation_waits_for_session_stabilization(self) -> None:
        window = _make_window()
        window._queue_discovery_presentation = Mock()
        session = window._discovery_session

        window._on_discovered_candidate(_candidate("peer-a"))

        window._queue_discovery_presentation.assert_not_called()
        session._on_stabilized()
        window._queue_discovery_presentation.assert_called_once_with(False)

    def test_trusted_rediscovery_updates_saved_endpoint_after_hello(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer")
        )
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._cluster_state = ClusterState(
            discovery_enabled=True,
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.168.1.10",
                    port=5000,
                    secret="a" * 64,
                ),
            ),
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        provider = Mock()
        provider.hello.return_value = {
            "ok": True,
            "node_id": "peer-a",
            "identity_fingerprint": node_identity_fingerprint("peer-a"),
            "app_version": "1.2.2.0",
            "capabilities": ["dashboard_read"],
        }

        candidate = DiscoveredNodeCandidate(
            stable_id="peer-a",
            hostname="new-host",
            addresses=("192.168.1.20",),
            port=6000,
            service_name="peer-a._system-analyzer._tcp.local.",
            app_version="1.2.4.0",
            protocol_version="1",
            platform="Linux",
            connectable=False,
            compatible=True,
            last_seen=1.0,
        )

        with patch("window.AuthenticatedNodeProvider", return_value=provider) as factory:
            window._on_discovered_candidate(candidate)

        factory.assert_called_once()
        self.assertEqual(runner.pending, 1)
        runner.run_next()
        self.assertEqual(len(deliveries), 1)
        deliveries[0]()

        record = window._cluster_state.record("peer-a")
        assert record is not None
        self.assertEqual(record.host, "192.168.1.20")
        self.assertEqual(record.port, 6000)
        self.assertEqual(record.hostname, "new-host")

    def test_rediscovery_never_replaces_persisted_tls_pin(self) -> None:
        fingerprint = node_identity_fingerprint("peer-a")
        context = _trusted_context(
            "peer-a", "Peer A", cpu_value="peer", host_label="peer"
        )
        context.descriptor = replace(
            context.descriptor,
            identity_fingerprint=fingerprint,
            identity_status=NodeIdentityStatus.VERIFIED,
        )
        window = _make_window(context, start_discovery=False)
        window._cluster_state = ClusterState(
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.168.1.10",
                    port=5000,
                    identity_fingerprint=fingerprint,
                    transport_fingerprint="tls-x",
                ),
            )
        )
        window._nodes_error = Mock()
        candidate = replace(
            _candidate("peer-a", fingerprint), transport_fingerprint="tls-y"
        )

        with patch("maintenance.ui.window_discovery.build_trusted_transport") as build:
            window._on_discovered_candidate(candidate)

        record = window._cluster_state.record("peer-a")
        assert record is not None
        self.assertEqual(record.transport_fingerprint, "tls-x")
        self.assertEqual(
            window._node_registry.context(NodeId("peer-a")).descriptor.identity_status,
            NodeIdentityStatus.MISMATCH,
        )
        build.assert_not_called()

    def test_legacy_trusted_rediscovery_hydrates_live_fingerprint(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer")
        )
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._cluster_state = ClusterState(
            discovery_enabled=True,
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.168.1.10",
                    port=5000,
                    secret="a" * 64,
                ),
            ),
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        provider = Mock()
        provider.hello.return_value = {
            "ok": True,
            "node_id": "peer-a",
            "identity_fingerprint": node_identity_fingerprint("peer-a"),
        }
        candidate = DiscoveredNodeCandidate(
            stable_id="peer-a",
            hostname="peer-a",
            addresses=("192.168.1.10",),
            port=5000,
            service_name="peer-a._system-analyzer._tcp.local.",
            app_version="1.2.4.0",
            protocol_version="1",
            platform="Linux",
            connectable=False,
            compatible=True,
            last_seen=1.0,
            identity_fingerprint=node_identity_fingerprint("peer-a"),
        )

        with patch("window.AuthenticatedNodeProvider", return_value=provider):
            window._on_discovered_candidate(candidate)

        # hello is deferred to background; flush the worker then the delivery.
        self.assertEqual(runner.pending, 1)
        runner.run_next()
        self.assertEqual(len(deliveries), 1)
        deliveries[0]()

        descriptor = window._node_registry.context(NodeId("peer-a")).descriptor
        self.assertEqual(
            descriptor.identity_fingerprint,
            node_identity_fingerprint("peer-a"),
        )
        self.assertEqual(descriptor.identity_status, NodeIdentityStatus.VERIFIED)
        record = window._cluster_state.record("peer-a")
        assert record is not None
        self.assertEqual(
            record.identity_fingerprint,
            node_identity_fingerprint("peer-a"),
        )
        provider.hello.assert_called_once()

    def test_trusted_rediscovery_rejects_identity_mismatch(self) -> None:
        window = _make_window(
            _trusted_context("peer-a", "Peer A", cpu_value="peer", host_label="peer")
        )
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._cluster_state = ClusterState(
            discovery_enabled=True,
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.168.1.10",
                    port=5000,
                    secret="a" * 64,
                    identity_fingerprint="original",
                ),
            ),
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        candidate = DiscoveredNodeCandidate(
            stable_id="peer-a",
            hostname="new-host",
            addresses=("192.168.1.20",),
            port=6000,
            service_name="peer-a._system-analyzer._tcp.local.",
            app_version="1.2.4.0",
            protocol_version="1",
            platform="Linux",
            connectable=False,
            compatible=True,
            last_seen=1.0,
            identity_fingerprint="changed",
        )

        # Mismatch is detected synchronously — no background task is queued.
        with patch("window.AuthenticatedNodeProvider") as factory:
            window._on_discovered_candidate(candidate)

        factory.assert_not_called()
        self.assertEqual(runner.pending, 0)
        record = window._cluster_state.record("peer-a")
        assert record is not None
        self.assertEqual(record.host, "192.168.1.10")
        self.assertEqual(
            window._node_registry.context(
                NodeId("peer-a")
            ).descriptor.identity_status.value,
            "mismatch",
        )

        # Recovery: matching fingerprint schedules hello; flush to confirm VERIFIED.
        matching = replace(candidate, identity_fingerprint="original")
        provider = Mock()
        provider.hello.return_value = {
            "ok": True,
            "node_id": "peer-a",
            "identity_fingerprint": "original",
        }
        with patch("window.AuthenticatedNodeProvider", return_value=provider):
            window._on_discovered_candidate(matching)

        self.assertEqual(runner.pending, 1)
        runner.run_next()
        self.assertEqual(len(deliveries), 1)
        deliveries[0]()

        self.assertEqual(
            window._node_registry.context(NodeId("peer-a")).descriptor.identity_status,
            NodeIdentityStatus.VERIFIED,
        )

    def test_confirmed_mismatch_repair_replaces_trust_record(self) -> None:
        context = _trusted_context(
            "peer-a", "Peer A", cpu_value="peer", host_label="peer"
        )
        context.descriptor = replace(
            context.descriptor,
            identity_fingerprint="original",
            identity_status=NodeIdentityStatus.VERIFIED,
        )
        window = _make_window(context)
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._cluster_state = ClusterState(
            trusted_nodes=(
                trusted_node_record(
                    node_id="peer-a",
                    display_name="Peer A",
                    hostname="peer-a",
                    host="192.168.1.10",
                    port=5000,
                    secret="a" * 64,
                    identity_fingerprint="original",
                ),
            )
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        window._node_registry.update_discovered(_candidate("peer-a", "replacement"))
        provision = Mock(return_value=True)
        window._provision_target_grant = provision

        # _prepare_pairing runs synchronously (fingerprint dialog on Tk);
        # provisioning is dispatched to background.
        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        self.assertEqual(runner.pending, 1)
        runner.run_next()
        self.assertEqual(len(deliveries), 1)
        deliveries[0]()

        records = window._cluster_state.trusted_nodes
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].identity_fingerprint, "replacement")
        self.assertIs(window._cluster_state.record("peer-a"), records[0])
        self.assertEqual(provision.call_args.args[0].caller_node_id, "local")
        self.assertEqual(window._cluster_state.peer_grants, ())

    def test_pairing_without_target_grant_is_not_marked_trusted(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._nodes_error = Mock()
        window._refresh_nodes_page = Mock()
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        self.assertIsNone(window._cluster_state.record("peer-a"))
        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))
        window._nodes_error.assert_called_once_with(
            "Pairing requires explicit target-side grant provisioning"
        )

    def test_pairing_provisions_grant_through_coordinator_before_persisting(
        self,
    ) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(
            runner=runner,
            deliver=deliveries.append,
        )
        provision = Mock(return_value=True)
        window._provision_target_grant = provision

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        self.assertEqual(runner.pending, 1)
        self.assertIsNone(window._cluster_state.record("peer-a"))
        window._pairing_dialog.set_pending.assert_called_once_with()
        self.assertEqual(
            window._coordinator.generation(
                node_operation_key(NodeId("peer-a"), "pair")
            ),
            1,
        )

        runner.run_next()
        self.assertEqual(len(deliveries), 1)
        deliveries[0]()

        provision.assert_called_once()
        self.assertEqual(len(provision.call_args.args), 1)
        self.assertIsNotNone(window._cluster_state.record("peer-a"))
        window._pairing_dialog.complete.assert_called_once_with()

    def test_revoke_cancels_pairing_before_late_success_delivery(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        window._provision_target_grant = Mock(return_value=True)

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        runner.run_next()
        window_node_actions.revoke_trusted_node(window, "peer-a")
        deliveries[0]()

        self.assertIsNone(window._cluster_state.record("peer-a"))
        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))

    def test_revoke_save_failure_keeps_pairing_state_consistent(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._pairing_dialog = Mock()
        window._nodes_error = Mock()
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        window._provision_target_grant = Mock(return_value=True)

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        window._save_cluster_state = Mock(return_value=False)
        window_node_actions.revoke_trusted_node(window, "peer-a")

        self.assertIsNotNone(window._node_registry.context(NodeId("peer-a")))
        self.assertIn(NodeId("peer-a"), window.__dict__["_pairing_attempts"])
        self.assertEqual(
            window._coordinator.generation(
                node_operation_key(NodeId("peer-a"), "pair")
            ),
            1,
        )
        window._nodes_error.assert_called_once_with(
            "Cluster settings could not be saved"
        )

    def test_pairing_success_after_worker_cancellation_is_not_persisted(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._cluster_store.save = Mock()
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        provision = Mock(return_value=True)

        def provision_and_cancel(grant: PeerGrantRecord) -> bool:
            result = provision(grant)
            cancel_event = window._coordinator.state(
                node_operation_key(NodeId("peer-a"), "pair")
            ).cancel_event
            assert cancel_event is not None
            cancel_event.set()
            return result

        window._provision_target_grant = provision_and_cancel
        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        runner.run_next()
        deliveries[0]()

        self.assertIsNone(window._cluster_state.record("peer-a"))
        window._pairing_dialog.complete.assert_not_called()

    def test_default_target_grant_provisioner_receives_cancel_event(self) -> None:
        window = _make_window(start_discovery=False)
        candidate = replace(
            _candidate("peer-a", node_identity_fingerprint("peer-a")),
            transport_fingerprint="target-tls",
        )
        window._node_registry.update_discovered(candidate)
        grant = PeerGrantRecord(
            caller_node_id="local",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
        )
        cancel_event = threading.Event()

        with patch.object(
            window_node_actions.AuthenticatedNodeProvider,
            "request_pairing",
            return_value=True,
        ) as request_pairing:
            window_node_actions.request_target_grant(
                window, candidate, grant, cancel_event=cancel_event
            )

        self.assertIs(request_pairing.call_args.kwargs["cancel_event"], cancel_event)

    def test_default_pairing_returns_target_transaction_for_confirm(self) -> None:
        window = _make_window(start_discovery=False)
        candidate = replace(
            _candidate("peer-a", node_identity_fingerprint("peer-a")),
            transport_fingerprint="target-tls",
        )
        window._node_registry.update_discovered(candidate)
        grant = PeerGrantRecord(
            caller_node_id="local",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
        )
        transaction = {
            "transaction_id": "tx-1",
            "caller_node_id": "local",
            "identity_fingerprint": window._node_registry.context(
                NodeId("local")
            ).descriptor.identity_fingerprint,
            "transport_fingerprint": "",
            "secret": grant.secret,
            "permissions": [permission.value for permission in grant.permissions],
            "expires_at": time.time() + 3600.0,
        }

        with patch.object(
            window_node_actions.AuthenticatedNodeProvider,
            "request_pairing",
            return_value=transaction,
        ):
            result = window_node_actions.request_target_grant(window, candidate, grant)

        self.assertIsInstance(result, window_node_actions.PairingTransaction)
        assert isinstance(result, window_node_actions.PairingTransaction)
        self.assertEqual(result.transaction_id, "tx-1")
        self.assertGreater(result.expires_at, time.time())

    def test_default_pairing_rejects_returned_binding_mismatch(self) -> None:
        window = _make_window(start_discovery=False)
        candidate = replace(
            _candidate("peer-a", node_identity_fingerprint("peer-a")),
            transport_fingerprint="target-tls",
        )
        window._node_registry.update_discovered(candidate)
        grant = PeerGrantRecord(
            caller_node_id="local",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
        )
        requested_expiry = time.time() + 3600.0
        mismatches = {
            "caller_node_id": "other-caller",
            "identity_fingerprint": "other-id",
            "transport_fingerprint": "other-tls",
            "secret": "c" * 64,
            "permissions": [],
            "expires_at": time.time() - 1.0,
        }
        window._save_cluster_state = Mock()

        for field, mismatch in mismatches.items():
            returned = {
                "transaction_id": "tx-1",
                "caller_node_id": grant.caller_node_id,
                "identity_fingerprint": window._node_registry.context(
                    NodeId("local")
                ).descriptor.identity_fingerprint,
                "transport_fingerprint": "",
                "secret": grant.secret,
                "permissions": [permission.value for permission in grant.permissions],
                "expires_at": requested_expiry,
            }
            returned[field] = mismatch
            with (
                self.subTest(field=field),
                patch.object(
                    window_node_actions.AuthenticatedNodeProvider,
                    "request_pairing",
                    return_value=returned,
                ),
                patch.object(window_node_actions, "confirm_target_pairing") as confirm,
                patch.object(window_node_actions, "abort_target_pairing") as abort,
            ):
                result = window_node_actions.request_target_grant(
                    window, candidate, grant
                )

            self.assertFalse(result)
            confirm.assert_not_called()
            if field == "expires_at":
                abort.assert_called_once()
            else:
                abort.assert_not_called()
        window._save_cluster_state.assert_not_called()

    def test_pairing_control_uses_same_pinned_transport(self) -> None:
        transport = Mock()
        transport.request.return_value = '{"approved": true}'
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=123.0,
            transport=transport,
        )

        self.assertTrue(window_node_actions.confirm_target_pairing(transaction))
        self.assertEqual(transport.request.call_args.args[0].__class__, str)
        self.assertIn("pair_confirm", transport.request.call_args.args[0])

        self.assertTrue(window_node_actions.abort_target_pairing(transaction))
        self.assertIn("pair_abort", transport.request.call_args.args[0])

    def test_network_pairing_saves_locally_before_confirming_target(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._pairing_dialog = Mock()
        candidate = replace(
            _candidate("peer-a", node_identity_fingerprint("peer-a")),
            transport_fingerprint="target-tls",
        )
        window._node_registry.update_discovered(candidate)
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)

        def save(state: ClusterState) -> bool:
            window._cluster_state = state
            return True

        window._save_cluster_state = Mock(side_effect=save)
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=123.0,
            transport=Mock(),
        )
        with (
            patch.object(
                window_node_actions, "request_target_grant", return_value=transaction
            ) as approval,
            patch.object(
                window_node_actions, "confirm_target_pairing", return_value=True
            ) as confirm,
        ):
            window_node_actions.pair_discovered_node_async(
                window,
                "peer-a",
                messagebox_module=Mock(askyesno=Mock(return_value=True)),
                dialog=window._pairing_dialog,
            )
            runner.run_next()
            self.assertEqual(window._cluster_state.record("peer-a"), None)
            deliveries.pop(0)()

            record = window._cluster_state.record("peer-a")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.node_id, "peer-a")
            confirm.assert_not_called()
            while runner.pending:
                runner.run_next()
                while deliveries:
                    deliveries.pop(0)()

        approval.assert_called_once()
        confirm.assert_called_once()
        self.assertIs(confirm.call_args.args[0], transaction)
        self.assertIsNotNone(confirm.call_args.kwargs["cancel_event"])
        window._pairing_dialog.complete.assert_called_once_with()

    def test_cancel_network_pairing_restores_saved_state_before_confirm_delivery(
        self,
    ) -> None:
        window = _make_window(start_discovery=False)
        previous_state = ClusterState()
        window._cluster_state = previous_state
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            replace(
                _candidate("peer-a", node_identity_fingerprint("peer-a")),
                transport_fingerprint="target-tls",
            )
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)

        def save(state: ClusterState) -> bool:
            window._cluster_state = state
            return True

        window._save_cluster_state = Mock(side_effect=save)
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=123.0,
            transport=Mock(),
        )
        with (
            patch.object(
                window_node_actions, "request_target_grant", return_value=transaction
            ),
            patch.object(
                window_node_actions, "confirm_target_pairing", return_value=True
            ),
        ):
            window_node_actions.pair_discovered_node_async(
                window,
                "peer-a",
                messagebox_module=Mock(askyesno=Mock(return_value=True)),
                dialog=window._pairing_dialog,
            )
            runner.run_next()
            deliveries.pop(0)()

            self.assertIsNotNone(window._cluster_state.record("peer-a"))
            window_node_actions.cancel_pairing(window, "peer-a")
            while deliveries:
                deliveries.pop(0)()

        self.assertEqual(window._cluster_state, previous_state)
        self.assertIs(
            window._save_cluster_state.call_args_list[-1].args[0], previous_state
        )
        self.assertGreaterEqual(runner.pending, 2)
        window._pairing_dialog.complete.assert_not_called()

    def test_cancel_during_target_confirmation_keeps_committed_local_trust(
        self,
    ) -> None:
        window = _make_window(start_discovery=False)
        previous_state = ClusterState()
        window._cluster_state = previous_state
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            replace(
                _candidate("peer-a", node_identity_fingerprint("peer-a")),
                transport_fingerprint="target-tls",
            )
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)

        def save(state: ClusterState) -> bool:
            window._cluster_state = state
            return True

        window._save_cluster_state = Mock(side_effect=save)
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=123.0,
            transport=Mock(),
        )

        def confirm(_transaction: Any, *, cancel_event: Any = None) -> bool:
            self.assertIsNotNone(cancel_event)
            window_node_actions.cancel_pairing(window, "peer-a")
            return True

        with (
            patch.object(
                window_node_actions, "request_target_grant", return_value=transaction
            ),
            patch.object(
                window_node_actions, "confirm_target_pairing", side_effect=confirm
            ),
            patch.object(
                window_node_actions, "abort_target_pairing", return_value=True
            ) as abort,
        ):
            window_node_actions.pair_discovered_node_async(
                window,
                "peer-a",
                messagebox_module=Mock(askyesno=Mock(return_value=True)),
                dialog=window._pairing_dialog,
            )
            while runner.pending or deliveries:
                if runner.pending:
                    runner.run_next()
                while deliveries:
                    deliveries.pop(0)()

        self.assertIsNotNone(window._cluster_state.record("peer-a"))
        abort.assert_not_called()
        window._pairing_dialog.complete.assert_called_once_with()

    def test_network_confirmation_failure_restores_local_trust_and_aborts(self) -> None:
        window = _make_window(start_discovery=False)
        previous_state = ClusterState()
        window._cluster_state = previous_state
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            replace(
                _candidate("peer-a", node_identity_fingerprint("peer-a")),
                transport_fingerprint="target-tls",
            )
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)

        def save(state: ClusterState) -> bool:
            window._cluster_state = state
            return True

        window._save_cluster_state = Mock(side_effect=save)
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=123.0,
            transport=Mock(),
        )
        with (
            patch.object(
                window_node_actions, "request_target_grant", return_value=transaction
            ),
            patch.object(
                window_node_actions, "confirm_target_pairing", return_value=False
            ),
            patch.object(
                window_node_actions, "abort_target_pairing", return_value=True
            ) as abort,
        ):
            window_node_actions.pair_discovered_node_async(
                window,
                "peer-a",
                messagebox_module=Mock(askyesno=Mock(return_value=True)),
                dialog=window._pairing_dialog,
            )
            while runner.pending or deliveries:
                if runner.pending:
                    runner.run_next()
                while deliveries:
                    deliveries.pop(0)()

        self.assertIsNone(window._cluster_state.record("peer-a"))
        self.assertEqual(
            window._save_cluster_state.call_args_list[-1].args[0], previous_state
        )
        abort.assert_called_once_with(transaction)
        window._pairing_dialog.complete.assert_not_called()
        window._pairing_dialog.show_error.assert_called_once_with(
            "Target pairing confirmation failed"
        )

    def test_async_pairing_failure_restores_discovered_candidate(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._pairing_dialog = Mock()
        candidate = _candidate("peer-a", node_identity_fingerprint("peer-a"))
        window._node_registry.update_discovered(candidate)
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(
            runner=runner,
            deliver=deliveries.append,
        )
        window._provision_target_grant = Mock(return_value=False)

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")
        runner.run_next()
        deliveries[0]()

        with self.assertRaises(KeyError):
            window._node_registry.context(NodeId("peer-a"))
        self.assertEqual(
            window._node_registry.discovered_candidates(),
            (candidate,),
        )
        window._pairing_dialog.complete.assert_not_called()
        window._pairing_dialog.show_error.assert_called_once_with(
            "Target did not provision the peer grant"
        )

    def test_pairing_clears_stale_revoked_role_assignment(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState(
            role_assignments=(
                RoleAssignment(
                    frozenset({ClusterRole.COORDINATOR, ClusterRole.WORKER}),
                    node_id=NodeId("local"),
                ),
                RoleAssignment(
                    frozenset({ClusterRole.WORKER}),
                    node_id=NodeId("peer-a"),
                    revoked=True,
                ),
            )
        )
        window._cluster_store = Mock()
        window._nodes_error = Mock()
        window._refresh_nodes_page = Mock()
        window._refresh_cluster_page = Mock()
        window._rebuild_node_selector = Mock()
        window._nodes_status = Mock()
        window._provision_target_grant = Mock(return_value=True)
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )

        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        stale = next(
            (
                item
                for item in window._cluster_state.role_assignments
                if item.node_id == NodeId("peer-a")
            ),
            None,
        )
        self.assertIsNone(stale)

        window._set_node_roles("peer-a", frozenset({"worker"}))

        window._nodes_error.assert_not_called()
        assignment = next(
            item
            for item in window._cluster_state.role_assignments
            if item.node_id == NodeId("peer-a")
        )
        self.assertFalse(assignment.revoked)

    def test_activation_result_is_ignored_after_record_replacement(self) -> None:
        window = _make_window(start_discovery=False)
        context = _trusted_context(
            "peer-a", "Peer A", cpu_value="peer", host_label="peer"
        )
        context.provider = None
        context.descriptor = replace(
            context.descriptor,
            identity_fingerprint=node_identity_fingerprint("peer-a"),
            identity_status=NodeIdentityStatus.VERIFIED,
        )
        window._node_registry.register_context(context)
        record = trusted_node_record(
            node_id="peer-a",
            display_name="Peer A",
            hostname="peer-a",
            host="peer-a",
            port=5000,
            identity_fingerprint=node_identity_fingerprint("peer-a"),
        )
        window._cluster_state = ClusterState(trusted_nodes=(record,))
        workers: list[Any] = []
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(
            runner=lambda worker: workers.append(worker),
            deliver=lambda callback: deliveries.append(callback),
        )
        provider = Mock()
        provider.hello.return_value = {
            "node_id": "peer-a",
            "identity_fingerprint": record.identity_fingerprint,
            "capabilities": ["dashboard_read"],
        }

        with patch("window.AuthenticatedNodeProvider", return_value=provider):
            window._activate_remote_node(NodeId("peer-a"))
        workers[0]()
        window._cluster_state = ClusterState(
            trusted_nodes=(replace(record, secret="b" * 64),)
        )
        deliveries[0]()

        self.assertIsNone(context.provider)

    def test_discovery_status_lists_untrusted_peers_and_hides_when_lost(self) -> None:
        window = _make_window()
        window._discovery_pages_visible = True
        window.discovery_status_label = Mock()

        window._on_discovered_candidate(_candidate("peer-b"))
        window._on_discovered_candidate(_candidate("peer-a"))
        window._discovery_session._on_stabilized()

        window.discovery_status_label.config.assert_called_with(
            text="Discovered 2 untrusted peers: peer-a-host, peer-b-host"
        )
        window._on_discovered_lost("peer-a")
        window._on_discovered_lost("peer-b")
        window._discovery_session._on_stabilized()
        window.discovery_status_label.pack_forget.assert_called_once()

    def test_shutdown_stops_discovery(self) -> None:
        window = _make_window()
        window._stop_discovery = Mock()
        window._finalize_shutdown()
        window._stop_discovery.assert_called_once()

    def test_shutdown_drops_pending_pairing_worker_delivery(self) -> None:
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._pairing_dialog = Mock()
        window._node_registry.update_discovered(
            replace(
                _candidate("peer-a", node_identity_fingerprint("peer-a")),
                transport_fingerprint="target-tls",
            )
        )
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        transaction = window_node_actions.PairingTransaction(
            transaction_id="tx-1",
            caller_node_id="local",
            identity_fingerprint="local-id",
            transport_fingerprint="local-tls",
            secret="b" * 64,
            permissions=READ_PERMISSIONS,
            expires_at=time.time() + 300,
            transport=Mock(),
        )
        window._save_cluster_state = Mock(return_value=True)

        with patch.object(
            window_node_actions, "request_target_grant", return_value=transaction
        ):
            window_node_actions.pair_discovered_node_async(
                window,
                "peer-a",
                messagebox_module=Mock(askyesno=Mock(return_value=True)),
                dialog=window._pairing_dialog,
            )

        runner.run_next()
        window._finalize_shutdown()
        while deliveries:
            deliveries.pop(0)()

        self.assertIsNone(window._cluster_state.record("peer-a"))
        window._pairing_dialog.complete.assert_not_called()


# fmt: on


class Phase10ThreadingTests(unittest.TestCase):
    """Phase 10 — Remote UI / Network threading hardening.

    These tests verify:
    - elevation messagebox runs on Tk (via _submit_ui), never on the server thread;
    - elevation deny/timeout fails closed;
    - concurrent elevation is serialized by _elevation_lock;
    - endpoint verify hello runs off-Tk via coordinator.run;
    - stale endpoint verify results are discarded when superseded;
    - trust revoked in-flight causes the endpoint verify commit to be discarded;
    - _pair_discovered_node always dispatches async (no sync fallback).
    """

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _make_elevation_request(
        self,
        caller: str = "caller-node",
        secret: str | None = None,
        permissions: frozenset | None = None,
    ) -> Any:
        from maintenance.nodes import NodePermission
        from maintenance.remote import CapabilityElevationRequest

        s = secret if secret is not None else "c" * 64
        perms = (
            permissions
            if permissions is not None
            else frozenset({NodePermission.COMPONENT_READ})
        )
        return CapabilityElevationRequest(
            caller_node_id=NodeId(caller),
            identity_fingerprint="fp-id",
            transport_fingerprint="fp-tls",
            current_secret=s,
            proposed_secret="d" * 64,
            permissions=perms,
        )

    def _make_elevation_controller(
        self, caller: str = "caller-node", secret: str = "c" * 64
    ) -> Any:
        from maintenance.cluster import PeerGrantRecord

        window = _make_window(start_discovery=False)
        grant = PeerGrantRecord(
            caller_node_id=caller,
            secret=secret,
            permissions=frozenset(),
        )
        window._cluster_state = ClusterState(peer_grants=(grant,))

        # Stub out _save_cluster_state so the full peer-listener/TLS chain
        # is not triggered by these threading-focused tests.
        def _save(state: Any) -> bool:
            window._cluster_state = state
            return True

        window._save_cluster_state = _save
        return window

    # ------------------------------------------------------------------ #
    # Elevation threading tests                                            #
    # ------------------------------------------------------------------ #

    def test_elevation_messagebox_runs_via_submit_ui_not_directly(self) -> None:
        """messagebox must not be called on the server thread; it must be
        marshaled through _submit_ui so Tk invokes it after delivery."""
        from maintenance.nodes import NodePermission
        from maintenance.ui.window_discovery import handle_elevation_request

        secret = "c" * 64
        controller = self._make_elevation_controller(secret=secret)
        request = self._make_elevation_request(
            secret=secret,
            permissions=frozenset({NodePermission.COMPONENT_READ}),
        )

        captured_callbacks: list[Any] = []
        callback_queued = threading.Event()

        def capturing_submit(cb: Any) -> None:
            captured_callbacks.append(cb)
            callback_queued.set()

        controller._submit_ui = capturing_submit

        results: list[Any] = []

        def call_on_background() -> None:
            with patch("window.messagebox.askyesno", return_value=True):
                results.append(handle_elevation_request(controller, request))

        t = threading.Thread(target=call_on_background)
        t.start()

        # Wait until the background thread has queued the callback via _submit_ui.
        self.assertTrue(callback_queued.wait(timeout=2.0), "callback never queued")
        # At this point the background thread is blocked on completed.wait().
        # messagebox has NOT been called yet (server thread is waiting, not calling).
        self.assertEqual(len(captured_callbacks), 1)
        # Deliver on the "Tk" thread (simulates Tk dispatching the callback).
        with patch("window.messagebox.askyesno", return_value=True) as mb:
            captured_callbacks[0]()
            messagebox_was_called = mb.called

        t.join(timeout=2.0)
        self.assertFalse(t.is_alive(), "server thread should have returned")
        # messagebox was invoked during Tk delivery, and the result approved.
        self.assertTrue(messagebox_was_called)
        self.assertTrue(results[0])

    def test_elevation_deny_returns_false(self) -> None:
        """Denying the messagebox must return False (fail-closed)."""
        from maintenance.nodes import NodePermission
        from maintenance.ui.window_discovery import handle_elevation_request

        secret = "c" * 64
        controller = self._make_elevation_controller(secret=secret)
        request = self._make_elevation_request(
            secret=secret,
            permissions=frozenset({NodePermission.COMPONENT_READ}),
        )
        # inject _submit_ui to fire callback inline (simulates Tk delivery).
        controller._submit_ui = lambda cb: cb()
        with patch("window.messagebox.askyesno", return_value=False):
            result = handle_elevation_request(controller, request)
        self.assertFalse(result)

    def test_elevation_wrong_secret_returns_false(self) -> None:
        """A caller presenting the wrong secret is rejected before any dialog."""
        from maintenance.nodes import NodePermission
        from maintenance.ui.window_discovery import handle_elevation_request

        controller = self._make_elevation_controller(secret="c" * 64)
        request = self._make_elevation_request(
            secret="ab" * 32,  # valid hex but different from stored secret
            permissions=frozenset({NodePermission.COMPONENT_READ}),
        )
        submit_ui = Mock()
        controller._submit_ui = submit_ui
        result = handle_elevation_request(controller, request)
        self.assertFalse(result)
        submit_ui.assert_not_called()

    def test_elevation_concurrent_second_request_rejected(self) -> None:
        """While one elevation dialog is open _elevation_lock prevents another."""
        from maintenance.nodes import NodePermission
        from maintenance.ui.window_discovery import handle_elevation_request

        secret = "c" * 64
        controller = self._make_elevation_controller(secret=secret)
        request = self._make_elevation_request(
            secret=secret,
            permissions=frozenset({NodePermission.COMPONENT_READ}),
        )
        gate = threading.Event()
        submitted = threading.Event()

        def blocking_submit_ui(cb: Any) -> None:
            submitted.set()
            gate.wait()  # hold until test releases
            cb()

        controller._submit_ui = blocking_submit_ui
        results: list[Any] = []

        def first() -> None:
            with patch("window.messagebox.askyesno", return_value=True):
                results.append(("first", handle_elevation_request(controller, request)))

        def second() -> None:
            results.append(("second", handle_elevation_request(controller, request)))

        t1 = threading.Thread(target=first)
        t1.start()
        # Let t1 acquire the lock before t2 tries.
        self.assertTrue(submitted.wait(timeout=2.0))
        t2 = threading.Thread(target=second)
        t2.start()
        t2.join(timeout=2.0)
        self.assertFalse(t2.is_alive(), "second call should return immediately")
        # second must have returned False (serialized/rejected).
        second_result = next(r for name, r in results if name == "second")
        self.assertFalse(second_result)
        # unblock first
        gate.set()
        t1.join(timeout=2.0)
        self.assertFalse(t1.is_alive(), "first call should return")

    # ------------------------------------------------------------------ #
    # Endpoint verify async / stale-result tests                          #
    # ------------------------------------------------------------------ #

    def _make_verify_window(
        self,
        host: str = "192.168.1.10",
        port: int = 5000,
        secret: str = "a" * 64,
        node_id: str = "peer-a",
    ) -> Any:
        window = _make_window(
            _trusted_context(node_id, "Peer A", cpu_value="peer", host_label="peer")
        )
        window._cluster_store = Mock()
        window._cluster_store.save = Mock(return_value=True)
        window._cluster_state = ClusterState(
            trusted_nodes=(
                trusted_node_record(
                    node_id=node_id,
                    display_name="Peer A",
                    hostname=node_id,
                    host=host,
                    port=port,
                    secret=secret,
                ),
            )
        )
        return window

    def test_endpoint_verify_does_not_block_tk(self) -> None:
        """sync_trusted_node_endpoint must return immediately (no hello on Tk)."""
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window = self._make_verify_window()
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        provider = Mock()
        provider.hello.return_value = {
            "node_id": "peer-a",
            "identity_fingerprint": node_identity_fingerprint("peer-a"),
        }
        candidate = DiscoveredNodeCandidate(
            stable_id="peer-a",
            hostname="new-host",
            addresses=("192.168.1.20",),
            port=6000,
            service_name="peer-a._system-analyzer._tcp.local.",
            app_version="1.2.4.0",
            protocol_version="1",
            platform="Linux",
            connectable=False,
            compatible=True,
            last_seen=1.0,
        )
        with patch("window.AuthenticatedNodeProvider", return_value=provider):
            window._on_discovered_candidate(candidate)

        # Must return with hello not yet called; task was queued, not run.
        provider.hello.assert_not_called()
        self.assertEqual(runner.pending, 1)

        runner.run_next()
        deliveries[0]()
        provider.hello.assert_called_once()

    def test_endpoint_verify_stale_e1_does_not_overwrite_e2(self) -> None:
        """When E2 coalesces into E1's in-flight verify, only E2's address
        should be committed even though the background task ran E1's hello.

        The coordinator coalesces E2 into E1's in-flight run: E2's on_result
        (carrying E2's generation token, E2's address/port) replaces E1's.
        After E1 completes the background hello, the coordinator calls E2's
        on_result; _finish_endpoint_verify commits E2's address, not E1's.
        A rerun for E2 then fires but _finish_endpoint_verify discards it
        because the generation token was already consumed by the first delivery.
        """
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window = self._make_verify_window()
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)

        def _make_provider() -> Mock:
            p = Mock()
            p.hello.return_value = {
                "node_id": "peer-a",
                "identity_fingerprint": node_identity_fingerprint("peer-a"),
            }
            return p

        def _make_candidate(
            addresses: tuple[str, ...], port: int
        ) -> DiscoveredNodeCandidate:
            return DiscoveredNodeCandidate(
                stable_id="peer-a",
                hostname="host",
                addresses=addresses,
                port=port,
                service_name="peer-a._system-analyzer._tcp.local.",
                app_version="1.0.0.0",
                protocol_version="1",
                platform="Linux",
                connectable=False,
                compatible=True,
                last_seen=1.0,
            )

        p1 = _make_provider()
        p2 = _make_provider()

        with patch("window.AuthenticatedNodeProvider", return_value=p1):
            window._on_discovered_candidate(_make_candidate(("192.168.1.20",), 6000))
        # E2 arrives before E1 hello has run — coordinator coalesces.
        with patch("window.AuthenticatedNodeProvider", return_value=p2):
            window._on_discovered_candidate(_make_candidate(("10.0.0.5",), 7000))

        # Coordinator coalesces E2 into E1's in-flight run; one worker queued.
        self.assertEqual(runner.pending, 1)

        # Run E1's background hello (the deferred task factory).
        runner.run_next()
        # First delivery: E2's on_result is called with E1's hello → commits E2's address.
        deliveries[0]()

        record = window._cluster_state.record("peer-a")
        assert record is not None
        self.assertEqual(record.host, "10.0.0.5")
        self.assertEqual(record.port, 7000)

        # A rerun of E2 is triggered by the coordinator after E1 completes.
        # _finish_endpoint_verify discards it because the gen token was consumed.
        if runner.pending > 0:
            runner.run_next()
        while deliveries:
            deliveries.pop(0)()
        # E2's address is still committed; the rerun is discarded (gen consumed).
        record = window._cluster_state.record("peer-a")
        assert record is not None
        self.assertEqual(record.host, "10.0.0.5")
        self.assertEqual(record.port, 7000)

    def test_endpoint_verify_revoke_in_flight_discards_result(self) -> None:
        """If trust is revoked while hello is in flight, the commit must no-op."""
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window = self._make_verify_window()
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        provider = Mock()
        provider.hello.return_value = {
            "node_id": "peer-a",
            "identity_fingerprint": node_identity_fingerprint("peer-a"),
        }
        candidate = DiscoveredNodeCandidate(
            stable_id="peer-a",
            hostname="new-host",
            addresses=("192.168.1.20",),
            port=6000,
            service_name="peer-a._system-analyzer._tcp.local.",
            app_version="1.0.0.0",
            protocol_version="1",
            platform="Linux",
            connectable=False,
            compatible=True,
            last_seen=1.0,
        )
        with patch("window.AuthenticatedNodeProvider", return_value=provider):
            window._on_discovered_candidate(candidate)

        runner.run_next()
        # Revoke trust before delivery fires.
        window._cluster_state = ClusterState()  # no trusted nodes
        deliveries[0]()

        # After revoke, commit should be a no-op — state stays empty.
        self.assertIsNone(window._cluster_state.record("peer-a"))

    # ------------------------------------------------------------------ #
    # _pair_discovered_node always-async test                             #
    # ------------------------------------------------------------------ #

    def test_pair_discovered_node_always_dispatches_async(self) -> None:
        """_pair_discovered_node with no _pairing_dialog must still go
        through coordinator.run and never block Tk for provisioning."""
        window = _make_window(start_discovery=False)
        window._cluster_state = ClusterState()
        window._cluster_store = Mock()
        window._cluster_store.save = Mock(return_value=True)
        # Explicitly no dialog set.
        self.assertIsNone(window.__dict__.get("_pairing_dialog"))
        runner = DeferredRunner()
        deliveries: list[Any] = []
        window._coordinator = AppCoordinator(runner=runner, deliver=deliveries.append)
        provision = Mock(return_value=True)
        window._provision_target_grant = provision
        window._node_registry.update_discovered(
            _candidate("peer-a", node_identity_fingerprint("peer-a"))
        )
        with patch("window.messagebox.askyesno", return_value=True):
            window._pair_discovered_node("peer-a")

        # Provisioning must have been dispatched to background, not run inline.
        provision.assert_not_called()
        self.assertEqual(runner.pending, 1)

        runner.run_next()
        deliveries[0]()

        provision.assert_called_once()
        self.assertIsNotNone(window._cluster_state.record("peer-a"))
