"""Selected-node bootstrap and cluster persistence adapters."""

from __future__ import annotations

from typing import Any


def build_local_node_context(controller: Any) -> None:
    context = _window_symbols().node_context.build_local_node_context(
        cluster_state=controller._cluster_state,
        analyzer=controller.analyzer,
        process_manager=controller.process_manager,
        file_manager=controller.file_manager,
        scheduler=controller._component_scheduler,
        coordinator=controller._coordinator,
        snapshot=controller.snapshot,
        capabilities=controller._capabilities,
    )
    controller.__dict__["_capability_counts"] = context.capability_counts
    controller.__dict__["_failed_card_counts"] = context.failed_card_counts
    controller._node_registry.register_context(context)
    controller._selected_node_id = controller._node_registry.select(context.node_id)


def restore_trusted_nodes(controller: Any) -> None:
    registry = controller.__dict__.get("_node_registry")
    state = controller.__dict__.get("_cluster_state")
    if registry is None or state is None:
        return
    window = _window_symbols()
    window.node_context.restore_trusted_nodes(
        registry=registry, cluster_state=state, logger=window.LOGGER
    )


def save_cluster_state(controller: Any, state: Any) -> bool:
    window = _window_symbols()
    try:
        controller._cluster_store.save(state)
    except window.ClusterSaveError as error:
        window.LOGGER.warning("Failed to save cluster settings: %s", error)
        return False
    controller._cluster_state = state
    controller._sync_peer_listener_grants()
    return True


def sync_peer_listener_grants(controller: Any) -> None:
    window = _window_symbols()
    server = controller.__dict__.get("_peer_server")
    if server is None:
        if controller._cluster_state.peer_grants:
            controller._start_peer_listener()
        return
    grants = {
        window.NodeId(grant.caller_node_id): window.PeerGrant(
            caller_node_id=window.NodeId(grant.caller_node_id),
            secret=grant.secret,
            permissions=grant.permissions,
        )
        for grant in controller._cluster_state.peer_grants
    }
    if not grants:
        server.stop()
        controller._peer_server = None
        return
    server.update_grants(grants)


def _window_symbols() -> Any:
    import window

    return window
