"""Role and cluster actions for the window node-action facade."""

import threading
import time
from collections.abc import Callable
from dataclasses import replace
from tkinter import messagebox
from typing import Any

from maintenance.cluster import (
    ClusterDataError,
    decode_invite_blob,
    encode_invite_blob,
)
from maintenance.components.cluster_roles import (
    HEARTBEAT_TIMEOUT_SECONDS,
    ClusterRole,
    CoordinatorEpoch,
    RoleAssignment,
    RoleAuthorizationError,
    RoleState,
)
from maintenance.nodes import NodeId, node_operation_key
from maintenance.remote import (
    AuthenticatedNodeProvider,
    SocketRemoteTransport,
    build_trusted_transport,
)

_ROLE_LOCAL = "local_only"
_ROLE_REMOTE = "remote"
_ROLE_FAIL = "fail"


def _role_state(controller: Any) -> RoleState:
    state = controller._cluster_state
    return RoleState(
        assignments=state.role_assignments,
        epoch=state.coordinator_epoch,
        promotion_epochs=state.promotion_epochs,
        capability_grants=state.capability_grants,
    )


def _save_role_state(controller: Any, state: RoleState) -> bool:
    updated = replace(
        controller._cluster_state,
        role_assignments=state.assignments,
        coordinator_epoch=state.epoch,
        capability_grants=state.capability_grants,
    )
    if not controller._save_cluster_state(updated):
        controller._nodes_error("Cluster settings could not be saved")
        return False
    registry = controller.__dict__.get("_node_registry")
    if registry is not None:
        for assignment in state.assignments:
            if assignment.node_id is None:
                continue
            try:
                context = registry.context(assignment.node_id)
            except KeyError:
                continue
            role = (
                "coordinator"
                if ClusterRole.COORDINATOR in assignment.roles
                else "subcoordinator"
                if ClusterRole.SUBCOORDINATOR in assignment.roles
                else "worker"
            )
            context.descriptor = replace(context.descriptor, role=role)
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    _propagate_capability_grants(controller, state)
    return True


def _propagate_capability_grants(controller: Any, state: RoleState) -> None:
    """Push durable grants to reachable targets through their ACL owner."""
    registry = controller.__dict__.get("_node_registry")
    epoch = state.epoch
    if registry is None or epoch is None:
        return
    for target in state.assignments:
        if target.node_id is None or target.node_id.value == epoch.coordinator_id.value:
            continue
        try:
            context = registry.context(target.node_id)
        except KeyError:
            continue
        provider = context.provider
        if provider is None or not hasattr(provider, "sync_capability_grant"):
            continue
        for subject in state.assignments:
            if (
                subject.node_id is None
                or subject.node_id == target.node_id
                or ClusterRole.SUBCOORDINATOR not in subject.roles
                or subject.revoked
            ):
                continue
            grant = state.capability_grant(
                subject.node_id, target.node_id, now=time.time()
            )
            permissions = (
                []
                if grant is None
                else sorted(permission.value for permission in grant.permissions)
            )
            expires_at = time.time() + 1.0 if grant is None else grant.expires_at
            try:
                provider.sync_capability_grant(
                    subject.node_id.value,
                    target.node_id.value,
                    permissions,
                    expires_at=expires_at,
                    cluster_id=controller._cluster_state.cluster_id,
                    epoch=epoch.epoch,
                    fencing_token=epoch.fencing_token,
                )
            except Exception as error:  # noqa: BLE001 - target remains fail-closed.
                controller._nodes_error(
                    f"Could not update permissions on {target.node_id}: {error}"
                )


