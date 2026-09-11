"""Discovery and peer-reconciliation adapters for :class:`window.AppWindow`."""

from __future__ import annotations

import logging
import json
import subprocess
import threading
import time
from dataclasses import replace
from typing import Any, cast

from maintenance.cluster import PeerGrantRecord
from maintenance.components import PeerConnectionManager
from maintenance.components.cluster_storage import (
    ResourceSnapshot,
    SnapshotBatch,
    snapshot_batch_to_dict,
)
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
    RemoteUnavailableError,
    RemoteRequest,
    build_trusted_transport,
)
from maintenance.remote_security import ensure_tls_material, server_context
from maintenance.ui import discovery_refresh as ui_discovery_refresh
from maintenance.ui import render_coordinator as ui_render

JOB_UPLOAD_DIVISOR = 5


def should_upload_job(sequence: int, has_active_job: bool) -> bool:
    """Deterministic 20% participation: idle workers upload 1 in 5 ticks."""
    if has_active_job:
        return True
    return sequence % JOB_UPLOAD_DIVISOR == 0
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
        cluster_id=controller._cluster_state.cluster_id,
        coordinator_epoch=(
            controller._cluster_state.coordinator_epoch.epoch
            if controller._cluster_state.coordinator_epoch is not None
            else None
        ),
        fencing_token=(
            controller._cluster_state.coordinator_epoch.fencing_token
            if controller._cluster_state.coordinator_epoch is not None
            else None
        ),
        role_handler=lambda request: handle_role_request(controller, request),
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


def handle_role_request(controller: Any, request: RemoteRequest) -> dict[str, Any]:
    """Apply only the typed role operations accepted by the local target."""

    from maintenance.components.cluster_roles import ClusterRole, RoleState, hash_invite

    state = controller._cluster_state
    if request.op == "consume_invite":
        invite = next(
            (
                item
                for item in state.active_invites
                if item.token_hash == hash_invite(request.params["token"])
            ),
            None,
        )
        if invite is None:
            raise RemoteAuthError("pairing invite is unknown or expired")
        if invite.target_node_id and invite.target_node_id != (
            request.caller_node_id or NodeId("")
        ).value:
            raise RemoteAuthError("pairing invite is bound to another node")
        invite = state.consume_invite(request.params["token"], now=time.time())
        if not controller._save_cluster_state(state):
            state.active_invites = (*state.active_invites, invite)
            raise RemoteAuthError("pairing invite could not be consumed")
        return {"target_node_id": invite.target_node_id, "expires_at": invite.expires_at}
    if request.op == "renew_coordinator_lease":
        manager = controller.__dict__.get("_peer_connection_manager")
        if manager is None:
            manager = peer_connections(controller)
        if manager is None:
            raise RemoteUnavailableError("peer lifecycle is unavailable")
        manager.renew_cluster_lease(
            state,
            coordinator_id=request.caller_node_id or NodeId(""),
            fencing_token=request.params["fencing_token"],
            now=time.time(),
        )
        update_listener_fence(controller, state)
        return {"ok": True, "epoch": request.params["epoch"]}
    if request.op in {"worker_snapshot", "standby_batch"}:
        from maintenance.components.cluster_storage import snapshot_batch_from_dict

        batch = snapshot_batch_from_dict(request.params["payload"])
        if batch.cluster_id not in ("", state.cluster_id):
            raise RemoteAuthError("snapshot cluster identity is invalid")
        caller = request.caller_node_id
        assignment = next(
            (
                item
                for item in state.role_assignments
                if item.node_id == caller
            ),
        )
        if assignment is None or assignment.paused or assignment.revoked:
            raise RemoteAuthError("snapshot sender is not active")
        expected_role = (
            ClusterRole.COORDINATOR
            if request.op == "standby_batch"
            else ClusterRole.WORKER
        )
        if expected_role not in assignment.roles:
            raise RemoteAuthError("snapshot sender has no required role")
        if batch.source_node_id != caller:
            raise RemoteAuthError("snapshot source does not match authenticated caller")
        storage = controller.__dict__.get(
            "_standby_buffer" if request.op == "standby_batch" else "_cluster_timeline"
        )
        if storage is None:
            raise RemoteUnavailableError("cluster storage is unavailable")
        accepted = storage.import_batch(
            batch,
            cluster_id=state.cluster_id,
            expected_source_node_id=caller,
            expected_epoch=request.params["epoch"],
            now=time.time(),
        )
        return {"accepted": accepted, "sequence": batch.sequence}
    actor_id = request.caller_node_id
    if actor_id is None:
        raise RemoteAuthError("role operation has no caller identity")
    actor = next(
        (
            item
            for item in state.role_assignments
            if item.node_id == actor_id
        ),
        None,
    )
    if actor is None:
        raise RemoteAuthError("role caller is not enrolled")
    role_state = RoleState(state.role_assignments, state.coordinator_epoch)
    if request.op == "assign_role":
        if state.record(request.params["target_node_id"]) is None and not any(
            item.node_id == NodeId(request.params["target_node_id"])
            for item in state.role_assignments
        ):
            raise RemoteAuthError("role target is not enrolled")
        updated, _change = role_state.assign(
            actor=actor,
            target=NodeId(request.params["target_node_id"]),
            roles=frozenset(ClusterRole(value) for value in request.params["roles"]),
            now=time.time(),
        )
    elif request.op == "pause_worker":
        updated = role_state.pause(
            actor=actor, target=NodeId(request.params["target_node_id"])
        )
    elif request.op == "resume_worker":
        updated = role_state.resume(
            actor=actor, target=NodeId(request.params["target_node_id"])
        )
    elif request.op == "revoke_worker":
        updated = role_state.revoke(
            actor=actor, target=NodeId(request.params["target_node_id"])
        )
    elif request.op == "remove_connection":
        if request.params.get("target_node_id") != actor_id.value:
            raise RemoteAuthError(
                "remove_connection is limited to the caller relationship"
            )
        manager = controller.__dict__.get("_peer_connection_manager")
        if manager is None:
            manager = peer_connections(controller)
        if manager is not None:
            manager.disconnect_manual(actor_id)
        return {"ok": True}
    elif request.op == "remove_job":
        updated = role_state.remove_job(
            actor=actor, target=NodeId(request.params["target_node_id"])
        )
    else:
        raise RemoteAuthError("unknown role operation")
    if not controller._save_cluster_state(replace(state, role_assignments=updated.assignments)):
        raise RemoteAuthError("role state could not be saved")
    return {"ok": True}


