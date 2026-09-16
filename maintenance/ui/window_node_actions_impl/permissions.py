"""Permission and color actions for the window node-actions facade."""

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from maintenance.components.cluster_roles import ClusterRole, RoleAuthorizationError
from maintenance.nodes import NodeId, NodePermission


def set_node_permissions(
    controller: Any,
    node_id: str,
    raw_permissions: frozenset[str],
    *,
    role_state_fn: Callable[[Any], Any],
    save_role_state_fn: Callable[[Any, Any], Any],
) -> None:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    try:
        context = registry.context(NodeId(node_id))
    except KeyError:
        return
    allowed = {permission.value for permission in NodePermission}
    previous = context.descriptor.permissions
    subcoordinator = next(
        (
            assignment
            for assignment in controller._cluster_state.role_assignments
            if assignment.node_id is not None
            and ClusterRole.SUBCOORDINATOR in assignment.roles
            and not assignment.revoked
        ),
        None,
    )
    if (
        ClusterRole.COORDINATOR in controller._cluster_state.local_assignment.roles
        and subcoordinator is not None
        and subcoordinator.node_id != NodeId(node_id)
    ):
        try:
            updated = role_state_fn(controller).grant_capabilities(
                actor=controller._cluster_state.local_assignment,
                subject=subcoordinator.node_id or NodeId(""),
                target=NodeId(node_id),
                permissions=frozenset(
                    NodePermission(value)
                    for value in raw_permissions
                    if value in allowed
                ),
                now=time.time(),
                expires_at=time.time() + 3600.0,
            )
            save_role_state_fn(controller, updated)
        except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
            controller._nodes_error(str(error))
        return
    process_permissions = {
        NodePermission.PROCESS_REVIEW,
        NodePermission.PROCESS_TERMINATION,
        NodePermission.PROCESS_FORCE_TERMINATION,
    }
    requested_process_permissions = frozenset(
        NodePermission(value) for value in raw_permissions if value in allowed
    )
    permissions = frozenset(
        permission for permission in previous if permission not in process_permissions
    ) | requested_process_permissions.intersection(process_permissions)
    context.descriptor = replace(context.descriptor, permissions=permissions)
    records = [
        replace(record, permissions=permissions)
        if record.node_id == node_id
        else record
        for record in controller._cluster_state.trusted_nodes
    ]
    state = replace(
        controller._cluster_state,
        trusted_nodes=tuple(records),
        peer_grants=tuple(
            replace(grant, permissions=permissions)
            if grant.caller_node_id == node_id
            else grant
            for grant in controller._cluster_state.peer_grants
        ),
    )
    if not controller._save_cluster_state(state):
        context.descriptor = replace(context.descriptor, permissions=previous)
        controller._nodes_error("Cluster settings could not be saved")
        return
    controller._refresh_nodes_page()


def set_node_color(controller: Any, node_id: str, color: str) -> None:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    try:
        context = registry.context(NodeId(node_id))
        previous = context.descriptor.color
        registry.set_color(NodeId(node_id), color)
    except KeyError as error:
        controller._nodes_error(str(error))
        return
    records = [
        replace(record, color=color) if record.node_id == node_id else record
        for record in controller._cluster_state.trusted_nodes
    ]
    state = replace(controller._cluster_state, trusted_nodes=tuple(records))
    if not controller._save_cluster_state(state):
        registry.set_color(NodeId(node_id), previous)
        controller._nodes_error("Cluster settings could not be saved")
        return
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
