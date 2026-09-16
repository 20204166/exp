"""Pairing lifecycle implementation for the window node-actions facade."""

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from maintenance.cluster import PeerGrantRecord, trusted_node_record
from maintenance.nodes import (
    READ_PERMISSIONS,
    NodeDescriptor,
    NodeId,
    NodePermission,
    node_operation_key,
)
from maintenance.remote import (
    READ_CAPABILITIES,
    AuthenticatedNodeProvider,
    PairingTransaction,
    TLSRemoteTransport,
)


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
    pairing_confirmation: Callable[[Any], str],
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
        pairing_confirmation(candidate),
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
    controller: Any,
    attempt: _PairingAttempt,
    provisioned: bool,
    *,
    role_state: Callable[[Any], Any],
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
    role_state_value = role_state(controller).clear_revocation(attempt.node)
    state = replace(
        controller._cluster_state,
        trusted_nodes=trusted_nodes,
        role_assignments=role_state_value.assignments,
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
    messagebox_module: Any,
    provision_target_grant: Callable[[PeerGrantRecord], bool] | None = None,
    pairing_confirmation: Callable[[Any], str],
    request_grant: Callable[..., PairingTransaction | bool],
    role_state: Callable[[Any], Any],
) -> None:
    attempt = _prepare_pairing(
        controller,
        node_id,
        messagebox_module=messagebox_module,
        pairing_confirmation=pairing_confirmation,
    )
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
            request_grant(controller, attempt.candidate, grant)
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
    _finish_pairing(controller, attempt, provisioned, role_state=role_state)


def pair_discovered_node_async(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any,
    provision_target_grant: Callable[[PeerGrantRecord], bool] | None = None,
    dialog: Any = None,
    pairing_confirmation: Callable[[Any], str],
    request_grant: Callable[..., PairingTransaction | bool],
    abort_grant: Callable[[PairingTransaction], bool],
    confirm_grant: Callable[..., bool],
    role_state: Callable[[Any], Any],
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
        pairing_confirmation=pairing_confirmation,
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
        provisioner = lambda grant, cancel_event: request_grant(
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
                _schedule_pairing_abort(controller, provisioned, abort_grant)
            return
        if network_flow and isinstance(provisioned, PairingTransaction):
            attempt.transaction = provisioned
            if not _finish_pairing(controller, attempt, True, role_state=role_state):
                attempts.pop(attempt.node, None)
                _schedule_pairing_abort(controller, provisioned, abort_grant)
                if dialog is not None:
                    dialog.show_error("Cluster settings could not be saved")
                return
            _schedule_pairing_confirm(
                controller,
                attempt,
                dialog,
                is_current,
                confirm_grant,
                abort_grant,
            )
            return
        attempts.pop(attempt.node, None)
        if _finish_pairing(controller, attempt, provisioned, role_state=role_state):
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
        _finish_pairing(controller, attempt, False, role_state=role_state)
        if dialog is not None:
            dialog.show_error("Target did not provision the peer grant")

    controller._coordinator.run(
        key,
        task,
        on_result=on_result,
        on_error=on_error,
    )


def cancel_pairing(
    controller: Any, node_id: str, *, abort_grant: Callable[[PairingTransaction], bool]
) -> None:
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
            _schedule_pairing_abort(controller, attempt.transaction, abort_grant)
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
    provider_cls: Any = AuthenticatedNodeProvider,
    abort_grant: Callable[[PairingTransaction], bool] | None = None,
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
    result = provider_cls.request_pairing(
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
        if abort_grant is None:
            abort_target_pairing(transaction, provider_cls=provider_cls)
        else:
            abort_grant(transaction)
        return False
    return transaction


def confirm_target_pairing(
    transaction: PairingTransaction,
    *,
    cancel_event: threading.Event | None = None,
    provider_cls: Any = AuthenticatedNodeProvider,
) -> bool:
    return bool(provider_cls.confirm_pairing(transaction, cancel_event=cancel_event))


def abort_target_pairing(
    transaction: PairingTransaction, *, provider_cls: Any = AuthenticatedNodeProvider
) -> bool:
    try:
        return provider_cls.abort_pairing(transaction)
    except Exception:  # noqa: BLE001 - rollback is explicitly best effort.
        return False


def _schedule_pairing_abort(
    controller: Any,
    transaction: PairingTransaction,
    abort_grant: Callable[[PairingTransaction], bool],
) -> None:
    controller._coordinator.run(
        f"pair-abort:{transaction.transaction_id}",
        lambda _cancel, _progress: abort_grant(transaction),
        on_result=lambda _key, _result: None,
        on_error=lambda _key, _message: None,
    )


def _schedule_pairing_confirm(
    controller: Any,
    attempt: _PairingAttempt,
    dialog: Any,
    is_current: Callable[[], bool],
    confirm_grant: Callable[..., bool],
    abort_grant: Callable[[PairingTransaction], bool],
) -> None:
    transaction = attempt.transaction
    if transaction is None:
        return
    descriptor = attempt.descriptor
    if descriptor is None:
        return

    def on_result(_key: str, confirmed: bool) -> None:
        if not is_current():
            _schedule_pairing_abort(controller, transaction, abort_grant)
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
        _schedule_pairing_abort(controller, transaction, abort_grant)
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
        return confirm_grant(current_transaction, cancel_event=cancel_event)

    controller._coordinator.run(
        node_operation_key(attempt.node, "pair-confirm"),
        lambda cancel_event, _progress: _confirm_pairing(transaction, cancel_event),
        on_result=on_result,
        on_error=on_error,
    )
