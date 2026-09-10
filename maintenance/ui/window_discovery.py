"""Discovery and peer-reconciliation adapters for :class:`window.AppWindow`."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import replace
from typing import Any, cast

from maintenance.cluster import ClusterState, PeerGrantRecord
from maintenance.components import PeerConnectionManager
from maintenance.components.coordinator import ComponentRefreshScheduler
from maintenance.components.discovery_session import DiscoverySession
from maintenance.nodes import (
    NodeCapability,
    NodeContext,
    NodeId,
    NodeIdentityStatus,
    NodeStatus,
)
from maintenance.remote import (
    AuthenticatedNodeProvider,
    PairingRequest,
    PeerGrant,
    RemoteAuthError,
    TLSRemoteTransport,
)
from maintenance.remote_security import ensure_tls_material, server_context
from maintenance.ui import discovery_refresh as ui_discovery_refresh
from maintenance.ui import render_coordinator as ui_render
from maintenance.ui.window_supports.timer_delivery import deadline_delay_ms

LOGGER = logging.getLogger(__name__)


def _window_symbols() -> Any:
    # Keep the historical window-module patch seams for injected transports.
    import window

    return window


def get_discovery_session(controller: Any) -> DiscoverySession:
    session = controller.__dict__.get("_discovery_session")
    if session is None:
        window = _window_symbols()
        session = window.DiscoverySession(
            coordinator=controller._coordinator,
            registry=controller._node_registry,
            get_cluster_state=lambda: controller.__dict__.get("_cluster_state"),
            set_cluster_state=lambda state: setattr(
                controller, "_cluster_state", state
            ),
            save_cluster_state=controller._save_cluster_state,
            schedule_timer=controller._schedule_timer,
            cancel_timer=controller._cancel_timer,
            start_background_poll=controller._start_background_poll,
            on_candidate=controller._on_discovered_candidate,
            on_lost=controller._on_discovered_lost,
            on_stabilized=lambda: controller._queue_discovery_presentation(False),
            discovery_factory=window.NetworkDiscovery,
            app_version=window.__version__,
            is_closing=lambda: controller._is_closing,
            get_listener_endpoint=controller._listener_endpoint,
            on_presence_changed=controller._reconcile_peer_connections,
        )
        session.timer_id = controller.__dict__.get("_discovery_tick_id")
        controller._discovery_session = session
    return session


def listener_endpoint(controller: Any) -> tuple[bool, int | None, str | None]:
    server = controller.__dict__.get("_peer_server")
    if server is None or server.bound_port is None:
        return False, None, None
    return True, server.bound_port, controller.__dict__.get("_tls_fingerprint")


def start_peer_listener(controller: Any) -> None:
    """Start the TLS target listener, including before the first grant exists."""
    if controller.__dict__.get("_peer_server") is not None:
        return
    grants = {
        NodeId(grant.caller_node_id): PeerGrant(
            caller_node_id=NodeId(grant.caller_node_id),
            secret=grant.secret,
            permissions=grant.permissions,
        )
        for grant in controller._cluster_state.peer_grants
    }
    local_context = controller._node_registry.context(
        controller._node_registry.local_id() or NodeId("local")
    )
    descriptor = local_context.descriptor
    window = _window_symbols()
    service = window.RemoteService(
        node_id=descriptor.id,
        display_name=descriptor.display_name,
        hostname=descriptor.hostname,
        platform=descriptor.platform,
        status=descriptor.status,
        capabilities=descriptor.capabilities,
        provider=local_context.provider,
        process_manager=local_context.process_manager,
        secret=window.generate_node_secret(),
        app_version=window.__version__,
        grants=grants,
        identity_fingerprint=descriptor.identity_fingerprint,
    )
    try:
        material = ensure_tls_material(
            controller._cluster_store.path.parent, descriptor.id.value
        )
        tls_context = server_context(material)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        LOGGER.warning("Remote peer listener unavailable: %s", error)
        return
    server = window.RemoteSocketServer(
        service,
        host="0.0.0.0",
        ssl_context=tls_context,
        pairing_handler=lambda request: handle_pairing_request(controller, request),
    )
    try:
        server.start()
    except OSError as error:
        LOGGER.warning("Remote peer listener unavailable: %s", error)
        return
    controller._peer_server = server
    controller._tls_fingerprint = material.fingerprint


def handle_pairing_request(controller: Any, request: PairingRequest) -> bool:
    """Ask the target's local user before installing a caller grant."""

    result = {"approved": False}
    completed = threading.Event()

    def ask_on_ui() -> None:
        window = _window_symbols()
        approved = window.messagebox.askyesno(
            "Approve peer pairing",
            (
                f"Allow {request.caller_node_id.value} to read this system?\n\n"
                f"Identity fingerprint: {request.identity_fingerprint}\n"
                f"TLS fingerprint: {request.transport_fingerprint}"
            ),
            parent=controller.master,
        )
        if approved:
            current = controller._cluster_state
            grants = tuple(
                item
                for item in current.peer_grants
                if item.caller_node_id != request.caller_node_id.value
            ) + (
                PeerGrantRecord(
                    caller_node_id=request.caller_node_id.value,
                    secret=request.proposed_secret,
                    permissions=request.permissions,
                ),
            )
            result["approved"] = controller._save_cluster_state(
                ClusterState(
                    discovery_enabled=current.discovery_enabled,
                    trusted_nodes=current.trusted_nodes,
                    local_node_id=current.local_node_id,
                    local_identity_persisted=current.local_identity_persisted,
                    peer_grants=grants,
                )
            )
        completed.set()

    controller._submit_ui(ask_on_ui)
    completed.wait(60.0)
    return bool(result["approved"])