def _classify_role_dispatch(controller: Any, node_id: str) -> tuple[str, str | None]:
    """Classify a role mutation as local-only, remote, or fail-closed.

    Returns (kind, reason):
    - (_ROLE_LOCAL, None)   — legitimate local-only: self, no cluster enrollment,
                              or non-cluster bootstrap state.
    - (_ROLE_REMOTE, None)  — dispatch via the remote control plane.
    - (_ROLE_FAIL, reason)  — enrolled cluster member; surface reason; do NOT
                              fall back to local-only mutation.

    REMOTE FAILURE IS NOT LOCAL PERMISSION TO MUTATE.
    An enrolled node is a cluster entity: connectivity or authority failures must
    surface as explicit errors, not be silently absorbed as local-only writes that
    create divergence between the Coordinator and the Worker.

    Legitimate local-only conditions (return _ROLE_LOCAL):
    - Operating on the local node itself.
    - No RoleAssignment for the target (not cluster-enrolled; may be a newly
      trusted peer or a legacy solo-bootstrap record).

    Fail-closed conditions (return _ROLE_FAIL):
    - Enrolled member + no coordinator_epoch: inconsistent cluster state.
    - Enrolled member + local node is not the Coordinator: cannot authorize RPC.
    - Enrolled member + assignment is revoked: use Revoke to manage state.
    - Enrolled member + no saved connection record: cannot reach target.
    - Enrolled member + port is None: target endpoint unavailable (offline).
    """
    state = controller._cluster_state

    # Operating on self is always a local action.
    if node_id == state.local_node_id:
        return _ROLE_LOCAL, None

    # A node with no RoleAssignment is not cluster-enrolled; local bookkeeping
    # is valid (e.g. a freshly-trusted peer awaiting explicit cluster admission).
    assignment = _role_state(controller).assignment_for(NodeId(node_id))
    if assignment is None:
        return _ROLE_LOCAL, None

    # The node IS enrolled.  Every further failure must be surfaced explicitly;
    # do not silently reinterpret a cluster member mutation as a local write.

    if state.coordinator_epoch is None:
        return (
            _ROLE_FAIL,
            "Coordinator epoch unavailable — cluster state is inconsistent",
        )

    if ClusterRole.COORDINATOR not in state.local_assignment.roles:
        return _ROLE_FAIL, "This node is not the current Coordinator"

    if assignment.revoked:
        return _ROLE_FAIL, "Target is already revoked"

    record = state.record(node_id)
    if record is None:
        return _ROLE_FAIL, "No connection record for enrolled cluster member"

    if record.port is None:
        return _ROLE_FAIL, "Target endpoint is unavailable (offline or no port saved)"

    return _ROLE_REMOTE, None


def _remote_role_op(
    controller: Any,
    node_id: str,
    op_key: str,
    rpc_call: Callable[[Any], Any],
    local_op: Callable[[], Any],
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    """Dispatch a role RPC to node_id; run local_op only on success (REMOTE FIRST)."""
    record = controller._cluster_state.record(node_id)
    if record is None or record.port is None:
        controller._nodes_error("No connection details saved for that node")
        return
    node = NodeId(node_id)

    def task(
        _cancel: threading.Event,
        _progress: Callable[[str], None],
    ) -> Any:
        provider = provider_cls(
            node_id=node,
            secret=record.secret,
            caller_node_id=NodeId(controller._cluster_state.local_node_id),
            transport=build_trusted_transport(record, transport_cls=transport_cls),
        )
        return rpc_call(provider)

    controller._coordinator.run(
        node_operation_key(node, op_key),
        task,
        on_result=lambda _key, _result: local_op(),
        on_error=lambda _key, message: controller._nodes_error(message),
    )


def set_node_roles(
    controller: Any,
    node_id: str,
    roles: frozenset[str],
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    try:
        requested = frozenset(ClusterRole(value) for value in roles)
        current = _role_state(controller)
        assignment, _change = current.assign(
            actor=controller._cluster_state.local_assignment,
            target=NodeId(node_id),
            roles=requested,
        )
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))
        return
    dispatch, reason = _classify_role_dispatch(controller, node_id)
    if dispatch == _ROLE_FAIL:
        controller._nodes_error(reason)
        return
    if dispatch == _ROLE_REMOTE:
        epoch = controller._cluster_state.coordinator_epoch

        def rpc_call(provider: Any) -> Any:
            return provider.assign_role(
                node_id,
                sorted(r.value for r in requested),
                cluster_id=controller._cluster_state.cluster_id,
                epoch=epoch.epoch,
                fencing_token=epoch.fencing_token,
            )

        _remote_role_op(
            controller,
            node_id,
            "assign_role",
            rpc_call,
            lambda: _save_role_state(controller, assignment),
            provider_cls=provider_cls,
            transport_cls=transport_cls,
        )
    else:
        _save_role_state(controller, assignment)


def create_cluster_invite(controller: Any) -> str | None:
    """Mint a join invite bound to this node's live cluster fence.

    Only the active Coordinator may invite a peer into its cluster --
    membership admission on the target side (see
    ``window_discovery.handle_role_request``'s ``consume_invite`` branch)
    trusts this invite's stamped fence, so only a Coordinator may stamp one.
    """

    state = controller._cluster_state
    if ClusterRole.COORDINATOR not in state.local_assignment.roles:
        controller._nodes_error("Only the active Coordinator can create an invite")
        return None
    invite = state.create_invite()
    if not controller._save_cluster_state(state):
        state.active_invites = tuple(
            item
            for item in state.active_invites
            if item.token_hash != invite.token_hash
        )
        controller._nodes_error("Cluster settings could not be saved")
        return None
    return encode_invite_blob(invite)


