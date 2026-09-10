"""Application-level lifecycle orchestration for local network discovery."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from maintenance.components.network_discovery import (
    PROTOCOL_VERSION,
    REAP_TICK_SECONDS,
    DiscoveryAdvertisement,
    NetworkDiscovery,
)
from maintenance.nodes import (
    LOCAL_NODE_ID,
    NodeId,
    NodeRegistry,
    node_identity_fingerprint,
)

if TYPE_CHECKING:
    from maintenance.cluster import ClusterState

LOGGER = logging.getLogger(__name__)
_MAX_STABILIZATION_MILLISECONDS = 250


@dataclass(frozen=True, slots=True)
class DiscoveryStartResult:
    """Outcome of one attempt to start application discovery."""

    started: bool
    available: bool = False
    reason: str | None = None


class DiscoverySession:
    """Coordinate discovery lifecycle without owning trust or presentation."""

    def __init__(
        self,
        *,
        coordinator: Any,
        registry: NodeRegistry,
        get_cluster_state: Callable[[], "ClusterState | None"],
        set_cluster_state: Callable[["ClusterState"], None],
        save_cluster_state: Callable[["ClusterState"], bool],
        schedule_timer: Callable[[int, Callable[[], None]], str | None],
        cancel_timer: Callable[[str | None], bool],
        start_background_poll: Callable[[], None],
        on_candidate: Callable[[Any], None],
        on_lost: Callable[[str], None],
        discovery_factory: Callable[..., Any] = NetworkDiscovery,
        app_version: str = "",
        is_closing: Callable[[], bool] = lambda: False,
        get_listener_endpoint: Callable[
            [], tuple[bool, int | None, str | None]
        ] = lambda: (False, None, None),
        on_stabilized: Callable[[], None] | None = None,
        stabilization_milliseconds: int = 100,
        on_presence_changed: Callable[[], None] | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._registry = registry
        self._get_cluster_state = get_cluster_state
        self._set_cluster_state = set_cluster_state
        self._save_cluster_state = save_cluster_state
        self._schedule_timer = schedule_timer
        self._cancel_timer = cancel_timer
        self._start_background_poll = start_background_poll
        self._on_candidate = on_candidate
        self._on_lost = on_lost
        self._discovery_factory = discovery_factory
        self._app_version = app_version
        self._is_closing = is_closing
        self._get_listener_endpoint = get_listener_endpoint
        self._on_stabilized = on_stabilized or (lambda: None)
        self._on_presence_changed = on_presence_changed or (lambda: None)
        self._stabilization_milliseconds = min(
            max(stabilization_milliseconds, 0), _MAX_STABILIZATION_MILLISECONDS
        )
        self.timer_id: str | None = None
        self._stabilization_timer_id: str | None = None
        self._stabilization_scheduled = False
        self._active = False
        self._lifecycle_generation: object | None = None

    def start(self) -> DiscoveryStartResult:
        if self._active:
            return DiscoveryStartResult(started=True, available=True)

        state = self._get_cluster_state()
        if state is not None and not state.discovery_enabled:
            return DiscoveryStartResult(started=False, reason="disabled")
        if state is not None and not state.local_identity_persisted:
            if not self._save_cluster_state(state):
                LOGGER.warning("Discovery waiting for durable local identity")
                return DiscoveryStartResult(
                    started=False, reason="identity persistence"
                )
            state = replace(state, local_identity_persisted=True)
            self._set_cluster_state(state)

        try:
            local_context = self._registry.context(
                self._registry.local_id() or NodeId(LOCAL_NODE_ID)
            )
        except KeyError:
            return DiscoveryStartResult(started=False, reason="local node unavailable")

        descriptor = local_context.descriptor
        endpoint = self._get_listener_endpoint()
        connectable, listener_port = endpoint[:2]
        transport_fingerprint = endpoint[2] if len(endpoint) > 2 else None
        advertisement = DiscoveryAdvertisement(
            stable_id=descriptor.id.value,
            display_name=descriptor.display_name,
            hostname=descriptor.hostname,
            app_version=self._app_version,
            protocol_version=PROTOCOL_VERSION,
            platform=descriptor.platform,
            connectable=connectable,
            port=listener_port if connectable else None,
            identity_fingerprint=(
                local_context.descriptor.identity_fingerprint
                or node_identity_fingerprint(descriptor.id)
            ),
            transport_fingerprint=(transport_fingerprint if connectable else None),
        )
        discovery = self._discovery_factory(
            descriptor.id,
            advertisement=advertisement,
        )
        started = self._coordinator.start_discovery(
            discovery,
            on_candidate=self._handle_candidate,
            on_lost=self._handle_lost,
        )
        if not started:
            return DiscoveryStartResult(
                started=False,
                available=discovery.available,
                reason=discovery.unavailable_reason or "unknown error",
            )

        self._active = True
        self._lifecycle_generation = object()
        self.timer_id = self._schedule_timer(int(REAP_TICK_SECONDS * 1000), self.tick)
        self._start_background_poll()
        return DiscoveryStartResult(started=True, available=True)

    def _handle_candidate(self, candidate: Any) -> None:
        self._on_candidate(candidate)
        self._on_presence_changed()
        self._schedule_stabilization()

    def _handle_lost(self, stable_id: str) -> None:
        self._on_lost(stable_id)
        self._on_presence_changed()
        self._schedule_stabilization()

    def _schedule_stabilization(self) -> None:
        if not self._active or self._is_closing():
            return
        if self._stabilization_scheduled:
            return
        generation = self._lifecycle_generation
        self._stabilization_scheduled = True
        self._stabilization_timer_id = self._schedule_timer(
            self._stabilization_milliseconds,
            lambda: self._run_stabilization(generation),
        )

    def _run_stabilization(self, generation: object | None) -> None:
        if (
            not self._active
            or self._is_closing()
            or generation is not self._lifecycle_generation
        ):
            return
        self._stabilization_timer_id = None
        self._stabilization_scheduled = False
        self._on_stabilized()

    def tick(self) -> None:
        self.timer_id = None
        if self._is_closing():
            return
        self._coordinator.discovery_tick()
        self.timer_id = self._schedule_timer(int(REAP_TICK_SECONDS * 1000), self.tick)

    def stop(self) -> None:
        self._cancel_timer(self.timer_id)
        self.timer_id = None
        if self._stabilization_scheduled:
            self._cancel_timer(self._stabilization_timer_id)
        self._stabilization_timer_id = None
        self._stabilization_scheduled = False
        self._lifecycle_generation = None
        self._active = False
        self._coordinator.stop_discovery()
