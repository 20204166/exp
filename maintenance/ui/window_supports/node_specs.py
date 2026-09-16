"""Pure projections from node models to the settings-page view specs."""

import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from maintenance.nodes import NodeId, NodeIdentityStatus, is_trusted_descriptor
from maintenance.ui import cluster_page as ui_cluster
from maintenance.ui import nodes_connections as ui_nodes
from maintenance.ui.target_state import render_target_state


def discovered_peer_specs(registry: Any) -> list[ui_nodes.DiscoveredPeerSpec]:
    """Project untrusted discovery observations without adding capabilities."""

    return [
        ui_nodes.DiscoveredPeerSpec(
            node_id=candidate.stable_id,
            hostname=candidate.hostname,
            app_version=candidate.app_version,
            compatible=candidate.compatible,
            connectable=candidate.connectable,
            port=candidate.port,
            identity_fingerprint=candidate.identity_fingerprint,
            transport_fingerprint=candidate.transport_fingerprint,
            pairing_state=registry.pairing_state(NodeId(candidate.stable_id)).value,
        )
        for candidate in registry.discovered_candidates()
    ]


def trusted_node_specs(
    registry: Any,
    cluster_state: Any,
    manual_node_ids: Iterable[str] = (),
) -> list[ui_nodes.TrustedNodeSpec]:
    """Project trusted non-manual contexts and preserve their display policy."""

    manual = set(manual_node_ids)
    selectable = {descriptor.id for descriptor in registry.selectable_descriptors()}
    actor = cluster_state.local_assignment
    specs: list[ui_nodes.TrustedNodeSpec] = []
    for context in registry.contexts():
        descriptor = context.descriptor
        if (
            descriptor.is_local
            or not is_trusted_descriptor(descriptor)
            or descriptor.id.value in manual
        ):
            continue
        record = cluster_state.record(descriptor.id.value)
        assignment = next(
            (
                item
                for item in cluster_state.role_assignments
                if item.node_id is not None
                and item.node_id.value == descriptor.id.value
            ),
            None,
        )
        specs.append(
            ui_nodes.TrustedNodeSpec(
                node_id=descriptor.id.value,
                display_name=descriptor.display_name,
                hostname=descriptor.hostname,
                color=descriptor.color,
                status=descriptor.status.value,
                host=record.host if record is not None else descriptor.hostname,
                port=record.port if record is not None else None,
                selectable=descriptor.id in selectable,
                openable=(
                    descriptor.identity_status == NodeIdentityStatus.VERIFIED
                    and descriptor.id in selectable
                    and record is not None
                    and record.port is not None
                ),
                identity_fingerprint=descriptor.identity_fingerprint,
                identity_status=descriptor.identity_status.value,
                permissions=tuple(
                    sorted(permission.value for permission in descriptor.permissions)
                ),
                pairing_state=descriptor.pairing_state.value,
                target_state=render_target_state(descriptor, context.snapshot).label,
                role=(
                    "coordinator"
                    if assignment is not None
                    and any(item.value == "coordinator" for item in assignment.roles)
                    else "subcoordinator"
                    if assignment is not None
                    and any(item.value == "subcoordinator" for item in assignment.roles)
                    else "worker"
                ),
                roles=tuple(
                    sorted(item.value for item in assignment.roles)
                    if assignment is not None
                    else ("worker",)
                ),
                role_editable=any(item.value == "coordinator" for item in actor.roles),
                paused=assignment.paused if assignment is not None else False,
                has_active_job=(
                    assignment.has_active_job if assignment is not None else False
                ),
            )
        )
    return specs


def manual_node_specs(
    registry: Any,
    cluster_state: Any,
    manual_node_ids: Iterable[str] = (),
) -> list[ui_nodes.TrustedNodeSpec]:
    """Project manually configured hosts as non-selectable trusted rows."""

    specs: list[ui_nodes.TrustedNodeSpec] = []
    for node_id in tuple(manual_node_ids):
        try:
            context = registry.context(NodeId(node_id))
        except KeyError:
            continue
        descriptor = context.descriptor
        record = cluster_state.record(node_id)
        specs.append(
            ui_nodes.TrustedNodeSpec(
                node_id=node_id,
                display_name=descriptor.display_name,
                hostname=descriptor.hostname,
                color=descriptor.color,
                status=descriptor.status.value,
                host=record.host if record is not None else descriptor.hostname,
                port=record.port if record is not None else None,
                selectable=False,
                openable=record is not None and record.port is not None,
                is_manual=True,
                identity_fingerprint=descriptor.identity_fingerprint,
                identity_status=descriptor.identity_status.value,
                permissions=tuple(
                    sorted(permission.value for permission in descriptor.permissions)
                ),
                pairing_state=descriptor.pairing_state.value,
                target_state=render_target_state(descriptor, context.snapshot).label,
            )
        )
    return specs