def _solo_bootstrap_violation(state: Any) -> str | None:
    """Refuse to join when leaving would silently destroy a real cluster."""

    message = (
        "This machine already coordinates a cluster with other members; "
        "leaving it to join another cluster is not supported yet."
    )
    if (
        len(state.role_assignments) != 1
        or state.capability_grants
        or state.promotion_epochs
    ):
        return message
    (only,) = state.role_assignments
    if (
        only.node_id is None
        or only.node_id.value != state.local_node_id
        or only.paused
        or only.revoked
        or only.roles != frozenset({ClusterRole.COORDINATOR, ClusterRole.WORKER})
    ):
        return message
    return None


def join_cluster_via_invite(
    controller: Any,
    node_id: str,
    blob: str,
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    """Ask a trusted peer's Coordinator to admit this node into its cluster.

    Pairing establishes trust only; this is the separate, explicit operation
    that converges ``cluster_id`` across two already-trusted peers. Refuses
    up front if the local cluster is not still an untouched solo bootstrap
    (see ``_solo_bootstrap_violation``), so a machine already coordinating a
    real cluster of its own can never have that membership silently
    replaced.
    """

    try:
        invite = decode_invite_blob(blob)
    except ClusterDataError as error:
        controller._nodes_error(f"That invite could not be read: {error}")
        return
    guard = _solo_bootstrap_violation(controller._cluster_state)
    if guard is not None:
        controller._nodes_error(guard)
        return
    record = controller._cluster_state.record(node_id)
    if record is None:
        controller._nodes_error("No connection details saved for that node")
        return
    if record.port is None:
        controller._nodes_error("That node has no authenticated remote port")
        return
    node = NodeId(node_id)

    def task() -> dict[str, Any]:
        provider = provider_cls(
            node_id=node,
            secret=record.secret,
            caller_node_id=NodeId(controller._cluster_state.local_node_id),
            transport=build_trusted_transport(record, transport_cls=transport_cls),
        )
        return provider.consume_invite(
            invite.token,
            cluster_id=invite.cluster_id,
            epoch=invite.epoch,
            fencing_token=invite.fencing_token,
        )

    def on_success(response: dict[str, Any]) -> None:
        _apply_cluster_join(controller, response)

    def on_error(message: str) -> None:
        controller._nodes_error(f"Could not join cluster: {message}")

    key = node_operation_key(node, "join_cluster")

    def coordinated_task(
        _cancel_event: threading.Event,
        _progress: Callable[[str], None],
    ) -> dict[str, Any]:
        return task()

    controller._coordinator.run(
        key,
        coordinated_task,
        on_result=lambda _key, result: on_success(result),
        on_error=lambda _key, message: on_error(message),
    )


def _apply_cluster_join(controller: Any, response: dict[str, Any]) -> None:
    try:
        cluster_id = str(response["cluster_id"])
        coordinator_id = str(response["coordinator_id"])
        epoch = int(response["epoch"])
        fencing_token = str(response["fencing_token"])
    except (KeyError, TypeError, ValueError) as error:
        controller._nodes_error(f"Join response was invalid: {error}")
        return
    now = time.time()
    updated = replace(
        controller._cluster_state,
        cluster_id=cluster_id,
        coordinator_epoch=CoordinatorEpoch(
            epoch=epoch,
            coordinator_id=NodeId(coordinator_id),
            fencing_token=fencing_token,
            issued_at=now,
            lease_expires_at=now + HEARTBEAT_TIMEOUT_SECONDS,
        ),
        role_assignments=(
            RoleAssignment(
                frozenset({ClusterRole.COORDINATOR, ClusterRole.WORKER}),
                node_id=NodeId(coordinator_id),
            ),
            RoleAssignment(
                frozenset({ClusterRole.WORKER}),
                node_id=NodeId(controller._cluster_state.local_node_id),
            ),
        ),
        capability_grants=(),
        promotion_epochs=frozenset(),
    )
    if not controller._save_cluster_state(updated):
        controller._nodes_error("Cluster settings could not be saved")
        return
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    controller._nodes_status(f"Joined cluster {cluster_id}")


def pause_node(
    controller: Any,
    node_id: str,
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    try:
        new_state = _role_state(controller).pause(
            actor=controller._cluster_state.local_assignment,
            target=NodeId(node_id),
        )
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))
        return
    dispatch, reason = _classify_role_dispatch(controller, node_id)
    if dispatch == _ROLE_FAIL:
        controller._nodes_error(reason)
        return
    if dispatch == _ROLE_REMOTE:
        epoch = controller._cluster_state.coordinator_epoch

        def rpc_call(provider: Any) -> Any:
            return provider.pause_worker(
                node_id,
                cluster_id=controller._cluster_state.cluster_id,
                epoch=epoch.epoch,
                fencing_token=epoch.fencing_token,
            )

        _remote_role_op(
            controller,
            node_id,
            "pause_worker",
            rpc_call,
            lambda: _save_role_state(controller, new_state),
            provider_cls=provider_cls,
            transport_cls=transport_cls,
        )
    else:
        _save_role_state(controller, new_state)