def handle_pairing_request(controller: Any, request: PairingRequest) -> bool:
    """Ask the target's local user before installing a caller grant."""

    pairing_lock = controller.__dict__.setdefault("_pairing_lock", threading.Lock())
    if not pairing_lock.acquire(blocking=False):
        return False
    result = {"approved": False}
    completed = threading.Event()

    def ask_on_ui() -> None:
        window = _window_symbols()
        approved = window.messagebox.askyesno(
            "Approve peer pairing",
            (
                f"Allow {request.caller_node_id.value} to read this system?\n\n"
                f"Identity fingerprint: {request.identity_fingerprint}\n"
                f"TLS fingerprint: {request.transport_fingerprint}\n"
                f"Requested permissions: {', '.join(sorted(p.value for p in request.permissions))}"
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
                replace(current, peer_grants=grants)
            )
        completed.set()

    try:
        controller._submit_ui(ask_on_ui)
        completed.wait(60.0)
        return bool(result["approved"])
    finally:
        pairing_lock.release()


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
        cluster_store=getattr(controller, "_cluster_store", None),
        timeline=getattr(controller, "_cluster_timeline", None),
        standby=getattr(controller, "_standby_buffer", None),
        on_promoted=lambda state, decision: handle_promotion(controller, state, decision),
    )
    controller.__dict__["_peer_connection_manager"] = manager
    return manager


def update_listener_fence(controller: Any, state: Any) -> None:
    server = controller.__dict__.get("_peer_server")
    epoch = state.coordinator_epoch
    if server is not None and epoch is not None:
        server.update_cluster_fence(
            cluster_id=state.cluster_id,
            coordinator_epoch=epoch.epoch,
            fencing_token=epoch.fencing_token,
        )


def handle_promotion(controller: Any, state: Any, decision: Any) -> None:
    """Activate Coordinator storage and import the prior standby epoch."""

    from maintenance.components.cluster_storage import CoordinatorTimeline

    if controller.__dict__.get("_cluster_timeline") is None:
        controller.__dict__["_cluster_timeline"] = CoordinatorTimeline(
            controller._cluster_store.path.with_name("cluster-history.sqlite3")
        )
    standby = controller.__dict__.get("_standby_buffer")
    timeline = controller.__dict__["_cluster_timeline"]
    if standby is not None:
        previous_epoch = decision.epoch.epoch - 1
        for batch in standby.batches():
            if batch.source_epoch != previous_epoch:
                continue
            try:
                timeline.import_batch(
                    batch,
                    cluster_id=state.cluster_id,
                    expected_epoch=previous_epoch,
                    now=time.time(),
                )
            except ValueError:
                continue
    update_listener_fence(controller, state)


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
        transport=build_trusted_transport(record),
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


def _is_local_subcoordinator(controller: Any) -> bool:
    from maintenance.components.cluster_roles import ClusterRole

    return ClusterRole.SUBCOORDINATOR in (
        controller._cluster_state.local_assignment.roles
    )