def start_discovery(controller: Any) -> None:
    """Advertise this node and browse for peers via the shared coordinator."""
    if controller.__dict__.get("_node_registry") is None:
        return
    if controller.__dict__.get("_coordinator") is None:
        return
    session = controller._get_discovery_session()
    result = session.start()
    controller._discovery_tick_id = session.timer_id
    if result.reason == "disabled":
        controller._nodes_status("Discovery disabled")
        return
    if result.started:
        controller._nodes_status("Discovery running - no peers found")
    else:
        if result.reason in {"identity persistence", "local node unavailable"}:
            return
        if result.available:
            controller._nodes_error(f"Discovery error: {result.reason}")
        else:
            controller._nodes_error(f"Discovery backend unavailable: {result.reason}")


def tick_discovery(controller: Any) -> None:
    session = controller._get_discovery_session()
    session.tick()
    controller._discovery_tick_id = session.timer_id


def peer_connections(controller: Any) -> PeerConnectionManager | None:
    manager = controller.__dict__.get("_peer_connection_manager")
    if manager is not None:
        return cast(PeerConnectionManager, manager)
    registry = controller.__dict__.get("_node_registry")
    coordinator = controller.__dict__.get("_coordinator")
    if registry is None or coordinator is None:
        return None
    manager = PeerConnectionManager(
        registry=registry,
        coordinator=coordinator,
        connect=lambda context, cancel_event, _progress: connect_peer(
            controller, context, cancel_event
        ),
        is_closing=lambda: controller._is_closing,
        can_connect=lambda context: can_connect_peer(controller, context),
        on_connected=lambda context, result: attach_peer(controller, context, result),
        on_failed=lambda context, _failure: detach_peer(controller, context),
    )
    controller.__dict__["_peer_connection_manager"] = manager
    return manager


def can_connect_peer(controller: Any, context: NodeContext) -> bool:
    record = controller._cluster_state.record(context.node_id.value)
    return bool(
        record is not None
        and record.port is not None
        and record.transport_fingerprint
        and context.descriptor.identity_status is not NodeIdentityStatus.MISMATCH
    )


