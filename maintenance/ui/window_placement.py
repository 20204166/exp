"""Target-bound placement validation and MOVABLE view projection.

Wires :class:`~maintenance.components.placement.PlacementPolicy` into the
one job class that is genuinely live today: TARGET_BOUND reads/actions
against whichever node the user (or the app, for the implicit local case)
has already named. No production job in this app is MOVABLE yet, so
``build_movable_views`` is the prepared seam for the first MOVABLE workload.

The candidate view is built from live descriptor/connection state already
owned by :mod:`maintenance.nodes` -- no probing, no new polling, no network
calls. For MOVABLE views, cluster/role eligibility is wired from
:class:`~maintenance.cluster.ClusterState` through ``same_cluster`` and
``worker_eligible`` on :class:`~maintenance.components.placement.PlacementView`.
"""

from __future__ import annotations

from typing import Any

from maintenance.cluster import ClusterState
from maintenance.components.cluster_roles import ClusterRole
from maintenance.components.placement import (
    JobClass,
    PlacementDecision,
    PlacementRequest,
    PlacementView,
    placement_view_for_context,
)
from maintenance.nodes import NodeCapability, NodeContext, NodePermission


def target_context(controller: Any, context: NodeContext | None) -> NodeContext | None:
    """Resolve the explicit node context a TARGET_BOUND request must name.

    ``context`` is normally ``controller._selected_context()``. Some
    controller states treat ``None`` as "the local node" implicitly;
    placement always requires an explicit ``target_node_id``, so this
    resolves the registry's own local context in that case. Returns
    ``None`` only when the registry itself is not wired up yet (tests that
    exercise a partially-constructed controller).
    """

    if context is not None:
        return context
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return None
    local_id = registry.local_id()
    if local_id is None:
        return None
    try:
        return registry.context(local_id)
    except KeyError:
        return None


def validate_target_placement(
    controller: Any,
    context: NodeContext | None,
    *,
    operation: str,
    required_capability: NodeCapability,
    required_permission: NodePermission | None = None,
) -> PlacementDecision | None:
    """Return the placement decision for one TARGET_BOUND operation.

    Returns ``None`` when the target cannot be resolved at all (no registry
    wired up yet), so callers can skip validation rather than fail on
    infrastructure that does not exist in that context. Otherwise the
    decision is also recorded on the controller for diagnostics.
    """

    target = target_context(controller, context)
    if target is None:
        return None
    request = PlacementRequest(
        operation=operation,
        job_class=JobClass.TARGET_BOUND,
        target_node_id=target.node_id,
        required_capability=required_capability,
        required_permission=required_permission,
    )
    registry = controller.__dict__.get("_node_registry")
    candidates = registry.contexts() if registry is not None else (target,)
    views = tuple(
        placement_view_for_context(candidate, protocol_compatible=True)
        for candidate in candidates
    )
    decision = controller._coordinator.choose_placement(request, views)
    controller.__dict__["_last_placement_decision"] = decision
    return decision


def build_movable_views(
    controller: Any,
    *,
    cluster_state: ClusterState,
) -> tuple[PlacementView, ...]:
    """Project cluster member contexts into MOVABLE-eligible placement views.

    Wires ``same_cluster``, ``worker_eligible``, and ``active_jobs`` from
    :class:`~maintenance.cluster.ClusterState` into each view.  A node is
    ``same_cluster`` when it has an active (non-revoked) assignment in this
    cluster; ``worker_eligible`` when it holds the WORKER role and is neither
    paused nor revoked.  ``active_jobs`` is 1 for an assigned job, 0 for idle.

    **Authority gate (caller responsibility):** only the current active
    Coordinator may initiate MOVABLE work.  Callers must check
    ``cluster_state.is_active_coordinator`` before invoking this function;
    a Worker, Subcoordinator, or stale former Coordinator must not call it.

    No production MOVABLE job exists yet; this function is the prepared seam.
    """

    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return ()
    assignment_by_id = {
        a.node_id: a
        for a in cluster_state.role_assignments
        if a.node_id is not None
    }
    views = []
    for context in registry.contexts():
        node_id = context.node_id
        assignment = assignment_by_id.get(node_id)
        same_cluster = assignment is not None and not assignment.revoked
        worker_eligible = (
            assignment is not None
            and not assignment.revoked
            and not assignment.paused
            and ClusterRole.WORKER in assignment.roles
        )
        active_jobs = 1 if (assignment is not None and assignment.has_active_job) else 0
        views.append(
            placement_view_for_context(
                context,
                protocol_compatible=True,
                same_cluster=same_cluster,
                worker_eligible=worker_eligible,
                active_jobs=active_jobs,
            )
        )
    return tuple(views)
