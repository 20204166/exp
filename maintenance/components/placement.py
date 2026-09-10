"""Pure, deterministic selection of an execution node for one typed job."""

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum

from maintenance.nodes import NodeCapability, NodeId, NodePermission

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
    transfer_cost_threshold_ms: float = 100.0

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
            isinstance(self.transfer_cost_threshold_ms, bool)
            or not isinstance(self.transfer_cost_threshold_ms, (int, float))
            or not math.isfinite(float(self.transfer_cost_threshold_ms))
            or self.transfer_cost_threshold_ms < 0
        ):
            raise ValueError("transfer cost threshold must be finite and non-negative")


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

    def __init__(self, *, clock: Callable[[], float]) -> None:
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
        if local is not None and transfer_size <= request.transfer_cost_threshold_ms:
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
            <= request.transfer_cost_threshold_ms
        ):
            return (
                f"selected local node {selected.node_id.value} below transfer threshold"
            )
        return f"selected {selected.node_id.value} by active jobs, latency, locality, and stable id"