def _renew_local_coordinator_lease(
    controller: Any, manager: PeerConnectionManager
) -> None:
    from maintenance.components.cluster_roles import ClusterRole, FencingError

    state = controller._cluster_state
    epoch = state.coordinator_epoch
    if epoch is None:
        return
    assignment = state.local_assignment
    if (
        ClusterRole.COORDINATOR not in assignment.roles
        or assignment.revoked
        or assignment.paused
    ):
        return
    now = time.time()
    if now >= epoch.lease_expires_at or now < epoch.lease_expires_at - 40.0:
        return
    try:
        manager.renew_cluster_lease(
            state,
            coordinator_id=NodeId(state.local_node_id),
            fencing_token=epoch.fencing_token,
            now=now,
        )
    except FencingError:
        return


def reconcile_peer_connections(controller: Any) -> None:
    manager = controller._peer_connections()
    if manager is None or controller._is_closing:
        return
    if _is_local_subcoordinator(controller):
        manager.promote_if_due(controller._cluster_state)
    _renew_local_coordinator_lease(controller, manager)
    queue_cluster_uploads(controller, manager)
    deadline = manager.reconcile()
    controller._schedule_peer_reconciliation(deadline)


def queue_cluster_uploads(controller: Any, manager: PeerConnectionManager) -> None:
    """Deliver bounded local snapshots through the existing coordinator runner."""

    state = controller._cluster_state
    epoch = state.coordinator_epoch
    snapshot = getattr(controller, "snapshot", None)
    if epoch is None or snapshot is None:
        return
    registry = controller.__dict__.get("_node_registry")
    coordinator_context = None
    subcoordinator_context = None
    if registry is not None:
        for context in registry.contexts():
            if context.descriptor.role == "coordinator" and not context.descriptor.is_local:
                coordinator_context = context
            if context.descriptor.role == "subcoordinator" and not context.descriptor.is_local:
                subcoordinator_context = context
    resources = getattr(snapshot, "resources", ())
    now = time.time()
    sequence = int(controller.__dict__.get("_cluster_upload_sequence", 0)) + 1
    controller.__dict__["_cluster_upload_sequence"] = sequence
    payload = tuple(
        ResourceSnapshot(
            NodeId(state.local_node_id),
            str(getattr(resource, "key", "unknown")),
            str(getattr(resource, "value", "Unavailable")),
            None,
            getattr(resource, "percent", None),
            now,
        )
        for resource in resources
    )
    batch = SnapshotBatch(
        f"{state.local_node_id}:{epoch.epoch}:{sequence}",
        NodeId(state.local_node_id),
        epoch.epoch,
        sequence,
        now,
        payload,
        0,
        state.cluster_id,
    )
    batch = replace(
        batch,
        encoded_size=len(
            json.dumps(snapshot_batch_to_dict(batch), separators=(",", ":")).encode()
        ),
    )
    local_roles = state.local_assignment.roles
    has_active_job = state.local_assignment.has_active_job
    if coordinator_context is not None and coordinator_context.provider is not None and "worker" in {
        role.value for role in local_roles
    } and "coordinator" not in {role.value for role in local_roles} and should_upload_job(
        sequence, has_active_job
    ):
        key = f"cluster:worker-snapshot:{coordinator_context.node_id.value}"
        if not manager._coordinator.in_flight(key):
            manager._coordinator.run(
                key,
                lambda cancel, _progress: coordinator_context.provider.upload_snapshot(
                    snapshot_batch_to_dict(batch),
                    cluster_id=state.cluster_id,
                    epoch=epoch.epoch,
                    fencing_token=epoch.fencing_token,
                ),
            )
    if subcoordinator_context is not None and subcoordinator_context.provider is not None and "coordinator" in {
        role.value for role in local_roles
    }:
        timeline = controller.__dict__.get("_cluster_timeline")
        batches = timeline.batches() if timeline is not None else ()
        if batches:
            latest = batches[-1]
            key = f"cluster:standby-batch:{subcoordinator_context.node_id.value}"
            if not manager._coordinator.in_flight(key):
                manager._coordinator.run(
                    key,
                    lambda cancel, _progress: subcoordinator_context.provider.upload_standby_batch(
                        snapshot_batch_to_dict(latest),
                        cluster_id=state.cluster_id,
                        epoch=epoch.epoch,
                        fencing_token=epoch.fencing_token,
                    ),
                )


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
    if (
        record.transport_fingerprint is not None
        and candidate.transport_fingerprint != record.transport_fingerprint
    ):
        context.descriptor = replace(
            descriptor,
            identity_status=NodeIdentityStatus.MISMATCH,
            identity_fingerprint=record.identity_fingerprint,
        )
        controller._nodes_error(
            f"TLS fingerprint mismatch for {descriptor.display_name}; re-pair required"
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
    endpoint_changed = address != record.host or port != record.port
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
                build_trusted_transport(replace(record, host=address, port=port))
                if record.transport_fingerprint
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
        transport_fingerprint=record.transport_fingerprint,
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
    updated_state = replace(state, trusted_nodes=updated_records)
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