def resume_node(
    controller: Any,
    node_id: str,
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    try:
        new_state = _role_state(controller).resume(
            actor=controller._cluster_state.local_assignment,
            target=NodeId(node_id),
        )
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))
        return
    dispatch, reason = _classify_role_dispatch(controller, node_id)
    if dispatch == _ROLE_FAIL:
        controller._nodes_error(reason)
        return
    if dispatch == _ROLE_REMOTE:
        epoch = controller._cluster_state.coordinator_epoch

        def rpc_call(provider: Any) -> Any:
            return provider.resume_worker(
                node_id,
                cluster_id=controller._cluster_state.cluster_id,
                epoch=epoch.epoch,
                fencing_token=epoch.fencing_token,
            )

        _remote_role_op(
            controller,
            node_id,
            "resume_worker",
            rpc_call,
            lambda: _save_role_state(controller, new_state),
            provider_cls=provider_cls,
            transport_cls=transport_cls,
        )
    else:
        _save_role_state(controller, new_state)


def remove_job_node(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    if not messagebox_module.askyesno(
        "Remove job",
        "This removes the active assignment and reduces normal collection to 20%.",
        parent=controller.master,
    ):
        return
    try:
        new_state = _role_state(controller).remove_job(
            actor=controller._cluster_state.local_assignment,
            target=NodeId(node_id),
        )
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))
        return
    dispatch, reason = _classify_role_dispatch(controller, node_id)
    if dispatch == _ROLE_FAIL:
        controller._nodes_error(reason)
        return
    if dispatch == _ROLE_REMOTE:
        epoch = controller._cluster_state.coordinator_epoch

        def rpc_call(provider: Any) -> Any:
            return provider.remove_job(
                node_id,
                cluster_id=controller._cluster_state.cluster_id,
                epoch=epoch.epoch,
                fencing_token=epoch.fencing_token,
            )

        def local_op() -> None:
            _save_role_state(controller, new_state)
            controller._nodes_status(f"Removed job for {node_id}")

        _remote_role_op(
            controller,
            node_id,
            "remove_job",
            rpc_call,
            local_op,
            provider_cls=provider_cls,
            transport_cls=transport_cls,
        )
    else:
        _save_role_state(controller, new_state)
        controller._nodes_status(f"Removed job for {node_id}")


def revoke_node(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
    revoke_trusted_node_fn: Callable[[Any, str], Any] = lambda _controller, _node_id: (
        None
    ),
) -> None:
    if not messagebox_module.askyesno(
        "Revoke",
        "This invalidates trust and permissions. A new invite is required to reconnect.",
        parent=controller.master,
    ):
        return
    try:
        role_state = _role_state(controller)
        assignment = role_state.assignment_for(NodeId(node_id))
        if assignment is None or assignment.revoked:
            revoke_trusted_node_fn(controller, node_id)
            return
        revoked_state = role_state.revoke(
            actor=controller._cluster_state.local_assignment,
            target=NodeId(node_id),
        )
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))
        return
    dispatch, reason = _classify_role_dispatch(controller, node_id)
    if dispatch == _ROLE_FAIL:
        controller._nodes_error(reason)
        return
    if dispatch == _ROLE_REMOTE:
        epoch = controller._cluster_state.coordinator_epoch

        def rpc_call(provider: Any) -> Any:
            return provider.revoke_worker(
                node_id,
                cluster_id=controller._cluster_state.cluster_id,
                epoch=epoch.epoch,
                fencing_token=epoch.fencing_token,
            )

        def local_op() -> None:
            if _save_role_state(controller, revoked_state):
                revoke_trusted_node_fn(controller, node_id)

        _remote_role_op(
            controller,
            node_id,
            "revoke_worker",
            rpc_call,
            local_op,
            provider_cls=provider_cls,
            transport_cls=transport_cls,
        )
    else:
        if _save_role_state(controller, revoked_state):
            revoke_trusted_node_fn(controller, node_id)
