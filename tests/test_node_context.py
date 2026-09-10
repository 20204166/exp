"""Focused tests for node context construction and restoration."""

import unittest
from unittest.mock import Mock

from maintenance.cluster import ClusterState, trusted_node_record
from maintenance.components.node_context import (
    build_local_node_context,
    restore_trusted_nodes,
)
from maintenance.nodes import (
    LOCAL_NODE_ID,
    LocalNodeProvider,
    NodeContext,
    NodeId,
    NodeRegistry,
    NodeTrustState,
    local_node_descriptor,
    node_identity_fingerprint,
)


class NodeContextTests(unittest.TestCase):
    def test_local_provider_binds_descriptor_without_changing_dashboard_shape(
        self,
    ) -> None:
        dashboard = Mock()
        dashboard.scanned_at = Mock()
        analyzer = Mock()
        analyzer.dashboard_snapshot.return_value = dashboard
        descriptor = local_node_descriptor()

        snapshot = LocalNodeProvider(analyzer, descriptor).node_snapshot()

        self.assertEqual(snapshot.node_id, descriptor.id)
        self.assertIs(snapshot.dashboard, dashboard)
        analyzer.dashboard_snapshot.assert_called_once_with(
            cancel_event=None,
            progress_callback=None,
        )

    def test_build_local_context_uses_persisted_identity_and_dependencies(self) -> None:
        analyzer = Mock()
        process_manager = Mock()
        file_manager = Mock()
        scheduler = Mock()
        coordinator = Mock()
        snapshot = Mock()
        capabilities = {"cpu": Mock()}

        context = build_local_node_context(
            cluster_state=ClusterState(local_node_id="persisted"),
            analyzer=analyzer,
            process_manager=process_manager,
            file_manager=file_manager,
            scheduler=scheduler,
            coordinator=coordinator,
            snapshot=snapshot,
            capabilities=capabilities,
            hostname="host",
            platform_name="Linux",
        )

        self.assertEqual(context.descriptor.id, NodeId("persisted"))
        self.assertEqual(
            context.descriptor.identity_fingerprint,
            node_identity_fingerprint("persisted"),
        )
        self.assertIs(context.provider, analyzer)
        self.assertIs(context.process_manager, process_manager)
        self.assertIs(context.file_manager, file_manager)
        self.assertIs(context.scheduler, scheduler)
        self.assertIs(context.coordinator, coordinator)
        self.assertIs(context.snapshot, snapshot)
        self.assertIs(context.capabilities, capabilities)

    def test_restore_creates_trusted_placeholders_and_skips_local_and_duplicates(
        self,
    ) -> None:
        registry = NodeRegistry(
            NodeContext(
                descriptor=local_node_descriptor(),
                provider=Mock(),
                process_manager=Mock(),
                file_manager=Mock(),
                scheduler=Mock(),
                coordinator=Mock(),
            )
        )
        record = trusted_node_record(
            node_id="peer",
            display_name="Peer",
            hostname="peer-host",
            host="192.0.2.1",
            color="blue",
            identity_fingerprint="fingerprint",
        )
        local_record = trusted_node_record(
            node_id=LOCAL_NODE_ID,
            display_name="Local",
            hostname="localhost",
            host="localhost",
        )
        logger = Mock()

        restore_trusted_nodes(
            registry=registry,
            cluster_state=ClusterState(trusted_nodes=(record, local_record, record)),
            logger=logger,
        )

        contexts = registry.contexts()
        self.assertEqual(len(contexts), 2)
        peer = registry.context(NodeId("peer"))
        self.assertEqual(peer.descriptor.trust, NodeTrustState.TRUSTED)
        self.assertEqual(peer.descriptor.identity_fingerprint, "fingerprint")
        self.assertIsNone(peer.provider)
        self.assertIsNone(peer.scheduler)
        logger.warning.assert_not_called()
