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

from maintenance.cluster import ClusterState, PeerGrantRecord, trusted_node_record
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
    RemoteProcessActionBackend,
    SocketRemoteTransport,
    TLSRemoteTransport,
)
from maintenance.ui import discovery_refresh as ui_discovery_refresh
from maintenance.ui.node_presentation import fingerprint_lines


def _pairing_confirmation(candidate: Any) -> str:
    """Keep the full identity values readable without changing their value."""

    fingerprint = candidate.identity_fingerprint or "Unavailable"
    fingerprint_text = "\n".join(fingerprint_lines(fingerprint))
    return (
        f"Pair {candidate.hostname}?\n\n"
        f"Stable node ID: {candidate.stable_id}\n\n"
        f"Identity fingerprint:\n{fingerprint_text}\n\n"
        f"TLS fingerprint: {candidate.transport_fingerprint or 'Unavailable'}\n\n"
        "Confirm this fingerprint through a trusted channel before pairing."
    )


def apply_discovery_enabled(controller: Any, enabled: bool) -> None:
    candidate = ClusterState(
        discovery_enabled=enabled,
        trusted_nodes=controller._cluster_state.trusted_nodes,
        local_node_id=controller._cluster_state.local_node_id,
        local_identity_persisted=controller._cluster_state.local_identity_persisted,
        peer_grants=controller._cluster_state.peer_grants,
    )
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


