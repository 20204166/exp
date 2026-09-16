"""Trusted and manual node connection actions for the window facade."""

import threading
from collections.abc import Callable
from dataclasses import replace
from tkinter import messagebox
from typing import Any

from maintenance.cluster import trusted_node_record
from maintenance.components.coordinator import ComponentRefreshScheduler
from maintenance.nodes import (
    READ_PERMISSIONS,
    NodeCapability,
    NodeContext,
    NodeDescriptor,
    NodeId,
    NodeIdentityStatus,
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
    build_trusted_transport,
)


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
