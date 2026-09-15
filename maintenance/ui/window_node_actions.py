"""Node administration actions used by the window controller.

The functions in this module deliberately keep the controller as an explicit
dependency.  This preserves the controller's dynamic callback seams while
keeping node administration out of the window's composition code.
"""

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from tkinter import messagebox, simpledialog
from typing import Any

from maintenance.cluster import PeerGrantRecord, trusted_node_record
from maintenance.components.cluster_roles import (
    ClusterRole,
    RoleAuthorizationError,
    RoleState,
)
from maintenance.components.coordinator import ComponentRefreshScheduler
from maintenance.nodes import (
    READ_PERMISSIONS,
    NodeCapability,
    NodeContext,
    NodeDescriptor,
    NodeId,
    NodeIdentityStatus,
    NodePermission,
    NodeStatus,
    NodeTrustState,
    is_trusted_descriptor,
    node_operation_key,
)
from maintenance.remote import (
    READ_CAPABILITIES,
    AuthenticatedNodeProvider,
    PairingTransaction,
    RemoteProcessActionBackend,
    SocketRemoteTransport,
    TLSRemoteTransport,
    build_trusted_transport,
)
from maintenance.ui import discovery_refresh as ui_discovery_refresh
from maintenance.ui.node_presentation import fingerprint_lines


def _pairing_confirmation(candidate: Any) -> str:
    """Keep the full identity values readable without changing their value."""

    fingerprint = candidate.identity_fingerprint or "Unavailable"
    transport_fingerprint = getattr(candidate, "transport_fingerprint", None)
    fingerprint_text = "\n".join(fingerprint_lines(fingerprint))
    return (
        f"Pair {candidate.hostname}?\n\n"
        f"Stable node ID: {candidate.stable_id}\n\n"
        f"Identity fingerprint:\n{fingerprint_text}\n\n"
        f"TLS fingerprint: {transport_fingerprint or 'Unavailable'}\n\n"
        "Confirm this fingerprint through a trusted channel before pairing."
    )


def apply_discovery_enabled(controller: Any, enabled: bool) -> None:
    candidate = replace(controller._cluster_state, discovery_enabled=enabled)
    if not controller._save_cluster_state(candidate):
        page = getattr(controller, "nodes_page", None)
        if page is not None:
            page.set_discovery_enabled(controller._cluster_state.discovery_enabled)
            page.show_error("Cluster settings could not be saved")
        return
    if enabled:
        controller._start_discovery()
    else:
        controller._stop_discovery()
    controller._nodes_status(
        f"Discovery {'enabled' if enabled else 'disabled'} and saved"
    )


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


def set_node_roles(controller: Any, node_id: str, roles: frozenset[str]) -> None:
    try:
        requested = frozenset(ClusterRole(value) for value in roles)
        current = _role_state(controller)
        assignment, _change = current.assign(
            actor=controller._cluster_state.local_assignment,
            target=NodeId(node_id),
            roles=requested,
        )
        _save_role_state(controller, assignment)
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))


def pause_node(controller: Any, node_id: str) -> None:
    try:
        _save_role_state(
            controller,
            _role_state(controller).pause(
                actor=controller._cluster_state.local_assignment,
                target=NodeId(node_id),
            ),
        )
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))


def resume_node(controller: Any, node_id: str) -> None:
    try:
        _save_role_state(
            controller,
            _role_state(controller).resume(
                actor=controller._cluster_state.local_assignment,
                target=NodeId(node_id),
            ),
        )
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))


def remove_connection_node(
    controller: Any, node_id: str, *, messagebox_module: Any = messagebox
) -> None:
    if not messagebox_module.askyesno(
        "Remove connection",
        "The connection will close, but trusted reconnect remains available.",
        parent=controller.master,
    ):
        return
    node = NodeId(node_id)
    manager = controller._peer_connections()
    if manager is not None:
        manager.disconnect_manual(node)
    registry = controller.__dict__.get("_node_registry")
    if registry is not None:
        try:
            context = registry.context(node)
        except KeyError:
            context = None
        if context is not None:
            controller._cancel_node_operations(context)
            controller._cancel_peer_connection(context)
            context.provider = None
            context.process_manager = None
            context.scheduler = None
            context.coordinator = None
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    controller._rebuild_node_selector()
    if controller.__dict__.get("_selected_node_id") == node and registry is not None:
        local_id = registry.local_id()
        if local_id is not None:
            registry.select(local_id)
    if (
        registry is not None
        and controller.__dict__.get("_selected_node_id") != registry.selected_id()
    ):
        controller.__dict__["_selected_node_id"] = registry.selected_id()
        context = registry.selected_context()
        controller._sync_selected_context_mirrors(context)
        controller._render_selected_node(context)
    controller._nodes_status(f"Removed connection to {node_id}")