def pair_discovered_node(
    controller: Any,
    node_id: str,
    *,
    messagebox_module: Any = messagebox,
    provision_target_grant: Callable[[PeerGrantRecord], bool] | None = None,
) -> None:
    registry = controller.__dict__.get("_node_registry")
    if registry is None:
        return
    candidates = {
        candidate.stable_id: candidate for candidate in registry.discovered_candidates()
    }
    candidate = candidates.get(node_id)
    if candidate is None:
        controller._nodes_error("That peer is no longer visible on the network")
        return
    if not candidate.identity_fingerprint:
        controller._nodes_error("That peer did not provide an identity fingerprint")
        return
    try:
        registry.begin_pairing(NodeId(node_id))
    except (KeyError, ValueError) as error:
        controller._nodes_error(str(error))
        return
    if not messagebox_module.askyesno(
        "Confirm peer fingerprint",
        _pairing_confirmation(candidate),
        parent=controller.master,
    ):
        registry.fail_pairing(NodeId(node_id))
        controller._refresh_nodes_page()
        controller._nodes_status(f"Pairing cancelled for {candidate.hostname}")
        return
    node = NodeId(node_id)
    # The target must durably accept this grant before the initiator records
    # the peer as trusted.  There is intentionally no automatic trust path.
    provisioner = provision_target_grant or controller.__dict__.get(
        "_provision_target_grant"
    )
    if not callable(provisioner):
        if candidate.port is None or not candidate.transport_fingerprint:
            registry.fail_pairing(node)
            controller._refresh_nodes_page()
            controller._nodes_error(
                "Pairing requires explicit target-side grant provisioning"
            )
            return
        provisioner = lambda grant: request_target_grant(controller, candidate, grant)
    if not callable(provisioner):
        registry.fail_pairing(node)
        controller._refresh_nodes_page()
        controller._nodes_error(
            "Pairing requires explicit target-side grant provisioning"
        )
        return
    previous_context = None
    previous_selected = False
    try:
        previous_context = registry.context(node)
        previous_selected = registry.selected_id() == node
    except KeyError:
        pass
    try:
        descriptor = registry.promote_to_trusted(node, capabilities=READ_CAPABILITIES)
    except (KeyError, ValueError) as error:
        registry.fail_pairing(node)
        controller._refresh_nodes_page()
        controller._nodes_error(str(error))
        return
    descriptor = replace(descriptor, permissions=READ_PERMISSIONS)
    registry.context(node).descriptor = descriptor
    host = candidate.addresses[0] if candidate.addresses else candidate.hostname
    record = trusted_node_record(
        node_id=node_id,
        display_name=descriptor.display_name,
        hostname=descriptor.hostname,
        host=host,
        platform=descriptor.platform,
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
    try:
        provisioned = provisioner(grant)
    except Exception:  # noqa: BLE001 - provisioning failure is fail-closed.
        provisioned = False
    if not provisioned:
        registry.revoke_trusted(node)
        if previous_context is not None:
            registry.register_context(previous_context)
            registry.update_discovered(candidate)
            if previous_selected:
                registry.select(node)
        else:
            registry.update_discovered(candidate)
            registry.fail_pairing(node)
        controller._nodes_error("Target did not provision the peer grant")
        return
    existing_record = controller._cluster_state.record(node_id)
    trusted_nodes = tuple(
        record if item.node_id == node_id else item
        for item in controller._cluster_state.trusted_nodes
    )
    if existing_record is None:
        trusted_nodes = (*trusted_nodes, record)
    state = ClusterState(
        discovery_enabled=controller._cluster_state.discovery_enabled,
        trusted_nodes=trusted_nodes,
        local_node_id=controller._cluster_state.local_node_id,
        local_identity_persisted=controller._cluster_state.local_identity_persisted,
        peer_grants=controller._cluster_state.peer_grants,
    )
    if not controller._save_cluster_state(state):
        registry.revoke_trusted(node)
        if previous_context is not None:
            registry.register_context(previous_context)
            registry.update_discovered(candidate)
            if previous_selected:
                registry.select(node)
        else:
            registry.update_discovered(candidate)
            registry.fail_pairing(node)
        controller._nodes_error("Cluster settings could not be saved")
        return
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    controller._rebuild_node_selector()
    controller._nodes_status(f"Paired {descriptor.display_name} (read-only)")
    controller._reconcile_peer_connections()


def request_target_grant(
    controller: Any, candidate: Any, grant: PeerGrantRecord
) -> bool:
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
    return AuthenticatedNodeProvider.request_pairing(
        transport=transport,
        caller_node_id=NodeId(controller._cluster_state.local_node_id),
        identity_fingerprint=local.identity_fingerprint or "",
        transport_fingerprint=controller.__dict__.get("_tls_fingerprint", ""),
        proposed_secret=grant.secret,
        permissions=grant.permissions,
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
    state = ClusterState(
        discovery_enabled=controller._cluster_state.discovery_enabled,
        trusted_nodes=tuple(records),
        local_node_id=controller._cluster_state.local_node_id,
        local_identity_persisted=controller._cluster_state.local_identity_persisted,
        peer_grants=controller._cluster_state.peer_grants,
    )
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
    state = ClusterState(
        discovery_enabled=controller._cluster_state.discovery_enabled,
        trusted_nodes=tuple(records),
        local_node_id=controller._cluster_state.local_node_id,
        local_identity_persisted=controller._cluster_state.local_identity_persisted,
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
    state = ClusterState(
        discovery_enabled=controller._cluster_state.discovery_enabled,
        trusted_nodes=tuple(records),
        local_node_id=controller._cluster_state.local_node_id,
        local_identity_persisted=controller._cluster_state.local_identity_persisted,
        peer_grants=controller._cluster_state.peer_grants,
    )
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
        previous_selected = registry.selected_id() == node
        registry.revoke_trusted(node)
    except (KeyError, ValueError) as error:
        controller._nodes_error(str(error))
        return
    state = ClusterState(
        discovery_enabled=controller._cluster_state.discovery_enabled,
        trusted_nodes=tuple(
            record
            for record in controller._cluster_state.trusted_nodes
            if record.node_id != node_id
        ),
        local_node_id=controller._cluster_state.local_node_id,
        local_identity_persisted=controller._cluster_state.local_identity_persisted,
        peer_grants=tuple(
            grant
            for grant in controller._cluster_state.peer_grants
            if grant.caller_node_id != node_id
        ),
    )
    if not controller._save_cluster_state(state):
        registry.register_context(previous_context)
        if previous_selected:
            registry.select(node)
        controller._nodes_error("Cluster settings could not be saved")
        return
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
    state = ClusterState(
        discovery_enabled=controller._cluster_state.discovery_enabled,
        trusted_nodes=controller._cluster_state.trusted_nodes + (record,),
        local_node_id=controller._cluster_state.local_node_id,
        local_identity_persisted=controller._cluster_state.local_identity_persisted,
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


def remove_manual_host(controller: Any, node_id: str) -> None:
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
            transport=transport_cls(record.host, port),
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
            transport=transport_cls(record.host, record.port),
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
