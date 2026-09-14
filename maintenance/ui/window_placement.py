"""Target-bound placement validation for the window controller.

Wires the previously-uncalled :class:`~maintenance.components.placement.
PlacementPolicy` into the one job class that is genuinely live today:
TARGET_BOUND reads/actions against whichever node the user (or the app,
for the implicit local case) has already named. No production job in this
app is MOVABLE, so its locality/latency ranking path stays exercised only
by ``tests/test_placement.py``. LOCAL_BOUND work (in-process UI/application
state) never reaches here because it is never modelled as a node operation.

The candidate view is built from live descriptor/connection state already
owned by :mod:`maintenance.nodes` -- no probing, no new polling, no network
calls. Cluster/worker-role eligibility is deliberately out of scope here: it
only matters for choosing *among* several candidates for MOVABLE work, and a
TARGET_BOUND request has exactly one legitimate candidate, the caller's
explicit target.
"""

from __future__ import annotations

from typing import Any

from maintenance.components.placement import (
    JobClass,
    PlacementDecision,
    PlacementRequest,
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