def remove_job_node(
    controller: Any, node_id: str, *, messagebox_module: Any = messagebox
) -> None:
    if not messagebox_module.askyesno(
        "Remove job",
        "This removes the active assignment and reduces normal collection to 20%.",
        parent=controller.master,
    ):
        return
    try:
        _save_role_state(
            controller,
            _role_state(controller).remove_job(
                actor=controller._cluster_state.local_assignment,
                target=NodeId(node_id),
            ),
        )
        controller._nodes_status(f"Removed job for {node_id}")
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))


def revoke_node(
    controller: Any, node_id: str, *, messagebox_module: Any = messagebox
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
            # A trusted node without a role record, or one whose revocation was
            # already persisted by an interrupted earlier revocation, has no
            # role to revoke; revocation means removing trust entirely.
            revoke_trusted_node(controller, node_id)
            return
        if not _save_role_state(
            controller,
            role_state.revoke(
                actor=controller._cluster_state.local_assignment,
                target=NodeId(node_id),
            ),
        ):
            return
        # Role revocation and trust/provider cleanup are one user-visible action.
        revoke_trusted_node(controller, node_id)
    except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
        controller._nodes_error(str(error))


@dataclass(slots=True)
class _PairingAttempt:
    node: NodeId
    candidate: Any
    descriptor: NodeDescriptor | None
    record: Any
    grant: PeerGrantRecord
    previous_context: Any
    previous_selected: bool
    previous_state: Any
    transaction: PairingTransaction | None = None
    confirm_started: bool = False


def _restore_pairing(
    controller: Any, attempt: _PairingAttempt, *, persist: bool = False
) -> bool:
    controller._cluster_state = attempt.previous_state
    persisted = True
    if persist:
        persisted = bool(controller._save_cluster_state(attempt.previous_state))
    registry = controller._node_registry
    if attempt.descriptor is not None:
        registry.revoke_trusted(attempt.node)
    if attempt.previous_context is not None:
        registry.register_context(attempt.previous_context)
        registry.update_discovered(attempt.candidate)
        if attempt.previous_selected:
            registry.select(attempt.node)
    else:
        registry.update_discovered(attempt.candidate)
        registry.fail_pairing(attempt.node)
    return persisted


def _prepare_pairing(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any,
    promote: bool = True,
) -> _PairingAttempt | None:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return None
    candidates = {
        candidate.stable_id: candidate for candidate in registry.discovered_candidates()
    }
    candidate = candidates.get(node_id)
    if candidate is None:
        controller._nodes_error("That peer is no longer visible on the network")
        return None
    if not candidate.identity_fingerprint:
        controller._nodes_error("That peer did not provide an identity fingerprint")
        return None
    node = NodeId(node_id)
    try:
        registry.begin_pairing(node)
    except (KeyError, ValueError) as error:
        controller._nodes_error(str(error))
        return None
    if not messagebox_module.askyesno(
        "Confirm peer fingerprint",
        _pairing_confirmation(candidate),
        parent=controller.master,
    ):
        registry.fail_pairing(node)
        controller._refresh_nodes_page()
        controller._nodes_status(f"Pairing cancelled for {candidate.hostname}")
        return None
    try:
        previous_context = registry.context(node)
        previous_selected = registry.selected_id() == node
    except KeyError:
        previous_context = None
        previous_selected = False
    descriptor: NodeDescriptor | None = None
    if promote:
        try:
            descriptor = registry.promote_to_trusted(
                node, capabilities=READ_CAPABILITIES
            )
        except (KeyError, ValueError) as error:
            registry.fail_pairing(node)
            controller._refresh_nodes_page()
            controller._nodes_error(str(error))
            return None
        assert descriptor is not None
        descriptor = replace(descriptor, permissions=READ_PERMISSIONS)
        registry.context(node).descriptor = descriptor
    host = candidate.addresses[0] if candidate.addresses else candidate.hostname
    record = trusted_node_record(
        node_id=node_id,
        display_name=candidate.hostname
        if descriptor is None
        else descriptor.display_name,
        hostname=candidate.hostname if descriptor is None else descriptor.hostname,
        host=host,
        platform=candidate.platform if descriptor is None else descriptor.platform,
        port=candidate.port,
        capabilities=READ_CAPABILITIES,
        permissions=READ_PERMISSIONS,
        identity_fingerprint=candidate.identity_fingerprint,
        transport_fingerprint=candidate.transport_fingerprint,
    )
    grant = PeerGrantRecord(
        caller_node_id=controller._cluster_state.local_node_id,
        secret=record.secret,
        permissions=READ_PERMISSIONS,
    )
    return _PairingAttempt(
        node=node,
        candidate=candidate,
        descriptor=descriptor,
        record=record,
        grant=grant,
        previous_context=previous_context,
        previous_selected=previous_selected,
        previous_state=controller._cluster_state,
    )


def _finish_pairing(
    controller: Any, attempt: _PairingAttempt, provisioned: bool
) -> bool:
    if not provisioned:
        _restore_pairing(controller, attempt)
        controller._nodes_error("Target did not provision the peer grant")
        return False
    if attempt.descriptor is None:
        try:
            attempt.descriptor = replace(
                controller._node_registry.promote_to_trusted(
                    attempt.node, capabilities=READ_CAPABILITIES
                ),
                permissions=READ_PERMISSIONS,
            )
            controller._node_registry.context(
                attempt.node
            ).descriptor = attempt.descriptor
        except (KeyError, ValueError) as error:
            _restore_pairing(controller, attempt)
            controller._nodes_error(str(error))
            return False
    descriptor = attempt.descriptor
    assert descriptor is not None
    node_id = attempt.node.value
    existing_record = controller._cluster_state.record(node_id)
    trusted_nodes = tuple(
        attempt.record if item.node_id == node_id else item
        for item in controller._cluster_state.trusted_nodes
    )
    if existing_record is None:
        trusted_nodes = (*trusted_nodes, attempt.record)
    role_state = _role_state(controller).clear_revocation(attempt.node)
    state = replace(
        controller._cluster_state,
        trusted_nodes=trusted_nodes,
        role_assignments=role_state.assignments,
    )
    if not controller._save_cluster_state(state):
        _restore_pairing(controller, attempt)
        controller._nodes_error("Cluster settings could not be saved")
        return False
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    controller._rebuild_node_selector()
    controller._nodes_status(f"Paired {descriptor.display_name} (read-only)")
    controller._reconcile_peer_connections()
    return True


def pair_discovered_node(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provision_target_grant: Callable[[PeerGrantRecord], bool] | None = None,
) -> None:
    attempt = _prepare_pairing(controller, node_id, messagebox_module=messagebox_module)
    if attempt is None:
        return
    provisioner = provision_target_grant or controller.__dict__.get(
        "_provision_target_grant"
    )
    if not callable(provisioner):
        if (
            attempt.candidate.port is None
            or not attempt.candidate.transport_fingerprint
        ):
            _restore_pairing(controller, attempt)
            controller._refresh_nodes_page()
            controller._nodes_error(
                "Pairing requires explicit target-side grant provisioning"
            )
            return
        provisioner = lambda grant: bool(
            request_target_grant(controller, attempt.candidate, grant)
        )
    if not callable(provisioner):
        _restore_pairing(controller, attempt)
        controller._refresh_nodes_page()
        controller._nodes_error(
            "Pairing requires explicit target-side grant provisioning"
        )
        return
    try:
        provisioned = bool(provisioner(attempt.grant))
    except Exception:  # noqa: BLE001 - provisioning failure is fail-closed.
        provisioned = False
    _finish_pairing(controller, attempt, provisioned)


def pair_discovered_node_async(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provision_target_grant: Callable[[PeerGrantRecord], bool] | None = None,
    dialog: Any = None,
) -> None:
    """Pair on Tk while coordinating only target-side provisioning."""

    initial_provisioner = provision_target_grant or controller.__dict__.get(
        "_provision_target_grant"
    )
    network_flow = not callable(initial_provisioner)
    attempt = _prepare_pairing(
        controller,
        node_id,
        messagebox_module=messagebox_module,
        promote=not network_flow,
    )
    if attempt is None:
        return
    provisioner: Any = initial_provisioner
    provisioner_accepts_cancel = False
    if not callable(provisioner):
        if (
            attempt.candidate.port is None
            or not attempt.candidate.transport_fingerprint
        ):
            _restore_pairing(controller, attempt)
            controller._refresh_nodes_page()
            controller._nodes_error(
                "Pairing requires explicit target-side grant provisioning"
            )
            if dialog is not None:
                dialog.show_error(
                    "Pairing requires explicit target-side grant provisioning"
                )
            return
        provisioner = lambda grant, cancel_event: request_target_grant(
            controller, attempt.candidate, grant, cancel_event=cancel_event
        )
        provisioner_accepts_cancel = True
    key = node_operation_key(attempt.node, "pair")
    generations = controller.__dict__.setdefault("_pairing_generations", {})
    generation = int(generations.get(attempt.node, 0)) + 1
    generations[attempt.node] = generation
    attempts = controller.__dict__.setdefault("_pairing_attempts", {})
    attempts[attempt.node] = attempt
    if dialog is not None:
        dialog.set_pending()

    def is_current() -> bool:
        return (
            generations.get(attempt.node) == generation
            and attempts.get(attempt.node) is attempt
        )

    def task(
        cancel_event: threading.Event,
        _progress: Callable[[str], None],
    ) -> Any:
        if cancel_event.is_set():
            return False
        provisioned = (
            provisioner(attempt.grant, cancel_event)
            if provisioner_accepts_cancel
            else provisioner(attempt.grant)
        )
        if cancel_event.is_set() and not isinstance(provisioned, PairingTransaction):
            return False
        return provisioned

    def on_result(_key: str, provisioned: Any) -> None:
        if not is_current():
            if isinstance(provisioned, PairingTransaction):
                _schedule_pairing_abort(controller, provisioned)
            return
        if network_flow and isinstance(provisioned, PairingTransaction):
            attempt.transaction = provisioned
            if not _finish_pairing(controller, attempt, True):
                attempts.pop(attempt.node, None)
                _schedule_pairing_abort(controller, provisioned)
                if dialog is not None:
                    dialog.show_error("Cluster settings could not be saved")
                return
            _schedule_pairing_confirm(controller, attempt, dialog, is_current)
            return
        attempts.pop(attempt.node, None)
        if _finish_pairing(controller, attempt, provisioned):
            if dialog is not None:
                dialog.complete()
        elif dialog is not None:
            dialog.show_error(
                "Target did not provision the peer grant"
                if not provisioned
                else "Cluster settings could not be saved"
            )

    def on_error(_key: str, _message: str) -> None:
        if not is_current():
            return
        attempts.pop(attempt.node, None)
        _finish_pairing(controller, attempt, False)
        if dialog is not None:
            dialog.show_error("Target did not provision the peer grant")

    controller._coordinator.run(
        key,
        task,
        on_result=on_result,
        on_error=on_error,
    )


def cancel_pairing(controller: Any, node_id: str) -> None:
    node = NodeId(node_id)
    attempts = controller.__dict__.setdefault("_pairing_attempts", {})
    attempt = attempts.get(node)
    if attempt is not None and attempt.confirm_started:
        return
    generations = controller.__dict__.setdefault("_pairing_generations", {})
    generations[node] = int(generations.get(node, 0)) + 1
    controller._coordinator.cancel(node_operation_key(node, "pair"))
    attempt = attempts.pop(node, None)
    if attempt is not None:
        if attempt.transaction is not None:
            _schedule_pairing_abort(controller, attempt.transaction)
        restored = _restore_pairing(
            controller, attempt, persist=attempt.transaction is not None
        )
        if not restored:
            controller._nodes_error(
                "Pairing recovery failed: could not restore saved cluster state"
            )
        controller._refresh_nodes_page()


def request_target_grant(
    controller: Any,
    candidate: Any,
    grant: PeerGrantRecord,
    *,
    cancel_event: threading.Event | None = None,
) -> PairingTransaction | bool:
    """Request target approval before the initiator persists trust."""

    if candidate.port is None or not candidate.transport_fingerprint:
        return False
    local = controller._node_registry.context(
        controller._node_registry.local_id() or NodeId("local")
    ).descriptor
    transport = TLSRemoteTransport(
        candidate.addresses[0] if candidate.addresses else candidate.hostname,
        candidate.port,
        expected_fingerprint=candidate.transport_fingerprint,
    )
    result = AuthenticatedNodeProvider.request_pairing(
        transport=transport,
        caller_node_id=NodeId(controller._cluster_state.local_node_id),
        identity_fingerprint=local.identity_fingerprint or "",
        transport_fingerprint=controller.__dict__.get("_tls_fingerprint", ""),
        proposed_secret=grant.secret,
        permissions=grant.permissions,
        cancel_event=cancel_event,
    )
    if isinstance(result, bool):
        return result
    if not isinstance(result, dict):
        return False
    try:
        transaction_id = result["transaction_id"]
        caller_node_id = result["caller_node_id"]
        identity_fingerprint = result["identity_fingerprint"]
        transport_fingerprint = result["transport_fingerprint"]
        secret = result["secret"]
        raw_permissions = result["permissions"]
        expires_at = result["expires_at"]
        if not isinstance(transaction_id, str) or not transaction_id:
            return False
        if not isinstance(caller_node_id, str):
            return False
        if not isinstance(identity_fingerprint, str):
            return False
        if not isinstance(transport_fingerprint, str):
            return False
        if not isinstance(secret, str):
            return False
        if not isinstance(raw_permissions, (list, tuple, set, frozenset)):
            return False
        permissions = frozenset(NodePermission(item) for item in raw_permissions)
        expires_at = float(expires_at)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False

    expected_caller = NodeId(grant.caller_node_id).value
    expected_identity = local.identity_fingerprint or ""
    expected_transport = controller.__dict__.get("_tls_fingerprint", "")
    bindings_match = (
        caller_node_id == expected_caller
        and identity_fingerprint == expected_identity
        and transport_fingerprint == expected_transport
        and secret == grant.secret
        and permissions == grant.permissions
    )
    if not bindings_match:
        return False

    transaction = PairingTransaction(
        transaction_id=transaction_id,
        caller_node_id=caller_node_id,
        identity_fingerprint=identity_fingerprint,
        transport_fingerprint=transport_fingerprint,
        secret=secret,
        permissions=permissions,
        expires_at=expires_at,
        transport=transport,
    )
    if not math.isfinite(expires_at) or expires_at <= time.time():
        # The pinned transport and every binding field are trusted only because
        # they exactly match the request; do not abort mismatched transactions.
        abort_target_pairing(transaction)
        return False
    return transaction


def confirm_target_pairing(
    transaction: PairingTransaction, *, cancel_event: threading.Event | None = None
) -> bool:
    return bool(
        AuthenticatedNodeProvider.confirm_pairing(
            transaction, cancel_event=cancel_event
        )
    )


def abort_target_pairing(transaction: PairingTransaction) -> bool:
    try:
        return AuthenticatedNodeProvider.abort_pairing(transaction)
    except Exception:  # noqa: BLE001 - rollback is explicitly best effort.
        return False


def _schedule_pairing_abort(controller: Any, transaction: PairingTransaction) -> None:
    controller._coordinator.run(
        f"pair-abort:{transaction.transaction_id}",
        lambda _cancel, _progress: abort_target_pairing(transaction),
        on_result=lambda _key, _result: None,
        on_error=lambda _key, _message: None,
    )


def _schedule_pairing_confirm(
    controller: Any,
    attempt: _PairingAttempt,
    dialog: Any,
    is_current: Callable[[], bool],
) -> None:
    transaction = attempt.transaction
    if transaction is None:
        return
    descriptor = attempt.descriptor
    if descriptor is None:
        return

    def on_result(_key: str, confirmed: bool) -> None:
        if not is_current():
            _schedule_pairing_abort(controller, transaction)
            return
        controller.__dict__.setdefault("_pairing_attempts", {}).pop(attempt.node, None)
        if confirmed:
            controller._refresh_nodes_page()
            controller._refresh_cluster_page()
            controller._rebuild_node_selector()
            controller._nodes_status(f"Paired {descriptor.display_name} (read-only)")
            controller._reconcile_peer_connections()
            if dialog is not None:
                dialog.complete()
            return
        restored = _restore_pairing(controller, attempt, persist=True)
        _schedule_pairing_abort(controller, transaction)
        if dialog is not None:
            dialog.show_error(
                "Pairing recovery failed: could not restore saved cluster state"
                if not restored
                else "Target pairing confirmation failed"
            )

    def on_error(_key: str, _message: str) -> None:
        on_result(_key, False)

    def _confirm_pairing(
        current_transaction: PairingTransaction, cancel_event: threading.Event
    ) -> bool:
        attempt.confirm_started = True
        return confirm_target_pairing(current_transaction, cancel_event=cancel_event)

    controller._coordinator.run(
        node_operation_key(attempt.node, "pair-confirm"),
        lambda cancel_event, _progress: _confirm_pairing(transaction, cancel_event),
        on_result=on_result,
        on_error=on_error,
    )


def reject_discovered_node(controller: Any, node_id: str) -> None:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    registry.reject_discovered(NodeId(node_id))
    ui_discovery_refresh.refresh_discovery_views(
        page=getattr(controller, "nodes_page", None),
        peer_specs=controller._nodes_peer_specs(),
        trusted_specs=(),
        refresh_trusted=False,
        refresh_cluster_page=controller._refresh_cluster_page,
        status_label=getattr(controller, "discovery_status_label", None),
        discovered_candidates=registry.discovered_candidates(),
    )
    controller._nodes_status(f"Rejected {node_id}")


def rename_node(
    controller: Any, node_id: str, *, simpledialog_module: Any = simpledialog
) -> None:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    current = registry.context(NodeId(node_id)).descriptor.display_name
    name = simpledialog_module.askstring(
        "Rename Node", "Display name:", initialvalue=current, parent=controller.master
    )
    if not name:
        return
    name = name.strip()
    if not name:
        return
    try:
        descriptor = registry.set_display_name(NodeId(node_id), name)
    except KeyError as error:
        controller._nodes_error(str(error))
        return
    records = [
        replace(record, display_name=name) if record.node_id == node_id else record
        for record in controller._cluster_state.trusted_nodes
    ]
    state = replace(controller._cluster_state, trusted_nodes=tuple(records))
    if not controller._save_cluster_state(state):
        registry.set_display_name(NodeId(node_id), current)
        controller._nodes_error("Cluster settings could not be saved")
        return
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    controller._rebuild_node_selector()
    controller._nodes_status(f"Renamed node to {descriptor.display_name}")


def set_node_permissions(
    controller: Any, node_id: str, raw_permissions: frozenset[str]
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
            updated = _role_state(controller).grant_capabilities(
                actor=controller._cluster_state.local_assignment,
                subject=subcoordinator.node_id or NodeId(""),
                target=NodeId(node_id),
                permissions=frozenset(
                    NodePermission(value)
                    for value in raw_permissions
                    if value in {permission.value for permission in NodePermission}
                ),
                now=time.time(),
                expires_at=time.time() + 3600.0,
            )
            _save_role_state(controller, updated)
        except (KeyError, TypeError, ValueError, RoleAuthorizationError) as error:
            controller._nodes_error(str(error))
        return
    process_permissions = {
        NodePermission.PROCESS_REVIEW,
        NodePermission.PROCESS_TERMINATION,
        NodePermission.PROCESS_FORCE_TERMINATION,
    }
    permissions = frozenset(
        permission for permission in previous if permission not in process_permissions
    ) | frozenset(
        NodePermission(value)
        for value in raw_permissions
        if value in allowed and NodePermission(value) in process_permissions
    )
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


def revoke_trusted_node(controller: Any, node_id: str) -> None:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    node = NodeId(node_id)
    try:
        previous_context = registry.context(node)
    except KeyError:
        if controller._cluster_state.record(node_id) is None:
            controller._nodes_status("Node is already revoked")
            return
        controller._nodes_error(f"Unknown node: {node}")
        return
    except ValueError as error:
        controller._nodes_error(str(error))
        return
    state = replace(
        controller._cluster_state,
        trusted_nodes=tuple(
            record
            for record in controller._cluster_state.trusted_nodes
            if record.node_id != node_id
        ),
        peer_grants=tuple(
            grant
            for grant in controller._cluster_state.peer_grants
            if grant.caller_node_id != node_id
        ),
    )
    if not controller._save_cluster_state(state):
        controller._nodes_error("Cluster settings could not be saved")
        return
    pairing_generations = controller.__dict__.setdefault("_pairing_generations", {})
    pairing_generations[node] = int(pairing_generations.get(node, 0)) + 1
    controller._coordinator.cancel(node_operation_key(node, "pair"))
    controller.__dict__.setdefault("_pairing_attempts", {}).pop(node, None)
    generations = controller.__dict__.setdefault("_activation_generations", {})
    generations[node] = int(generations.get(node, 0)) + 1
    controller._cancel_node_operations(previous_context)
    controller._cancel_peer_connection(previous_context)
    controller._coordinator.cancel(node_operation_key(node, "test_connection"))
    controller._coordinator.cancel(node_operation_key(node, "connect"))
    controller._invalidate_node_render_targets(node)
    invalidate = getattr(previous_context.provider, "invalidate", None)
    if callable(invalidate):
        invalidate()
    previous_context.provider = None
    previous_context.process_manager = None
    previous_context.scheduler = None
    previous_context.coordinator = None
    registry.revoke_trusted(node)
    getattr(controller, "_manual_host_ids", set()).discard(node_id)
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    controller._rebuild_node_selector()
    if controller.__dict__.get("_selected_node_id") != registry.selected_id():
        controller.__dict__["_selected_node_id"] = registry.selected_id()
        context = registry.selected_context()
        controller._sync_selected_context_mirrors(context)
        controller._render_selected_node(context)
    controller._nodes_status("Node removed from trusted machines")


def add_manual_host(
    controller: Any, display_name: str, host: str, port: int | None
) -> None:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    if port is not None and (
        not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535
    ):
        controller._nodes_error("Port must be between 0 and 65535")
        return
    node_id = f"manual-{host}:{port}" if port is not None else f"manual-{host}"
    node = NodeId(node_id)
    try:
        registry.context(node)
        controller._nodes_error("That manual host is already configured")
        return
    except KeyError:
        pass
    descriptor = NodeDescriptor(
        id=node,
        display_name=display_name,
        hostname=host,
        is_local=False,
        trust=NodeTrustState.TRUSTED,
        status=NodeStatus.UNKNOWN,
        capabilities=READ_CAPABILITIES,
        platform=None,
        color=None,
        permissions=READ_PERMISSIONS,
    )
    context = NodeContext(
        descriptor=descriptor,
        provider=None,
        process_manager=None,
        file_manager=None,
        scheduler=None,
        coordinator=None,
    )
    record = trusted_node_record(
        node_id=node_id,
        display_name=display_name,
        hostname=host,
        host=host,
        port=port,
        capabilities=READ_CAPABILITIES,
        permissions=READ_PERMISSIONS,
    )
    state = replace(
        controller._cluster_state,
        trusted_nodes=controller._cluster_state.trusted_nodes + (record,),
        peer_grants=tuple(
            grant
            for grant in controller._cluster_state.peer_grants
            if grant.caller_node_id != node_id
        ),
    )
    try:
        registry.register_context(context)
    except ValueError as error:
        controller._nodes_error(str(error))
        return
    if not controller._save_cluster_state(state):
        registry.revoke_trusted(node)
        controller._nodes_error("Cluster settings could not be saved")
        return
    manual_ids = getattr(controller, "_manual_host_ids", None)
    if manual_ids is None:
        manual_ids = set()
        controller._manual_host_ids = manual_ids
    manual_ids.add(node_id)
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    controller._nodes_status(f"Configured manual host {display_name}")


def remove_manual_host(
    controller: Any, node_id: str, *, messagebox_module: Any = messagebox
) -> None:
    if not messagebox_module.askyesno(
        "Remove manual host",
        "This deletes the manual host configuration and invalidates its trust "
        "and permissions. Add it again to reconnect.",
        parent=controller.master,
    ):
        return
    controller._revoke_trusted_node(node_id)


def test_connection(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    record = controller._cluster_state.record(node_id)
    if record is None:
        controller._nodes_error("No connection details saved for that node")
        return
    port = record.port
    if port is None:
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
        return provider.hello()

    def on_success(result: dict[str, Any]) -> None:
        if result.get("node_id") != node_id:
            messagebox_module.showerror(
                "Connection Failed",
                f"{record.display_name} answered as a different node.",
                parent=controller.master,
            )
            return
        if (
            record.identity_fingerprint is not None
            and result.get("identity_fingerprint") != record.identity_fingerprint
        ):
            messagebox_module.showerror(
                "Connection Failed",
                f"{record.display_name} presented a changed identity.",
                parent=controller.master,
            )
            return
        version = result.get("app_version") or "peer"
        messagebox_module.showinfo(
            "Connection OK",
            f"{record.display_name} answered an authenticated hello ({version}).",
            parent=controller.master,
        )

    def on_error(message: str) -> None:
        messagebox_module.showerror(
            "Connection Failed",
            f"Could not reach {record.display_name}: {message}",
            parent=controller.master,
        )

    key = node_operation_key(node, "test_connection")

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


def open_cluster_node(controller: Any, node_id: str) -> None:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    try:
        registry.context(NodeId(node_id))
    except KeyError:
        return
    node = NodeId(node_id)
    context = registry.context(node)
    if context.provider is None:
        controller._activate_remote_node(node)
        return
    controller._switch_selected_node(node)
    controller._show_dashboard_page()


def activate_remote_node(
    controller: Any,
    node_id: NodeId,
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
    backend_cls: Any = RemoteProcessActionBackend,
    scheduler_cls: Any = ComponentRefreshScheduler,
) -> None:
    """Authenticate and attach one remote context without blocking Tk."""

    registry = controller.__dict__.get("_node_registry")
    state = controller.__dict__.get("_cluster_state")
    if registry is None or state is None:
        return
    record = state.record(node_id.value)
    if record is None or record.port is None:
        controller._nodes_error("That trusted node has no authenticated remote port")
        return
    key = node_operation_key(node_id, "connect")
    generations = controller.__dict__.setdefault("_activation_generations", {})
    generation = int(generations.get(node_id, 0)) + 1
    generations[node_id] = generation

    def is_current() -> bool:
        if controller.__dict__.get("_is_closing", False):
            return False
        if generations.get(node_id) != generation:
            return False
        current_state = controller.__dict__.get("_cluster_state")
        if current_state is None or current_state.record(node_id.value) != record:
            return False
        try:
            current_context = registry.context(node_id)
        except KeyError:
            return False
        descriptor = current_context.descriptor
        return (
            is_trusted_descriptor(descriptor)
            and descriptor.identity_status is not NodeIdentityStatus.MISMATCH
            and (
                record.identity_fingerprint is None
                or descriptor.identity_fingerprint == record.identity_fingerprint
            )
        )

    def task(
        _cancel_event: threading.Event,
        _progress: Callable[[str], None],
    ) -> tuple[AuthenticatedNodeProvider, frozenset[NodeCapability], str]:
        provider = provider_cls(
            node_id=node_id,
            secret=record.secret,
            caller_node_id=NodeId(state.local_node_id),
            transport=build_trusted_transport(record, transport_cls=transport_cls),
        )
        result = provider.hello(cancel_event=_cancel_event)
        if result.get("node_id") != node_id.value:
            raise RuntimeError("authenticated peer returned the wrong node ID")
        expected_fingerprint = record.identity_fingerprint
        actual_fingerprint = result.get("identity_fingerprint")
        if not isinstance(actual_fingerprint, str) or not actual_fingerprint:
            raise RuntimeError("authenticated peer returned no identity fingerprint")
        if (
            expected_fingerprint is not None
            and actual_fingerprint != expected_fingerprint
        ):
            raise RuntimeError("authenticated peer identity fingerprint changed")
        capabilities = frozenset(
            NodeCapability(raw)
            for raw in result.get("capabilities", [])
            if isinstance(raw, str)
            and raw in {capability.value for capability in NodeCapability}
        )
        return provider, capabilities, actual_fingerprint

    def on_result(
        _key: str,
        result: tuple[AuthenticatedNodeProvider, frozenset[NodeCapability], str],
    ) -> None:
        provider, capabilities, fingerprint = result
        if not is_current():
            return
        try:
            context = registry.context(node_id)
        except KeyError:
            return
        if (
            context.descriptor.identity_fingerprint is not None
            and context.descriptor.identity_fingerprint != fingerprint
        ):
            return
        context.descriptor = replace(
            context.descriptor,
            capabilities=capabilities,
            status=NodeStatus.ONLINE,
            identity_status=NodeIdentityStatus.VERIFIED,
            permissions=record.permissions,
        )
        context.provider = provider
        context.process_manager = backend_cls(provider)
        context.scheduler = scheduler_cls()
        context.coordinator = controller._coordinator
        controller._refresh_nodes_page()
        controller._refresh_cluster_page()
        controller._rebuild_node_selector()
        controller._switch_selected_node(node_id)
        controller._show_dashboard_page()

    def on_error(_key: str, message: str) -> None:
        if not is_current():
            return
        controller._nodes_error(
            f"Could not authenticate {record.display_name}: {message}"
        )

    controller._coordinator.run(key, task, on_result=on_result, on_error=on_error)
