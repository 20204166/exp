"""Selected-node bootstrap and cluster persistence adapters."""

from __future__ import annotations

import logging
from typing import Any

from maintenance.cluster import ClusterSaveError
from maintenance.components import node_context
from maintenance.nodes import NodeId
from maintenance.remote import PeerGrant

LOGGER = logging.getLogger(__name__)


def build_local_node_context(
    controller: Any, *, context_builder: Any = node_context
) -> None:
    context = context_builder.build_local_node_context(
        cluster_state=controller._cluster_state,
        analyzer=controller.analyzer,
        process_manager=controller.process_manager,
        file_manager=controller.file_manager,
        scheduler=controller._component_scheduler,
        coordinator=controller._coordinator,
        observer=getattr(controller, "_observer", None),
        snapshot=controller.snapshot,
        capabilities=controller._capabilities,
    )
    controller.__dict__["_capability_counts"] = context.capability_counts
    controller.__dict__["_failed_card_counts"] = context.failed_card_counts
    controller._node_registry.register_context(context)
    controller._selected_node_id = controller._node_registry.select(context.node_id)


def restore_trusted_nodes(
    controller: Any,
    *,
    context_builder: Any = node_context,
    logger: Any = LOGGER,
) -> None:
    registry = controller.__dict__.get("_node_registry")
    state = controller.__dict__.get("_cluster_state")
    if registry is None or state is None:
        return
    context_builder.restore_trusted_nodes(
        registry=registry, cluster_state=state, logger=logger
    )


def save_cluster_state(
    controller: Any,
    state: Any,
    *,
    save_error: type[Exception] = ClusterSaveError,
    logger: Any = LOGGER,
) -> bool:
    try:
        controller._cluster_store.save(state)
    except save_error as error:
        logger.warning("Failed to save cluster settings: %s", error)
        return False
    controller._cluster_state = state
    epoch = state.coordinator_epoch
    server = controller.__dict__.get("_peer_server")
    if server is not None and epoch is not None:
        server.update_cluster_fence(
            cluster_id=state.cluster_id,
            coordinator_epoch=epoch.epoch,
            fencing_token=epoch.fencing_token,
        )
    controller._sync_peer_listener_grants()
    return True


def sync_peer_listener_grants(
    controller: Any,
    *,
    node_id_type: Any = NodeId,
    peer_grant_type: Any = PeerGrant,
) -> None:
    server = controller.__dict__.get("_peer_server")
    if server is None:
        if controller._cluster_state.peer_grants:
            controller._start_peer_listener()
        return
    grants = {
        node_id_type(grant.caller_node_id): peer_grant_type(
            caller_node_id=node_id_type(grant.caller_node_id),
            secret=grant.secret,
            permissions=grant.permissions,
            expires_at=grant.expires_at,
        )
        for grant in controller._cluster_state.peer_grants
    }
    if not grants:
        server.update_grants({})
        return
    server.update_grants(grants)