def connect_peer(
    controller: Any, context: NodeContext, cancel_event: threading.Event
) -> tuple[AuthenticatedNodeProvider, frozenset[NodeCapability], str]:
    record = controller._cluster_state.record(context.node_id.value)
    if record is None or record.port is None or not record.transport_fingerprint:
        raise RuntimeError("trusted peer has no connectable TLS endpoint")
    provider = AuthenticatedNodeProvider(
        node_id=context.node_id,
        secret=record.secret,
        caller_node_id=NodeId(controller._cluster_state.local_node_id),
        transport=TLSRemoteTransport(
            record.host, record.port, expected_fingerprint=record.transport_fingerprint
        ),
    )
    hello = provider.hello(cancel_event=cancel_event)
    if hello.get("node_id") != context.node_id.value:
        raise RemoteAuthError("authenticated peer returned the wrong node ID")
    fingerprint = hello.get("identity_fingerprint")
    if not isinstance(fingerprint, str) or fingerprint != record.identity_fingerprint:
        raise RemoteAuthError("authenticated peer identity fingerprint changed")
    capabilities = frozenset(
        NodeCapability(raw)
        for raw in hello.get("capabilities", [])
        if isinstance(raw, str) and raw in {item.value for item in NodeCapability}
    )
    return provider, capabilities, fingerprint


def attach_peer(
    controller: Any,
    context: NodeContext,
    result: tuple[AuthenticatedNodeProvider, frozenset[NodeCapability], str],
) -> None:
    provider, capabilities, fingerprint = result
    if context.descriptor.identity_fingerprint not in (None, fingerprint):
        return
    context.provider = provider
    context.process_manager = _window_symbols().RemoteProcessActionBackend(provider)
    context.scheduler = ComponentRefreshScheduler()
    context.coordinator = controller._coordinator
    context.descriptor = replace(
        context.descriptor,
        capabilities=capabilities,
        status=NodeStatus.ONLINE,
        identity_status=NodeIdentityStatus.VERIFIED,
    )
    controller._refresh_nodes_page()
    controller._refresh_cluster_page()
    controller._rebuild_node_selector()


def detach_peer(controller: Any, context: NodeContext) -> None:
    if context.descriptor.is_local:
        return
    context.provider = None
    context.process_manager = None
    context.scheduler = None
    context.coordinator = None
    context.descriptor = replace(context.descriptor, status=NodeStatus.OFFLINE)
    controller._refresh_nodes_page()


def cancel_peer_connection(controller: Any, context: NodeContext) -> None:
    manager = controller._peer_connections()
    if manager is not None:
        manager.cancel(context.node_id)


def reconcile_peer_connections(controller: Any) -> None:
    manager = controller._peer_connections()
    if manager is None or controller._is_closing:
        return
    deadline = manager.reconcile()
    controller._schedule_peer_reconciliation(deadline)


def schedule_peer_reconciliation(controller: Any, deadline: float | None) -> None:
    controller._cancel_timer(controller.__dict__.get("_peer_reconcile_timer_id"))
    controller.__dict__["_peer_reconcile_timer_id"] = None
    if deadline is None or controller._is_closing:
        return
    delay = deadline_delay_ms(deadline, time.monotonic())
    controller.__dict__["_peer_reconcile_timer_id"] = controller._schedule_timer(
        delay, controller._run_peer_reconciliation
    )


def run_peer_reconciliation(controller: Any) -> None:
    controller.__dict__["_peer_reconcile_timer_id"] = None
    controller._reconcile_peer_connections()


def on_discovered_candidate(controller: Any, candidate: Any) -> None:
    if controller._is_closing:
        return
    registry = controller.__dict__.get("_node_registry")
    trusted_descriptor = None
    trusted_updated = False
    if registry is not None:
        registry.update_discovered(candidate)
        if controller._selected_node_id != registry.selected_id():
            controller._switch_selected_node(registry.selected_id())
        try:
            context = registry.context(NodeId(candidate.stable_id))
        except KeyError:
            context = None
        if context is not None and _window_symbols().is_trusted_descriptor(
            context.descriptor
        ):
            trusted_descriptor = context.descriptor
        trusted_updated = controller._sync_trusted_node_endpoint(candidate)
        if trusted_descriptor is not None:
            controller.__dict__["_discovery_trusted_refresh_pending"] = True
        count = len(registry.discovered_candidates())
        controller._nodes_status(
            f"Discovery running - {count} peer{'s' if count != 1 else ''} found"
        )
        if trusted_updated:
            try:
                descriptor = registry.context(NodeId(candidate.stable_id)).descriptor
            except KeyError:
                descriptor = None
            if descriptor is not None:
                controller._nodes_status(
                    f"Verified {descriptor.display_name} at a new address"
                )


