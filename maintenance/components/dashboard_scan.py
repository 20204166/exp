"""Lifecycle state for the window's full dashboard scan."""

from __future__ import annotations

import threading
from collections.abc import Callable

from .coordinator import ScanCoordinator


class DashboardScanLifecycle:
    """Own generation, cancellation, timeout, and lease transitions.

    Rendering and the scan provider stay outside this component.  Callbacks are
    invoked only for the corresponding UI or worker boundary.
    """

    def __init__(
        self,
        *,
        coordinator: ScanCoordinator,
        is_closing: Callable[[], bool],
        schedule_timer: Callable[..., str | None],
        cancel_timer: Callable[[str | None], object],
        show_timeout_error: Callable[[str], None],
        schedule_rerun: Callable[[], None],
        timeout_callback: Callable[[int], None] | None = None,
        grace_callback: Callable[[int], None] | None = None,
        timeout_milliseconds: int,
        grace_milliseconds: int,
        timeout_message: str,
    ) -> None:
        self.coordinator = coordinator
        self._is_closing = is_closing
        self._schedule_timer = schedule_timer
        self._cancel_timer = cancel_timer
        self._show_timeout_error = show_timeout_error
        self._schedule_rerun = schedule_rerun
        self._timeout_callback = timeout_callback or self.handle_timeout
        self._grace_callback = grace_callback or self.release_lease_after_grace
        self._timeout_milliseconds = timeout_milliseconds
        self._grace_milliseconds = grace_milliseconds
        self._timeout_message = timeout_message
        self.cancel_event: threading.Event | None = None
        self.timeout_id: str | None = None
        self.lease_grace_id: str | None = None
        self.timed_out_generation: int | None = None
        self.resolved_generation = 0

    def start(
        self,
        on_started: Callable[[int, threading.Event], None],
        start_worker: Callable[[int, threading.Event], None],
    ) -> None:
        if self._is_closing():
            return
        generation, started = self.coordinator.begin()
        if not started:
            return
        cancel_event = threading.Event()
        self.cancel_event = cancel_event
        on_started(generation, cancel_event)
        self.timeout_id = self._schedule_timer(
            self._timeout_milliseconds,
            self._timeout_callback,
            generation,
        )
        start_worker(generation, cancel_event)

    def claim_resolution(self, generation: int) -> tuple[bool, bool]:
        if generation <= self.resolved_generation:
            return False, False
        finished, rerun_requested = self.coordinator.finish(generation)
        if not finished:
            return False, False
        self.resolved_generation = generation
        return finished, rerun_requested

    def resolve_generation(self, generation: int) -> tuple[bool, bool]:
        finished, rerun_requested = self.claim_resolution(generation)
        if not finished:
            return False, False
        self.cancel_timeout()
        self.cancel_event = None
        return True, rerun_requested

    def resolution_for_generation(self, generation: int) -> bool | None:
        if self.timed_out_generation == generation:
            return None
        resolved, rerun_requested = self.resolve_generation(generation)
        return rerun_requested if resolved else None

    def handle_timeout(self, generation: int) -> None:
        if self._is_closing():
            return
        if generation != self.coordinator.generation:
            return
        if generation <= self.resolved_generation:
            return
        if self.timed_out_generation is not None:
            return
        self.timeout_id = None
        self.timed_out_generation = generation
        self.lease_grace_id = self._schedule_timer(
            self._grace_milliseconds,
            self._grace_callback,
            generation,
        )
        cancel_event = self.cancel_event
        self.cancel_event = None
        if cancel_event is not None:
            cancel_event.set()
        self._show_timeout_error(self._timeout_message)

    def release_timed_out_lease(
        self, generation: int, *, cancel_grace_timer: bool
    ) -> None:
        self.resolved_generation = generation
        self.timed_out_generation = None
        if cancel_grace_timer:
            self._cancel_timer(self.lease_grace_id)
        self.lease_grace_id = None
        finished, rerun_requested = self.coordinator.finish(generation)
        if finished and rerun_requested and not self._is_closing():
            self._schedule_rerun()

    def release_lease_after_grace(self, generation: int) -> None:
        if self._is_closing():
            return
        if self.timed_out_generation != generation:
            return
        if generation <= self.resolved_generation:
            return
        self.release_timed_out_lease(generation, cancel_grace_timer=False)

    def resolve_completed_worker(self) -> None:
        if self._is_closing():
            return
        generation = self.timed_out_generation
        if generation is None or generation <= self.resolved_generation:
            return
        self.release_timed_out_lease(generation, cancel_grace_timer=True)

    def cancel_timeout(self) -> None:
        self._cancel_timer(self.timeout_id)
        self.timeout_id = None

    def cancel(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.cancel_event = None
        self.coordinator.cancel()
        self.cancel_timeout()
        self.timed_out_generation = None
        self._cancel_timer(self.lease_grace_id)
        self.lease_grace_id = None
