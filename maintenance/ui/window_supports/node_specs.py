"""Pure projections from node models to the settings-page view specs."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from maintenance.nodes import NodeId, NodeIdentityStatus, is_trusted_descriptor
from maintenance.ui import cluster_page as ui_cluster
from maintenance.ui import nodes_connections as ui_nodes


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
            )
        )
    return specs


def cluster_node_specs(registry: Any) -> list[ui_cluster.ClusterNodeSpec]:
    """Project registered contexts and untrusted observations for All Systems."""

    selectable = {descriptor.id for descriptor in registry.selectable_descriptors()}
    specs: list[ui_cluster.ClusterNodeSpec] = []
    for context in registry.contexts():
        descriptor = context.descriptor
        snapshot = context.snapshot
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