def on_discovered_lost(controller: Any, stable_id: str) -> None:
    if controller._is_closing:
        return
    registry = controller.__dict__.get("_node_registry")
    trusted_descriptor = None
    if registry is not None:
        manager = controller._peer_connections()
        if manager is not None:
            manager.mark_disconnected(NodeId(stable_id))
        registry.remove_discovered(NodeId(stable_id))
        try:
            context = registry.context(NodeId(stable_id))
        except KeyError:
            context = None
        if context is not None and _window_symbols().is_trusted_descriptor(
            context.descriptor
        ):
            trusted_descriptor = context.descriptor
    if trusted_descriptor is not None:
        controller.__dict__["_discovery_trusted_refresh_pending"] = True
    count = len(registry.discovered_candidates()) if registry is not None else 0
    controller._nodes_status(
        f"Discovery running - {count} peers found"
        if count != 1
        else "Discovery running - 1 peer found"
    )


def queue_discovery_presentation(controller: Any, trusted_involved: bool) -> None:
    """Keep discovery mutations immediate while batching their rendering."""
    if trusted_involved:
        controller.__dict__["_discovery_trusted_refresh_pending"] = True
    coordinator = controller.__dict__.get("_coordinator")
    registry = controller.__dict__.get("_node_registry")
    if coordinator is None or registry is None:
        return
    ui_discovery_refresh.post_discovery_refresh(
        coordinator=coordinator,
        key="discovery-pages",
        page=getattr(controller, "nodes_page", None),
        get_peer_specs=controller._nodes_peer_specs,
        get_trusted_specs=controller._nodes_trusted_specs,
        should_refresh_trusted=lambda: bool(
            controller.__dict__.pop("_discovery_trusted_refresh_pending", False)
        ),
        refresh_cluster_page=controller._refresh_cluster_page,
        status_label=getattr(controller, "discovery_status_label", None),
        get_discovered_candidates=registry.discovered_candidates,
        visible=bool(controller.__dict__.get("_discovery_pages_visible", False)),
        is_active=lambda: not controller._is_closing,
    )


