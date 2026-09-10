"""Transport-independent reconciliation policy for trusted peers."""

import threading
import time
from collections.abc import Callable
from typing import Any

from maintenance.nodes import (
    ConnectionState,
    NodeConnectionStatus,
    NodeContext,
    NodeId,
    NodeRegistry,
    PeerFailure,
    RetryState,
    classify_peer_failure,
    is_trusted_descriptor,
    node_operation_key,
)


class PeerConnectionManager:
    """Reconcile trusted peer connections through the shared coordinator.

    This class deliberately owns neither timers nor workers. The caller invokes
    ``reconcile`` from its one application timer and supplies the transport
    operation used for each attempt.
    """

    def __init__(
        self,
        *,
        registry: NodeRegistry,
        coordinator: Any,
        connect: Callable[[NodeContext, threading.Event, Callable[[str], None]], Any],
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[int], float] = lambda _attempt: 0.0,
        is_closing: Callable[[], bool] = lambda: False,
        can_connect: Callable[[NodeContext], bool] = lambda _context: True,
        on_connected: Callable[[NodeContext, Any], None] | None = None,
        on_failed: Callable[[NodeContext, PeerFailure], None] | None = None,
    ) -> None:
        self._registry = registry
        self._coordinator = coordinator
        self._connect = connect
        self._clock = clock
        self._jitter = jitter
        self._is_closing = is_closing
        self._can_connect = can_connect
        self._on_connected = on_connected
        self._on_failed = on_failed
        self._stopped = False

    def reconcile(self, now: float | None = None) -> float | None:
        """Start due attempts and return the earliest future retry deadline."""

        if self._stopped or self._is_closing():
            return None
        current = self._clock() if now is None else now
        deadlines: list[float] = []
        for context in self._registry.contexts():
            if context.descriptor.is_local or not is_trusted_descriptor(
                context.descriptor
            ):
                continue
            if context.connection.status is NodeConnectionStatus.IDENTITY_CHANGED:
                continue
            if not self._can_connect(context):
                continue
            key = node_operation_key(context.node_id, "connect")
            if self._coordinator.in_flight(key):
                continue
            retry_at = context.retry.next_attempt_at
            if (
                context.connection.status is not NodeConnectionStatus.ONLINE
                and context.retry.automatic_retry
                and (retry_at is None or retry_at <= current)
            ):
                self._start(context, current)
                continue
            if context.retry.automatic_retry and retry_at is not None:
                deadlines.append(retry_at)
        return min(deadlines) if deadlines else None

    def _start(self, context: NodeContext, now: float) -> None:
        context.connection_generation += 1
        generation = context.connection_generation
        context.connection = ConnectionState.connecting(now=now)
        key = node_operation_key(context.node_id, "connect")

        def task(cancel_event: threading.Event, progress: Callable[[str], None]) -> Any:
            return self._connect(context, cancel_event, progress)

        self._coordinator.run(
            key,
            task,
            on_result=lambda _key, result: self.complete(
                context.node_id, generation, result=result
            ),
            on_error=lambda _key, error: self.failed(
                context.node_id, generation, classify_peer_failure(error), error
            ),
        )

    def complete(self, node_id: NodeId, generation: int, *, result: Any = None) -> bool:
        """Accept a successful attempt only for the current node generation."""

        if self._stopped:
            return False
        try:
            context = self._registry.context(node_id)
        except KeyError:
            return False
        if context.connection_generation != generation:
            return False
        context.connection = ConnectionState.online(now=self._clock())
        context.retry.reset()
        if self._on_connected is not None:
            self._on_connected(context, result)
        return True

    def failed(
        self,
        node_id: NodeId,
        generation: int,
        failure: PeerFailure,
        reason: str | None = None,
    ) -> bool:
        """Record a current-generation failure and schedule bounded retry."""

        if self._stopped:
            return False
        try:
            context = self._registry.context(node_id)
        except KeyError:
            return False
        if context.connection_generation != generation:
            return False
        status = (
            NodeConnectionStatus.AUTHENTICATION_FAILED
            if failure is PeerFailure.AUTHENTICATION_FAILED
            else NodeConnectionStatus.IDENTITY_CHANGED
            if failure is PeerFailure.IDENTITY_CHANGED
            else NodeConnectionStatus.OFFLINE
        )
        context.connection = ConnectionState(
            status, reason=reason, changed_at=self._clock()
        )
        context.retry.record_failure(failure, now=self._clock(), jitter=self._jitter)
        if self._on_failed is not None:
            self._on_failed(context, failure)
        return True

    def cancel(self, node_id: NodeId) -> None:
        """Cancel a peer attempt and invalidate late completion callbacks."""

        try:
            context = self._registry.context(node_id)
        except KeyError:
            return
        if not isinstance(context.connection_generation, int):
            context.connection_generation = 0
        context.connection_generation += 1
        self._coordinator.cancel(node_operation_key(node_id, "connect"))

    def mark_disconnected(
        self, node_id: NodeId, reason: str = "peer disappeared"
    ) -> bool:
        """Turn a connected peer offline when discovery loses its presence."""

        try:
            context = self._registry.context(node_id)
        except KeyError:
            return False
        if context.descriptor.is_local:
            return False
        context.connection_generation += 1
        self._coordinator.cancel(node_operation_key(node_id, "connect"))
        context.connection = ConnectionState.offline(reason, now=self._clock())
        context.retry.record_failure(
            PeerFailure.DISAPPEARED, now=self._clock(), jitter=self._jitter
        )
        if self._on_failed is not None:
            self._on_failed(context, PeerFailure.DISAPPEARED)
        return True

    def cancel_all(self) -> None:
        for context in self._registry.contexts():
            if not context.descriptor.is_local:
                self.cancel(context.node_id)

    def shutdown(self) -> None:
        self._stopped = True
        self.cancel_all()


__all__ = ["PeerConnectionManager", "RetryState"]