def cluster_node_specs(
    registry: Any,
    *,
    cluster_state: Any = None,
    role_editable: bool = False,
    dashboard_share_active: bool = False,
) -> list[ui_cluster.ClusterNodeSpec]:
    """Project registered contexts and untrusted observations for All Systems."""

    selectable = {descriptor.id for descriptor in registry.selectable_descriptors()}
    specs: list[ui_cluster.ClusterNodeSpec] = []
    for context in registry.contexts():
        descriptor = context.descriptor
        snapshot = context.snapshot
        presentation = render_target_state(descriptor, snapshot)
        assignment = (
            next(
                (
                    item
                    for item in cluster_state.role_assignments
                    if item.node_id is not None
                    and item.node_id.value == descriptor.id.value
                ),
                None,
            )
            if cluster_state is not None
            else None
        )
        specs.append(
            ui_cluster.ClusterNodeSpec(
                node_id=descriptor.id.value,
                display_name=descriptor.display_name,
                hostname=descriptor.hostname,
                color=descriptor.color,
                trust=descriptor.trust.value,
                status=descriptor.status.value,
                capabilities=tuple(
                    sorted(capability.value for capability in descriptor.capabilities)
                ),
                is_local=descriptor.is_local,
                selectable=descriptor.id in selectable,
                last_refresh=(
                    snapshot.scanned_at.strftime("%H:%M:%S")
                    if snapshot is not None
                    else None
                ),
                target_state=presentation.label,
                share_active=dashboard_share_active if descriptor.is_local else False,
                role=descriptor.role,
                role_editable=role_editable,
                has_active_job=(
                    assignment.has_active_job if assignment is not None else False
                ),
            )
        )
    for candidate in registry.discovered_candidates():
        specs.append(
            ui_cluster.ClusterNodeSpec(
                node_id=candidate.stable_id,
                display_name=candidate.hostname,
                hostname=candidate.hostname,
                color=None,
                trust="untrusted",
                status="online" if candidate.last_seen else "unknown",
                capabilities=(),
                is_local=False,
                selectable=False,
                pairing_state=registry.pairing_state(NodeId(candidate.stable_id)).value,
                target_state="Unsupported",
            )
        )
    name_counts = Counter(spec.display_name for spec in specs)
    return [
        replace(
            spec,
            display_name=(
                f"{spec.display_name} ({spec.node_id})"
                if name_counts[spec.display_name] > 1
                else spec.display_name
            ),
        )
        for spec in specs
    ]


def local_cluster_spec(
    registry: Any,
    cluster_state: Any,
    *,
    dashboard_share_expires_at: float = 0.0,
    coordinator_lease_expires_at: float = 0.0,
    now: float | None = None,
) -> ui_nodes.LocalClusterSpec | None:
    """Build the local cluster membership spec from canonical state.

    Returns ``None`` for a solo bootstrap (coordinator of its own single-node
    cluster with no enrolled members) where the section adds no value.
    """
    if now is None:
        now = time.time()

    local_node_id = cluster_state.local_node_id
    epoch = cluster_state.coordinator_epoch
    local_assignment = cluster_state.local_assignment
    local_roles = local_assignment.roles if local_assignment else frozenset()

    is_coordinator = any(r.value == "coordinator" for r in local_roles)
    is_subcoordinator = any(r.value == "subcoordinator" for r in local_roles)

    coordinator_id = epoch.coordinator_id.value if epoch is not None else local_node_id
    joined = coordinator_id != local_node_id

    if not joined and is_coordinator:
        has_workers = any(
            a.node_id is not None and a.node_id.value != local_node_id
            for a in cluster_state.role_assignments
        )
        if not has_workers:
            return None

    if is_coordinator:
        local_role = "coordinator"
    elif is_subcoordinator:
        local_role = "subcoordinator"
    else:
        local_role = "worker"

    coordinator_display_name: str | None = None
    coordinator_status = "unknown"
    if joined:
        try:
            context = registry.context(NodeId(coordinator_id))
            coordinator_display_name = context.descriptor.display_name
            coordinator_status = context.descriptor.status.value
        except (KeyError, AttributeError):
            record = cluster_state.record(coordinator_id)
            if record is not None:
                coordinator_display_name = record.display_name

    return ui_nodes.LocalClusterSpec(
        joined=joined,
        local_role=local_role,
        coordinator_node_id=coordinator_id if joined else None,
        coordinator_display_name=coordinator_display_name,
        coordinator_status=coordinator_status,
        dashboard_share_active=dashboard_share_expires_at > now,
        dashboard_share_expires_at=dashboard_share_expires_at,
        has_peer_grants=bool(cluster_state.peer_grants),
        coordinator_lease_expires_at=coordinator_lease_expires_at,
        coordinator_lease_healthy=coordinator_lease_expires_at > now + 30.0,
    )
