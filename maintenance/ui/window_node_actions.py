"""Node administration actions used by the window controller.

The functions in this module deliberately keep the controller as an explicit
dependency.  This preserves the controller's dynamic callback seams while
keeping node administration out of the window's composition code.
"""

import threading
from collections.abc import Callable
from dataclasses import replace
from tkinter import messagebox, simpledialog
from typing import Any

from maintenance.cluster import (
    PeerGrantRecord,
)
from maintenance.components.coordinator import ComponentRefreshScheduler
from maintenance.nodes import (
    NodeId,
    node_operation_key,
)
from maintenance.remote import (
    AuthenticatedNodeProvider,
    PairingTransaction,
    RemoteProcessActionBackend,
    SocketRemoteTransport,
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


_ROLE_LOCAL = "local_only"
_ROLE_REMOTE = "remote"
_ROLE_FAIL = "fail"


def remove_connection_node(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
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
    # remove_connection is a local action: the local disconnect above always
    # proceeds.  The RPC is a best-effort notification — fire-and-forget with
    # silent failure — so we attempt it only when the cluster path is fully
    # reachable; otherwise we accept the asymmetric disconnect gracefully.
    dispatch, _reason = _classify_role_dispatch(controller, node_id)
    if dispatch == _ROLE_REMOTE:
        epoch = controller._cluster_state.coordinator_epoch
        record = controller._cluster_state.record(node_id)
        if record is not None and record.port is not None:
            _node = node

            def task(
                _cancel: threading.Event,
                _progress: Callable[[str], None],
            ) -> Any:
                provider = provider_cls(
                    node_id=_node,
                    secret=record.secret,
                    caller_node_id=NodeId(controller._cluster_state.local_node_id),
                    transport=build_trusted_transport(
                        record, transport_cls=transport_cls
                    ),
                )
                return provider.remove_connection(
                    node_id,
                    cluster_id=controller._cluster_state.cluster_id,
                    epoch=epoch.epoch,
                    fencing_token=epoch.fencing_token,
                )

            controller._coordinator.run(
                node_operation_key(node, "remove_connection"),
                task,
                on_result=lambda _key, _result: None,
                on_error=lambda _key, _message: None,
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
    return _permissions_impl.set_node_permissions(
        controller,
        node_id,
        raw_permissions,
        role_state_fn=_role_state,
        save_role_state_fn=_save_role_state,
    )


def set_node_color(controller: Any, node_id: str, color: str) -> None:
    return _permissions_impl.set_node_color(controller, node_id, color)


def revoke_trusted_node(controller: Any, node_id: str) -> None:
    return _connections_impl.revoke_trusted_node(controller, node_id)


def attempt_pending_trust_revocations(controller: Any, node_id: str) -> None:
    return _connections_impl.attempt_pending_trust_revocations(controller, node_id)


def remove_manual_host(
    controller: Any, node_id: str, *, messagebox_module: Any = messagebox
) -> None:
    return _connections_impl.remove_manual_host(
        controller,
        node_id,
        messagebox_module=_current_connection_dependency(
            messagebox_module, _CONNECTION_DEFAULT_MESSAGEBOX, messagebox
        ),
    )


def add_manual_host(
    controller: Any, display_name: str, host: str, port: int | None
) -> None:
    return _connections_impl.add_manual_host(controller, display_name, host, port)


def test_connection(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    return _connections_impl.test_connection(
        controller,
        node_id,
        messagebox_module=_current_connection_dependency(
            messagebox_module, _CONNECTION_DEFAULT_MESSAGEBOX, messagebox
        ),
        provider_cls=_current_connection_dependency(
            provider_cls, _CONNECTION_DEFAULT_PROVIDER, AuthenticatedNodeProvider
        ),
        transport_cls=_current_connection_dependency(
            transport_cls, _CONNECTION_DEFAULT_TRANSPORT, SocketRemoteTransport
        ),
    )


def open_cluster_node(controller: Any, node_id: str) -> None:
    return _connections_impl.open_cluster_node(controller, node_id)


def activate_remote_node(
    controller: Any,
    node_id: NodeId,
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
    backend_cls: Any = RemoteProcessActionBackend,
    scheduler_cls: Any = ComponentRefreshScheduler,
) -> None:
    return _connections_impl.activate_remote_node(
        controller,
        node_id,
        provider_cls=_current_connection_dependency(
            provider_cls, _CONNECTION_DEFAULT_PROVIDER, AuthenticatedNodeProvider
        ),
        transport_cls=_current_connection_dependency(
            transport_cls, _CONNECTION_DEFAULT_TRANSPORT, SocketRemoteTransport
        ),
        backend_cls=_current_connection_dependency(
            backend_cls, _CONNECTION_DEFAULT_BACKEND, RemoteProcessActionBackend
        ),
        scheduler_cls=_current_connection_dependency(
            scheduler_cls, _CONNECTION_DEFAULT_SCHEDULER, ComponentRefreshScheduler
        ),
    )


# Keep the historical facade names while resolving provider and transport
# collaborators from this module at invocation time.
_ROLE_DEFAULT_PROVIDER = AuthenticatedNodeProvider
_ROLE_DEFAULT_TRANSPORT = SocketRemoteTransport
_CONNECTION_DEFAULT_MESSAGEBOX = messagebox
_CONNECTION_DEFAULT_PROVIDER = AuthenticatedNodeProvider
_CONNECTION_DEFAULT_TRANSPORT = SocketRemoteTransport
_CONNECTION_DEFAULT_BACKEND = RemoteProcessActionBackend
_CONNECTION_DEFAULT_SCHEDULER = ComponentRefreshScheduler


def _current_connection_dependency(value: Any, original: Any, current: Any) -> Any:
    return current if value is original else value


from maintenance.ui.window_node_actions_impl import connections as _connections_impl
from maintenance.ui.window_node_actions_impl import pairing as _pairing_impl
from maintenance.ui.window_node_actions_impl import permissions as _permissions_impl
from maintenance.ui.window_node_actions_impl import roles as _role_impl

_role_state = _role_impl._role_state
_save_role_state = _role_impl._save_role_state
_propagate_capability_grants = _role_impl._propagate_capability_grants
_classify_role_dispatch = _role_impl._classify_role_dispatch
_remote_role_op = _role_impl._remote_role_op


_PairingAttempt = _pairing_impl._PairingAttempt


def pair_discovered_node(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provision_target_grant: Callable[[PeerGrantRecord], bool] | None = None,
) -> None:
    return _pairing_impl.pair_discovered_node(
        controller,
        node_id,
        messagebox_module=messagebox_module,
        provision_target_grant=provision_target_grant,
        pairing_confirmation=_pairing_confirmation,
        request_grant=request_target_grant,
        role_state=_role_state,
    )


def pair_discovered_node_async(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provision_target_grant: Callable[[PeerGrantRecord], bool] | None = None,
    dialog: Any = None,
) -> None:
    return _pairing_impl.pair_discovered_node_async(
        controller,
        node_id,
        messagebox_module=messagebox_module,
        provision_target_grant=provision_target_grant,
        dialog=dialog,
        pairing_confirmation=_pairing_confirmation,
        request_grant=request_target_grant,
        abort_grant=abort_target_pairing,
        confirm_grant=confirm_target_pairing,
        role_state=_role_state,
    )


def cancel_pairing(controller: Any, node_id: str) -> None:
    return _pairing_impl.cancel_pairing(
        controller, node_id, abort_grant=abort_target_pairing
    )


def request_target_grant(
    controller: Any,
    candidate: Any,
    grant: PeerGrantRecord,
    *,
    cancel_event: threading.Event | None = None,
) -> PairingTransaction | bool:
    return _pairing_impl.request_target_grant(
        controller,
        candidate,
        grant,
        cancel_event=cancel_event,
        provider_cls=AuthenticatedNodeProvider,
        abort_grant=abort_target_pairing,
    )


def confirm_target_pairing(
    transaction: PairingTransaction, *, cancel_event: threading.Event | None = None
) -> bool:
    return _pairing_impl.confirm_target_pairing(
        transaction,
        cancel_event=cancel_event,
        provider_cls=AuthenticatedNodeProvider,
    )


def abort_target_pairing(transaction: PairingTransaction) -> bool:
    return _pairing_impl.abort_target_pairing(
        transaction, provider_cls=AuthenticatedNodeProvider
    )


_restore_pairing = _pairing_impl._restore_pairing
_prepare_pairing = _pairing_impl._prepare_pairing
_finish_pairing = _pairing_impl._finish_pairing


def _schedule_pairing_abort(controller: Any, transaction: PairingTransaction) -> None:
    return _pairing_impl._schedule_pairing_abort(
        controller, transaction, abort_target_pairing
    )


def _schedule_pairing_confirm(
    controller: Any,
    attempt: _PairingAttempt,
    dialog: Any,
    is_current: Callable[[], bool],
) -> None:
    return _pairing_impl._schedule_pairing_confirm(
        controller,
        attempt,
        dialog,
        is_current,
        confirm_target_pairing,
        abort_target_pairing,
    )


def _current_role_dependency(value: Any, original: Any, current: Any) -> Any:
    return current if value is original else value


def set_node_roles(
    controller: Any,
    node_id: str,
    roles: frozenset[str],
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    return _role_impl.set_node_roles(
        controller,
        node_id,
        roles,
        provider_cls=_current_role_dependency(
            provider_cls, _ROLE_DEFAULT_PROVIDER, AuthenticatedNodeProvider
        ),
        transport_cls=_current_role_dependency(
            transport_cls, _ROLE_DEFAULT_TRANSPORT, SocketRemoteTransport
        ),
    )


def pause_node(
    controller: Any,
    node_id: str,
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    return _role_impl.pause_node(
        controller,
        node_id,
        provider_cls=_current_role_dependency(
            provider_cls, _ROLE_DEFAULT_PROVIDER, AuthenticatedNodeProvider
        ),
        transport_cls=_current_role_dependency(
            transport_cls, _ROLE_DEFAULT_TRANSPORT, SocketRemoteTransport
        ),
    )


def resume_node(
    controller: Any,
    node_id: str,
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    return _role_impl.resume_node(
        controller,
        node_id,
        provider_cls=_current_role_dependency(
            provider_cls, _ROLE_DEFAULT_PROVIDER, AuthenticatedNodeProvider
        ),
        transport_cls=_current_role_dependency(
            transport_cls, _ROLE_DEFAULT_TRANSPORT, SocketRemoteTransport
        ),
    )


def remove_job_node(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    return _role_impl.remove_job_node(
        controller,
        node_id,
        messagebox_module=messagebox_module,
        provider_cls=_current_role_dependency(
            provider_cls, _ROLE_DEFAULT_PROVIDER, AuthenticatedNodeProvider
        ),
        transport_cls=_current_role_dependency(
            transport_cls, _ROLE_DEFAULT_TRANSPORT, SocketRemoteTransport
        ),
    )


def revoke_node(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    return _role_impl.revoke_node(
        controller,
        node_id,
        messagebox_module=messagebox_module,
        provider_cls=_current_role_dependency(
            provider_cls, _ROLE_DEFAULT_PROVIDER, AuthenticatedNodeProvider
        ),
        transport_cls=_current_role_dependency(
            transport_cls, _ROLE_DEFAULT_TRANSPORT, SocketRemoteTransport
        ),
        revoke_trusted_node_fn=revoke_trusted_node,
    )


def create_cluster_invite(controller: Any) -> str | None:
    return _role_impl.create_cluster_invite(controller)


def join_cluster_via_invite(
    controller: Any,
    node_id: str,
    blob: str,
    *,
    provider_cls: Any = AuthenticatedNodeProvider,
    transport_cls: Any = SocketRemoteTransport,
) -> None:
    return _role_impl.join_cluster_via_invite(
        controller,
        node_id,
        blob,
        provider_cls=_current_role_dependency(
            provider_cls, _ROLE_DEFAULT_PROVIDER, AuthenticatedNodeProvider
        ),
        transport_cls=_current_role_dependency(
            transport_cls, _ROLE_DEFAULT_TRANSPORT, SocketRemoteTransport
        ),
    )


_apply_cluster_join = _role_impl._apply_cluster_join
