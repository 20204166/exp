"""Construction and restoration helpers for registered node contexts."""

import logging
import platform
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from maintenance.cluster import ClusterState
from maintenance.nodes import (
    LOCAL_NODE_ID,
    NodeContext,
    NodeDescriptor,
    NodeId,
    NodeIdentityStatus,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
    generate_stable_node_id,
    local_node_descriptor,
    node_identity_fingerprint,
)


def build_local_node_context(
    *,
    cluster_state: ClusterState,
    analyzer: Any,
    process_manager: Any,
    file_manager: Any,
    scheduler: Any,
    coordinator: Any,
    snapshot: Any | None,
    capabilities: dict[str, Any],
    hostname: str | None = None,
    platform_name: str | None = None,
    stable_node_id: Callable[[], str] = generate_stable_node_id,
) -> NodeContext:
    """Build the canonical local context without touching the UI or registry."""

    descriptor = local_node_descriptor(
        hostname=platform.node() if hostname is None else hostname,
        display_name="This System",
        platform_name=(platform.system() if platform_name is None else platform_name),
    )
    descriptor = replace(
        descriptor,
        id=NodeId(cluster_state.local_node_id or stable_node_id()),
        identity_fingerprint=node_identity_fingerprint(cluster_state.local_node_id),
        role=(
            "coordinator"
            if any(
                role.value == "coordinator"
                for role in cluster_state.local_assignment.roles
            )
            else "subcoordinator"
            if any(
                role.value == "subcoordinator"
                for role in cluster_state.local_assignment.roles
            )
            else "worker"
        ),
    )
    return NodeContext(
        descriptor=descriptor,
        provider=analyzer,
        process_manager=process_manager,
        file_manager=file_manager,
        scheduler=scheduler,
        coordinator=coordinator,
        snapshot=snapshot,
        capabilities=capabilities,
    )


def restore_trusted_nodes(
    *,
    registry: NodeRegistry,
    cluster_state: ClusterState,
    logger: logging.Logger,
) -> None:
    """Restore trusted records as non-operational registry placeholders."""

    for record in cluster_state.trusted_nodes:
        if record.node_id in {LOCAL_NODE_ID, cluster_state.local_node_id}:
            continue
        node_id = NodeId(record.node_id)
        try:
            registry.context(node_id)
            continue
        except KeyError:
            pass
        descriptor = NodeDescriptor(
            id=node_id,
            display_name=record.display_name,
            hostname=record.hostname,
            is_local=False,
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.UNKNOWN,
            capabilities=record.capabilities,
            platform=record.platform,
            color=record.color,
            identity_fingerprint=record.identity_fingerprint,
            identity_status=(
                NodeIdentityStatus.VERIFIED
                if record.identity_fingerprint
                else NodeIdentityStatus.UNVERIFIED
            ),
            permissions=record.permissions,
            role=(
                "coordinator"
                if any(
                    assignment.node_id == node_id
                    and any(role.value == "coordinator" for role in assignment.roles)
                    for assignment in cluster_state.role_assignments
                )
                else "subcoordinator"
                if any(
                    assignment.node_id == node_id
                    and any(
                        role.value == "subcoordinator" for role in assignment.roles
                    )
                    for assignment in cluster_state.role_assignments
                )
                else "worker"
            ),
        )
        context = NodeContext(
            descriptor=descriptor,
            provider=None,
            process_manager=None,
            file_manager=None,
            scheduler=None,
            coordinator=None,
        )
        try:
            registry.register_context(context)
        except ValueError as error:
            logger.warning(
                "Failed to restore trusted node %s: %s", record.node_id, error
            )