def sync_trusted_node_endpoint(controller: Any, candidate: Any) -> bool:
    registry = controller.__dict__.get("_node_registry")
    state = controller.__dict__.get("_cluster_state")
    if registry is None or state is None:
        return False
    try:
        context = registry.context(NodeId(candidate.stable_id))
    except (AttributeError, KeyError):
        return False
    descriptor = context.descriptor
    if descriptor.is_local or not _window_symbols().is_trusted_descriptor(descriptor):
        return False
    record = state.record(descriptor.id.value)
    if record is None:
        return False
    if (
        record.identity_fingerprint is not None
        and candidate.identity_fingerprint != record.identity_fingerprint
    ):
        context.descriptor = replace(
            descriptor,
            identity_fingerprint=record.identity_fingerprint,
            identity_status=NodeIdentityStatus.MISMATCH,
        )
        controller._nodes_error(
            f"Identity mismatch for {descriptor.display_name}; re-pair required"
        )
        return False
    needs_identity_hydration = (
        record.identity_fingerprint is None
        and candidate.identity_fingerprint is not None
        and candidate.identity_fingerprint
        == _window_symbols().node_identity_fingerprint(descriptor.id)
    )
    needs_identity_recovery = (
        descriptor.identity_status is NodeIdentityStatus.MISMATCH
        and record.identity_fingerprint is not None
        and candidate.identity_fingerprint == record.identity_fingerprint
    )
    address = candidate.addresses[0] if candidate.addresses else record.host
    port = candidate.port if candidate.port is not None else record.port
    transport_changed = candidate.transport_fingerprint != record.transport_fingerprint
    endpoint_changed = (
        address != record.host or port != record.port or transport_changed
    )
    if not endpoint_changed and not (
        needs_identity_hydration or needs_identity_recovery
    ):
        return False
    if port is None:
        return False
    window = _window_symbols()
    try:
        provider = window.AuthenticatedNodeProvider(
            node_id=descriptor.id,
            secret=record.secret,
            caller_node_id=NodeId(controller._cluster_state.local_node_id),
            transport=(
                window.TLSRemoteTransport(
                    address,
                    port,
                    expected_fingerprint=candidate.transport_fingerprint,
                )
                if candidate.transport_fingerprint
                else window.SocketRemoteTransport(address, port)
            ),
        )
        hello = provider.hello()
        if not isinstance(hello, dict):
            raise TypeError("authenticated peer returned invalid hello metadata")
        if hello.get("node_id") != descriptor.id.value:
            raise RuntimeError("authenticated peer returned the wrong node ID")
        actual_fingerprint = hello.get("identity_fingerprint")
        if not isinstance(actual_fingerprint, str) or not actual_fingerprint:
            raise RuntimeError("authenticated peer returned no identity fingerprint")
        if record.identity_fingerprint is not None and actual_fingerprint != (
            record.identity_fingerprint
        ):
            raise RuntimeError("authenticated peer identity fingerprint changed")
    except Exception as error:  # noqa: BLE001 - failed verification means no update.
        LOGGER.info(
            "Trusted node %s could not be verified at %s:%s: %s",
            descriptor.id,
            address,
            port,
            error,
        )
        return False
    display_name = record.display_name
    if display_name == record.hostname:
        display_name = descriptor.display_name
    updated_record = replace(
        record,
        display_name=display_name,
        hostname=descriptor.hostname,
        host=address,
        port=port,
        platform=descriptor.platform,
        identity_fingerprint=(
            candidate.identity_fingerprint
            if needs_identity_hydration
            else record.identity_fingerprint
        ),
        transport_fingerprint=(
            candidate.transport_fingerprint or record.transport_fingerprint
        ),
    )
    if updated_record == record:
        if needs_identity_recovery:
            registry.confirm_identity(descriptor.id, candidate.identity_fingerprint)
            return True
        return False
    updated_records = tuple(
        updated_record if item.node_id == record.node_id else item
        for item in state.trusted_nodes
    )
    updated_state = ClusterState(
        discovery_enabled=state.discovery_enabled,
        trusted_nodes=updated_records,
        local_node_id=state.local_node_id,
        local_identity_persisted=state.local_identity_persisted,
        peer_grants=state.peer_grants,
    )
    if not controller._save_cluster_state(updated_state):
        controller._nodes_error("Cluster settings could not be saved")
        return False
    if needs_identity_hydration or needs_identity_recovery:
        registry.confirm_identity(descriptor.id, candidate.identity_fingerprint)
    return True


def refresh_discovery_status(controller: Any) -> None:
    """Render untrusted peer presence without offering any interaction."""
    label = getattr(controller, "discovery_status_label", None)
    if label is None:
        return
    controller._request_render(
        ui_render.RenderIntent(
            target="dashboard-discovery",
            components=frozenset({"discovery"}),
            layout_changed=True,
            payload=controller._node_registry.discovered_candidates(),
            payload_set=True,
            priority=1,
        ),
        lambda _intent: ui_discovery_refresh.render_discovery_status(
            label, controller._node_registry.discovered_candidates()
        ),
    )


def stop_discovery(controller: Any) -> None:
    if "_node_registry" not in controller.__dict__:
        controller._cancel_timer(controller.__dict__.get("_discovery_tick_id"))
        controller._discovery_tick_id = None
        return
    if controller.__dict__.get("_coordinator") is None:
        controller._cancel_timer(controller.__dict__.get("_discovery_tick_id"))
        controller._discovery_tick_id = None
        return
    session = controller._get_discovery_session()
    session.stop()
    controller._discovery_tick_id = session.timer_id
