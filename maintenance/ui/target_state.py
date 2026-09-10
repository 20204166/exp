"""Pure target-state presentation for node-aware UI surfaces.

This module only projects already-authoritative node metadata.  It does not
contact a provider, grant permissions, or identify a node from its hostname.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from maintenance.nodes import (
    NodeCapability,
    NodeDescriptor,
    NodeIdentityStatus,
    NodePermission,
    NodeStatus,
    NodeTrustState,
)


class TargetState(str, Enum):
    LOCAL = "Local"
    REMOTE_TRUSTED = "Remote trusted"
    REMOTE_READ_ONLY = "Remote read-only"
    OFFLINE = "Offline"
    UNSUPPORTED = "Unsupported"
    PERMISSION_DENIED = "Permission denied"


@dataclass(frozen=True, slots=True)
class TargetPresentation:
    """Text and affordances shared by target-aware pages and dialogs."""

    state: TargetState
    label: str
    identity: str
    status: str
    capabilities: tuple[str, ...]
    can_review: bool
    can_quit: bool
    can_cleanup: bool
    value: str | None = None


_RESOURCE_RULES: dict[str, tuple[NodeCapability, NodePermission]] = {
    "cpu": (NodeCapability.PROCESS_REVIEW, NodePermission.PROCESS_REVIEW),
    "memory": (NodeCapability.PROCESS_REVIEW, NodePermission.PROCESS_REVIEW),
    "storage": (NodeCapability.STORAGE_REVIEW, NodePermission.STORAGE_REVIEW),
    "gpu": (NodeCapability.COMPONENT_READ, NodePermission.COMPONENT_READ),
    "battery": (NodeCapability.COMPONENT_READ, NodePermission.COMPONENT_READ),
    "network": (NodeCapability.COMPONENT_READ, NodePermission.COMPONENT_READ),
}


def render_target_state(
    descriptor: NodeDescriptor,
    snapshot: Any | None = None,
    resource_key: str | None = None,
) -> TargetPresentation:
    """Return the target state and allowed read/action affordances.

    ``snapshot`` is display data only.  If it contains the requested resource,
    its value is retained even when the target is offline; callers decide when
    to replace the snapshot itself.
    """

    capabilities = tuple(
        sorted(capability.value for capability in descriptor.capabilities)
    )
    value: str | None = None
    snapshot_capability: str | None = None
    if snapshot is not None and resource_key is not None:
        try:
            resource = snapshot.resource(resource_key)
            value = resource.value
            snapshot_capability = getattr(resource.capability, "value", None)
        except AttributeError:
            resource = next(
                (
                    resource
                    for resource in getattr(snapshot, "resources", ())
                    if resource.key == resource_key
                ),
                None,
            )
            if resource is not None:
                value = resource.value
                snapshot_capability = getattr(resource.capability, "value", None)
        except KeyError:
            value = None

    identity = f"{descriptor.display_name} · ID {descriptor.id.value}"
    if descriptor.hostname and descriptor.hostname != descriptor.display_name:
        identity += f" · {descriptor.hostname}"
    if descriptor.status is NodeStatus.OFFLINE:
        state = TargetState.OFFLINE
    elif descriptor.identity_status is NodeIdentityStatus.MISMATCH:
        state = TargetState.PERMISSION_DENIED
    else:
        required = _RESOURCE_RULES.get(resource_key or "")
        missing_capability = required is not None and not descriptor.has(required[0])
        missing_permission = (
            required is not None and required[1] not in descriptor.permissions
        )
        if missing_capability or snapshot_capability == "unsupported":
            state = TargetState.UNSUPPORTED
        elif missing_permission:
            state = TargetState.PERMISSION_DENIED
        elif descriptor.trust is NodeTrustState.LOCAL:
            state = TargetState.LOCAL
        elif descriptor.trust in (NodeTrustState.TRUSTED, NodeTrustState.AUTHORISED):
            destructive = (
                descriptor.has(NodeCapability.PROCESS_TERMINATION)
                and NodePermission.PROCESS_TERMINATION in descriptor.permissions
            ) or (
                descriptor.has(NodeCapability.CLEANUP)
                and NodePermission.CLEANUP in descriptor.permissions
            )
            state = (
                TargetState.REMOTE_TRUSTED
                if destructive
                else TargetState.REMOTE_READ_ONLY
            )
        else:
            state = TargetState.PERMISSION_DENIED

    online = descriptor.status is NodeStatus.ONLINE
    trusted = descriptor.trust in (
        NodeTrustState.LOCAL,
        NodeTrustState.TRUSTED,
        NodeTrustState.AUTHORISED,
    )
    required = _RESOURCE_RULES.get(resource_key or "")
    can_review = (
        online
        and trusted
        and state not in (TargetState.UNSUPPORTED, TargetState.PERMISSION_DENIED)
        and (
            required is None
            or (descriptor.has(required[0]) and required[1] in descriptor.permissions)
        )
    )
    can_quit = (
        can_review
        and descriptor.has(NodeCapability.PROCESS_TERMINATION)
        and NodePermission.PROCESS_TERMINATION in descriptor.permissions
    )
    can_cleanup = (
        descriptor.trust is NodeTrustState.LOCAL
        and can_review
        and descriptor.has(NodeCapability.CLEANUP)
        and NodePermission.CLEANUP in descriptor.permissions
    )
    return TargetPresentation(
        state=state,
        label=state.value,
        identity=identity,
        status=descriptor.status.value,
        capabilities=capabilities,
        can_review=can_review,
        can_quit=can_quit,
        can_cleanup=can_cleanup,
        value=value,
    )
