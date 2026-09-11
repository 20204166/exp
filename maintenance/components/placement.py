"""Pure, deterministic selection of an execution node for one typed job."""

import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum

from maintenance.nodes import (
    NodeCapability,
    NodeConnectionStatus,
    NodeContext,
    NodeId,
    NodeIdentityStatus,
    NodePermission,
    NodeStatus,
    NodeTrustState,
)

METRICS_MAX_AGE_SECONDS = 30.0


class JobClass(str, Enum):
    LOCAL_BOUND = "local_bound"
    TARGET_BOUND = "target_bound"
    MOVABLE = "movable"


@dataclass(frozen=True, slots=True)
class PlacementRequest:
    operation: str
    job_class: JobClass
    target_node_id: NodeId | None
    required_capability: NodeCapability
    required_permission: NodePermission | None = None
    input_size_bytes: int = 0
    output_size_bytes: int = 0
    remote_transfer_threshold_bytes: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str) or not self.operation:
            raise ValueError("operation must not be empty")
        if not isinstance(self.job_class, JobClass):
            raise TypeError("job_class must be a JobClass")
        if not isinstance(self.required_capability, NodeCapability):
            raise TypeError("required_capability must be a NodeCapability")
        if self.job_class is JobClass.TARGET_BOUND and self.target_node_id is None:
            raise ValueError("target-bound jobs require a target node")
        if self.job_class is JobClass.LOCAL_BOUND and self.target_node_id is not None:
            raise ValueError("local-bound jobs cannot have a target node")
        for name, value in (
            ("input_size_bytes", self.input_size_bytes),
            ("output_size_bytes", self.output_size_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if (
            isinstance(self.remote_transfer_threshold_bytes, bool)
            or not isinstance(self.remote_transfer_threshold_bytes, int)
            or self.remote_transfer_threshold_bytes < 0
        ):
            raise ValueError(
                "remote transfer threshold must be a non-negative integer"
            )


@dataclass(frozen=True, slots=True)
class PlacementView:
    node_id: NodeId
    is_local: bool
    trusted: bool
    authenticated: bool
    online: bool
    protocol_compatible: bool
    identity_valid: bool
    shutting_down: bool
    capabilities: frozenset[NodeCapability]
    permissions: frozenset[NodePermission]
    active_jobs: int = 0
    recent_latency_ms: float | None = None
    metrics_observed_at: float | None = None


@dataclass(frozen=True, slots=True)
class PlacementDecision:
    selected_node_id: NodeId | None
    eligible_node_ids: tuple[NodeId, ...]
    rejected: tuple[tuple[NodeId, str], ...]
    reason: str


class PlacementPolicy:
    """Choose a node without probing, mutating, authorizing, or executing."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock

    def choose(
        self,
        request: PlacementRequest,
        views: Iterable[PlacementView],
    ) -> PlacementDecision:
        ordered_views = tuple(views)
        eligible: list[PlacementView] = []
        rejected: list[tuple[NodeId, str]] = []
        for view in ordered_views:
            rejection = self._rejection_for(request, view)
            if rejection is None:
                eligible.append(view)
            else:
                rejected.append((view.node_id, rejection))

        eligible.sort(key=lambda view: view.node_id.value)
        if not eligible:
            return PlacementDecision(
                None,
                (),
                tuple(rejected),
                "no eligible nodes",
            )
        selected = self._select(request, eligible)
        return PlacementDecision(
            selected.node_id,
            tuple(view.node_id for view in eligible),
            tuple(rejected),
            self._selection_reason(request, selected, eligible),
        )

    def _rejection_for(
        self, request: PlacementRequest, view: PlacementView
    ) -> str | None:
        if request.job_class is JobClass.LOCAL_BOUND and not view.is_local:
            return "not local"
        if (
            request.job_class is JobClass.TARGET_BOUND
            and view.node_id != request.target_node_id
        ):
            return "target mismatch"
        checks = (
            (not view.trusted, "not trusted"),
            (not view.authenticated, "not authenticated"),
            (not view.online, "offline"),
            (not view.protocol_compatible, "incompatible protocol"),
            (not view.identity_valid, "invalid identity"),
            (view.shutting_down, "shutting down"),
            (
                request.required_capability not in view.capabilities,
                "missing capability",
            ),
            (
                request.required_permission is not None
                and request.required_permission not in view.permissions,
                "missing permission",
            ),
        )
        for failed, reason in checks:
            if failed:
                return reason
        if isinstance(view.active_jobs, bool) or view.active_jobs < 0:
            return "invalid active-job count"
        return None

    def _select(
        self, request: PlacementRequest, eligible: list[PlacementView]
    ) -> PlacementView:
        if request.job_class in (JobClass.LOCAL_BOUND, JobClass.TARGET_BOUND):
            return eligible[0]
        local = next((view for view in eligible if view.is_local), None)
        transfer_size = request.input_size_bytes + request.output_size_bytes
        if (
            local is not None
            and transfer_size <= request.remote_transfer_threshold_bytes
        ):
            return local
        fresh_remote = [
            view for view in eligible if not view.is_local and self._is_fresh(view)
        ]
        if local is not None and transfer_size and not fresh_remote:
            return local
        candidates = fresh_remote + [
            view for view in eligible if view not in fresh_remote
        ]
        return min(
            candidates,
            key=lambda view: (
                view.active_jobs,
                self._latency_key(view),
                not view.is_local,
                view.node_id.value,
            ),
        )

    def _is_fresh(self, view: PlacementView) -> bool:
        return (
            view.recent_latency_ms is not None
            and view.metrics_observed_at is not None
            and self._clock() - view.metrics_observed_at <= METRICS_MAX_AGE_SECONDS
        )

    def _latency_key(self, view: PlacementView) -> float:
        return (
            view.recent_latency_ms
            if self._is_fresh(view) and view.recent_latency_ms is not None
            else math.inf
        )

    def _selection_reason(
        self,
        request: PlacementRequest,
        selected: PlacementView,
        eligible: list[PlacementView],
    ) -> str:
        if request.job_class is JobClass.LOCAL_BOUND:
            return f"selected local node {selected.node_id.value}"
        if request.job_class is JobClass.TARGET_BOUND:
            return f"selected target node {selected.node_id.value}"
        if selected.is_local and (
            request.input_size_bytes + request.output_size_bytes
            <= request.remote_transfer_threshold_bytes
        ):
            return (
                f"selected local node {selected.node_id.value} below transfer threshold"
            )
        return f"selected {selected.node_id.value} by active jobs, latency, locality, and stable id"


def placement_view_for_context(
    context: NodeContext,
    *,
    protocol_compatible: bool | None = None,
    shutting_down: bool = False,
    active_jobs: int = 0,
    recent_latency_ms: float | None = None,
    metrics_observed_at: float | None = None,
) -> PlacementView:
    """Project node state into a fail-closed, read-only placement view."""

    descriptor = context.descriptor
    is_local = descriptor.is_local
    connection_status = context.connection.status
    trusted = is_local or descriptor.trust in (
        NodeTrustState.TRUSTED,
        NodeTrustState.AUTHORISED,
    )
    authenticated = is_local or connection_status is NodeConnectionStatus.ONLINE
    online = descriptor.status is NodeStatus.ONLINE and (
        is_local or connection_status is NodeConnectionStatus.ONLINE
    )
    identity_valid = (
        descriptor.identity_status is not NodeIdentityStatus.MISMATCH
        and connection_status is not NodeConnectionStatus.IDENTITY_CHANGED
    )
    return PlacementView(
        node_id=descriptor.id,
        is_local=is_local,
        trusted=trusted,
        authenticated=authenticated,
        online=online,
        protocol_compatible=(
            is_local if protocol_compatible is None else protocol_compatible
        ),
        identity_valid=identity_valid,
        shutting_down=shutting_down,
        capabilities=descriptor.capabilities,
        permissions=descriptor.permissions,
        active_jobs=active_jobs,
        recent_latency_ms=recent_latency_ms,
        metrics_observed_at=metrics_observed_at,
    )
