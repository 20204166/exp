"""Live scan-state coordination for the dashboard window.

Includes the dashboard ``ScanCoordinator``, the per-component refresh
``ComponentRefreshScheduler``, and the universal ``AppCoordinator`` — the
single "shock absorber" between slow background work (scans, page loads)
and the Tkinter UI thread.
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)


def _make_monotonic_clock(clock: Callable[[], float]) -> Callable[[], float]:
    """Prevent an injected clock from moving backwards between reads."""

    last = float("-inf")

    def read() -> float:
        nonlocal last
        current = float(clock())
        if current < last:
            return last
        last = current
        return current

    return read


@dataclass(frozen=True, slots=True)
class RefreshIntervals:
    """Per-component refresh intervals in milliseconds.

    Chosen from measured scan cost and how quickly each metric meaningfully
    changes: CPU usage and network rates are live (~1s); memory is moderate
    (existing 5s); GPU usage/temperature moderate (3s); storage capacity and
    battery state change slowly (30s). Static hardware is not in this mapping
    because it is cached by the scanner, not refreshed here.
    """

    cpu: int = 1000
    network: int = 1000
    memory: int = 5000
    gpu: int = 3000
    storage: int = 30000
    battery: int = 30000

    def as_dict(self) -> dict[str, int]:
        return {
            "cpu": self.cpu,
            "network": self.network,
            "memory": self.memory,
            "gpu": self.gpu,
            "storage": self.storage,
            "battery": self.battery,
        }


@dataclass(slots=True)
class _RefreshEntry:
    interval: float
    next_due: float = 0.0
    in_flight: bool = False
    paused: bool = False
    refresh_requested: bool = False


class ComponentRefreshScheduler:
    """Track per-component refresh due times and prevent overlapping scans."""

    def __init__(
        self,
        intervals: dict[str, int] | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        configured_intervals = (
            dict(intervals) if intervals is not None else RefreshIntervals().as_dict()
        )
        for milliseconds in configured_intervals.values():
            if milliseconds <= 0:
                raise ValueError("Interval must be positive")
        self.intervals = configured_intervals
        self._clock = _make_monotonic_clock(clock or time.monotonic)
        self._records = {
            key: _RefreshEntry(interval=milliseconds / 1000.0)
            for key, milliseconds in self.intervals.items()
        }

    def begin(self, key: str, now: float) -> bool:
        entry = self._records.get(key)
        if entry is None:
            entry = _RefreshEntry(interval=5.0)
            self._records[key] = entry
        if entry.in_flight or entry.paused:
            return False
        if not self._is_due(entry, now):
            return False
        entry.in_flight = True
        entry.refresh_requested = False
        if now >= entry.next_due:
            periods = int((now - entry.next_due) // entry.interval) + 1
            entry.next_due += periods * entry.interval
        else:
            entry.next_due = now + entry.interval
        return True

    def finish(self, key: str) -> None:
        entry = self._records.get(key)
        if entry is None:
            return
        entry.in_flight = False

    def cancel(self, key: str) -> None:
        if key not in self.intervals:
            raise ValueError(f"Unknown component: {key}")
        entry = self._entry(key)
        entry.in_flight = False
        entry.refresh_requested = False

    def mark_all_refreshed(self, now: float) -> None:
        for entry in self._records.values():
            entry.next_due = now + entry.interval
            entry.refresh_requested = False

    def due_keys(self, now: float) -> tuple[str, ...]:
        return tuple(
            key for key, entry in self._records.items() if self._is_due(entry, now)
        )

    def collect_due(self, now: float | None = None) -> tuple[str, ...]:
        resolved_now = self._clock() if now is None else now
        return self.due_keys(resolved_now)

    def next_deadline(self, now: float | None = None) -> float | None:
        resolved_now = self._clock() if now is None else now
        deadlines: list[float] = []
        for entry in self._records.values():
            ready_at = self._ready_at(entry, resolved_now)
            if ready_at is not None:
                deadlines.append(ready_at)
        return min(deadlines) if deadlines else None

    def in_flight(self, key: str) -> bool:
        return self._entry(key).in_flight

    def has_pending_work(self) -> bool:
        """Return whether a component has a lease or coalesced refresh."""

        return any(
            entry.in_flight or entry.refresh_requested
            for entry in self._records.values()
        )

    def set_interval(self, key: str, milliseconds: int, now: float) -> None:
        if key not in self.intervals:
            raise ValueError(f"Unknown component: {key}")
        if not isinstance(milliseconds, int) or isinstance(milliseconds, bool):
            raise TypeError("Interval must be an integer number of milliseconds")
        if milliseconds <= 0:
            raise ValueError("Interval must be positive")
        self.intervals[key] = milliseconds
        entry = self._entry(key)
        entry.interval = milliseconds / 1000.0
        entry.next_due = now + entry.interval

    def pause(self, key: str) -> None:
        if key not in self.intervals:
            raise ValueError(f"Unknown component: {key}")
        self._entry(key).paused = True

    def resume(self, key: str) -> None:
        if key not in self.intervals:
            raise ValueError(f"Unknown component: {key}")
        self._entry(key).paused = False

    def is_paused(self, key: str) -> bool:
        return self._entry(key).paused

    def request_refresh(self, key: str) -> None:
        if key not in self.intervals:
            raise ValueError(f"Unknown component: {key}")
        self._entry(key).refresh_requested = True

    def _entry(self, key: str) -> _RefreshEntry:
        try:
            return self._records[key]
        except KeyError as error:
            raise ValueError(f"Unknown component: {key}") from error

    @staticmethod
    def _ready_at(entry: _RefreshEntry, now: float) -> float | None:
        if entry.paused or entry.in_flight:
            return None
        ready_at = entry.next_due
        if entry.refresh_requested:
            ready_at = min(ready_at, now)
        return ready_at

    def _is_due(self, entry: _RefreshEntry, now: float) -> bool:
        ready_at = self._ready_at(entry, now)
        return ready_at is not None and ready_at <= now


@dataclass
class ScanCoordinator:
    """Track live scan state for `window.AppWindow`.

    Extracted from the live-scan coordination flow in `window.py:394-451`.

    It keeps the in-flight flag, generation counter, and queued rerun request
    together so the UI can wait for the current loading cycle to finish before
    scheduling the next one.
    """

    active: bool = False
    generation: int = 0
    rerun_requested: bool = False

    def begin(self) -> tuple[int, bool]:
        """Start a scan or mark that one should run again after completion."""

        if self.active:
            self.rerun_requested = True
            return self.generation, False

        self.active = True
        self.generation += 1
        return self.generation, True

    def finish(self, generation: int) -> tuple[bool, bool]:
        """Finish the active generation and report whether a rerun is queued."""

        if generation != self.generation:
            return False, False

        return True, self._reset_state_and_return_rerun()

    def cancel(self) -> None:
        """Invalidate the active generation without scheduling another scan."""

        if self.active:
            # A queued completion from the cancelled worker must never satisfy
            # a later target selection before its replacement scan begins.
            self.generation += 1
        self._reset_state()

    def _reset_state(self) -> None:
        self.active = False
        self.rerun_requested = False

    def _reset_state_and_return_rerun(self) -> bool:
        rerun_requested = self.rerun_requested
        self._reset_state()
        return rerun_requested


@dataclass
class AppRunState:
    """Per-key runtime state for one coordinated background operation."""

    in_flight: bool = False
    generation: int = 0
    rerun_requested: bool = False
    cancelled: bool = False
    cancel_event: threading.Event | None = None
    last_result: Any | None = None
    subscribers: list[Callable[[str, Any | None], None]] | None = field(default=None)
    on_result: Callable[[str, Any], None] | None = None
    on_error: Callable[[str, str], None] | None = None
    on_progress: Callable[[str, str], None] | None = None
    on_finished: Callable[[], None] | None = None
    task_factory: Callable[..., Any] | None = None


class AppCoordinator:
    """Universal per-key shock absorber between background work and the UI.

    Dependency-composed: the caller injects how the work actually runs (the
    ``runner``) and how results reach the UI thread (``deliver``), so this
    coordinator never owns threading, widgets, or delivery queues itself. The
    whole app shares one instance, so pages, dialog scans, component scans,
    and the dashboard all move at one steady pace:

    - **Coalesce**: repeated triggers of the same key collapse into one
      in-flight run plus at most one pending rerun, so rapid triggers (button
      spam, dialog reopens, overlapping scans) can never start duplicate
      heavy work.
    - **Cache**: the last good completed result is kept for instant retrieval
      (``last_result`` / ``store``), so a reopened surface renders immediately.
    - **Safe cancel / retry**: ``cancel`` sets a cooperative event, late
      results are dropped generational, the owner is told it was cancelled,
      and waiting subscribers are woken with ``None`` so they can retry by
      re-triggering.
    - **One delivery path**: ``run`` executes the task through the injected
      ``runner`` and delivers every completion, error, and progress message
      through the injected ``deliver`` onto the UI thread — worker threads
      never touch widgets.

    Thread contract: ``run``/``begin``/``finish``/``cancel`` are called on the
    main thread; only each run's ``cancel_event`` crosses threads; ``deliver``
    must be thread-safe and schedule callbacks on the UI thread (default:
    synchronous, for tests); ``on_activity`` (if given) is called on the
    triggering thread so the app can keep its drain poll alive.
    """

    def __init__(
        self,
        *,
        runner: Callable[[Callable[[], None]], None] | None = None,
        deliver: Callable[[Callable[[], None]], None] | None = None,
        on_activity: Callable[[], None] | None = None,
    ) -> None:
        self._executor = (
            None if runner is not None else ThreadPoolExecutor(max_workers=4)
        )
        self._runner = runner or self._submit_default
        self._deliver = deliver or (lambda callback: callback())
        self._on_activity = on_activity
        self._states: dict[str, AppRunState] = {}
        self._coalesced_generations: dict[str, int] = {}
        self._coalesced_callbacks: dict[str, Callable[[], None]] = {}
        self._coalesced_pending: set[str] = set()
        self._deferred_triggers: dict[str, Callable[[], None]] = {}
        self._discovery: Any = None
        self._discovery_generation: object | None = None
        self._discovery_handlers: dict[str, Any] = {}

    def _submit_default(self, worker: Callable[[], None]) -> None:
        if self._executor is None:
            raise RuntimeError("default worker executor is unavailable")
        self._executor.submit(worker)

    def state(self, key: str) -> AppRunState:
        return self._states.setdefault(key, AppRunState())

    @property
    def has_pending_work(self) -> bool:
        return any(state.in_flight for state in self._states.values())

    def begin(self, key: str) -> tuple[int, bool]:
        """Claim one operation run, returning ``(generation, started)``.

        A trigger while the operation is in flight is coalesced into one
        rerun (``started=False``).
        """

        state = self.state(key)
        if state.in_flight:
            state.rerun_requested = True
            return state.generation, False
        generation = self._claim_run(state)
        return generation, True

    def _claim_run(self, state: AppRunState) -> int:
        """Claim a fresh run on ``state`` and return its new generation.

        Shared by ``begin`` and ``_start_run`` so the run-claim state
        transition (in-flight, next generation, cleared rerun/cancel flags,
        fresh cancel event) exists in exactly one place.
        """

        state.in_flight = True
        state.generation += 1
        state.rerun_requested = False
        state.cancelled = False
        state.cancel_event = threading.Event()
        return state.generation

    def run(
        self,
        key: str,
        task_factory: Callable[[threading.Event, Callable[[str], None]], Any],
        *,
        on_result: Callable[[str, Any], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
        on_progress: Callable[[str, str], None] | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> int | None:
        """Run one background operation under the shared key.

        Returns the run generation, or ``None`` when the trigger was coalesced
        into the in-flight run (its completion will notify any subscribers and
        honour one pending rerun). Callbacks fire on the UI thread through the
        injected ``deliver``.
        """

        state = self.state(key)
        if state.in_flight:
            state.rerun_requested = True
            return None
        if on_result is not None:
            state.on_result = on_result
        if on_error is not None:
            state.on_error = on_error
        if on_progress is not None:
            state.on_progress = on_progress
        state.on_finished = on_finished
        state.task_factory = task_factory
        return self._start_run(key, state)

    def _start_run(self, key: str, state: AppRunState) -> int:
        generation = self._claim_run(state)
        cancel_event = state.cancel_event
        task_factory = state.task_factory

        def emit_progress(message: str) -> None:
            self._deliver(lambda: self._invoke_progress(key, generation, message))

        def worker() -> None:
            try:
                result = task_factory(cancel_event, emit_progress)  # type: ignore[misc]
            except Exception as error:  # noqa: BLE001 - failures reach the UI thread.
                message = str(error)
                self._deliver(
                    lambda: self._complete_run(key, generation, error=message)
                )
            else:
                self._deliver(
                    lambda: self._complete_run(key, generation, result=result)
                )

        self._note_activity()
        try:
            self._runner(worker)
        except RuntimeError as error:
            message = str(error)
            LOGGER.warning("Could not start operation %r: %s", key, message)
            self._deliver(lambda: self._complete_run(key, generation, error=message))
        return generation

    def _note_activity(self) -> None:
        if self._on_activity is not None:
            self._on_activity()

    def _invoke_progress(self, key: str, generation: int, message: str) -> None:
        state = self._states.get(key)
        if state is None or generation != state.generation or state.cancelled:
            return
        self._safe_invoke(state.on_progress, key, message)

    def _settle_run(self, state: AppRunState) -> bool:
        """Clear one run's in-flight state and return its rerun flag.

        Shared by ``_complete_run`` and ``finish`` so the settle transition
        (in-flight off, cancel event dropped, rerun flag read and cleared)
        exists in exactly one place.
        """

        state.in_flight = False
        state.cancel_event = None
        rerun_requested = state.rerun_requested
        state.rerun_requested = False
        return rerun_requested

    def _complete_run(
        self,
        key: str,
        generation: int,
        *,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        state = self._states.get(key)
        if state is None or generation != state.generation or not state.in_flight:
            return
        rerun_requested = self._settle_run(state)
        if state.cancelled:
            self._invoke_finished(key, state)
            if rerun_requested:
                self._replay(key, state)
            return
        if error is None:
            state.last_result = result
            self._notify_subscribers(state, key, result)
            self._safe_invoke(state.on_result, key, result)
        else:
            self._notify_subscribers(state, key, None)
            self._safe_invoke(state.on_error, key, error)
        self._invoke_finished(key, state)
        if rerun_requested:
            self._replay(key, state)

    @staticmethod
    def _invoke_finished(key: str, state: AppRunState) -> None:
        if state.on_finished is None:
            return
        try:
            state.on_finished()
        except Exception as finalizer_error:  # noqa: BLE001 - completion must still be delivered.
            LOGGER.warning("Operation %r finalizer failed: %s", key, finalizer_error)

    def _replay(self, key: str, state: AppRunState) -> None:
        if state.task_factory is not None:
            self._start_run(key, state)

    def _safe_invoke(
        self,
        handler: Callable[..., None] | None,
        key: str,
        payload: Any,
    ) -> None:
        if handler is None:
            return
        try:
            handler(key, payload)
        except Exception as error:  # noqa: BLE001 - a dead widget must never kill the drain.
            LOGGER.warning("Operation %r callback failed: %s", key, error)

    def _notify_subscribers(
        self,
        state: AppRunState,
        key: str,
        result: Any | None,
    ) -> None:
        subscribers = state.subscribers or []
        state.subscribers = None
        for callback in subscribers:
            try:
                callback(key, result)
            except Exception as error:  # noqa: BLE001 - subscribers are best-effort.
                LOGGER.warning("Operation %r subscriber failed: %s", key, error)

    def finish(
        self,
        key: str,
        generation: int,
        result: Any | None = None,
    ) -> tuple[bool, bool]:
        """Complete one claimed run, caching its result and notifying waiters.

        State API for callers that manage their own runner/delivery (e.g.
        tests and non-run-based consumers). A ``None`` result (an error or
        cancellation) is not cached, so the last good result survives.
        """

        state = self._states.get(key)
        if state is None or generation != state.generation or not state.in_flight:
            return False, False
        rerun_requested = self._settle_run(state)
        if state.cancelled:
            return False, rerun_requested
        if result is not None:
            state.last_result = result
        self._notify_subscribers(state, key, result)
        return True, rerun_requested

    def cancel(self, key: str, cancellation_message: str | None = None) -> None:
        """Cancel one run cooperatively and wake waiting subscribers.

        The run's in-flight flag is held until the worker's completion is
        delivered (so a new trigger can never overlap the old worker); the
        owner is notified once with ``cancellation_message`` (when given)
        through the delivered ``on_error`` channel. Any pending rerun is
        dropped with it, so a cancelled operation is never restarted by
        surprise; a trigger issued *after* the cancel is honoured once the
        worker quits.
        """

        state = self._states.get(key)
        self._deferred_triggers.pop(key, None)
        if state is None:
            return
        already_cancelled = state.cancelled
        state.cancelled = True
        state.rerun_requested = False
        if state.cancel_event is not None:
            state.cancel_event.set()
        # Waking waiters is idempotent (subscribers are cleared on the first
        # wake), but the owner must be told about the cancellation exactly
        # once even if cancel() is called repeatedly.
        if not already_cancelled:
            self._notify_subscribers(state, key, None)
        if (
            not already_cancelled
            and cancellation_message is not None
            and state.on_error is not None
        ):
            handler = state.on_error
            self._deliver(lambda: self._safe_invoke(handler, key, cancellation_message))

    def cancel_all(self, cancellation_message: str | None = None) -> None:
        """Cancel every tracked run, typically during shutdown."""

        for key in tuple(self._states):
            self.cancel(key, cancellation_message)

    def shutdown(self) -> None:
        """Stop accepting new default worker tasks during application teardown."""

        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    def in_flight(self, key: str) -> bool:
        state = self._states.get(key)
        return state.in_flight if state is not None else False

    def generation(self, key: str) -> int:
        state = self._states.get(key)
        return state.generation if state is not None else 0

    def last_result(self, key: str) -> Any | None:
        state = self._states.get(key)
        return state.last_result if state is not None else None

    def store(self, key: str, result: Any) -> None:
        """Cache one result for instant retrieval without a run lifecycle."""

        self.state(key).last_result = result

    def subscribe(
        self,
        key: str,
        callback: Callable[[str, Any | None], None],
    ) -> None:
        """Register a callback to receive the next shared run's result."""

        state = self.state(key)
        if state.subscribers is None:
            state.subscribers = []
        state.subscribers.append(callback)

    def unsubscribe(
        self,
        key: str,
        callback: Callable[[str, Any | None], None],
    ) -> None:
        """Remove a callback so a closed dialog no longer receives results."""

        state = self._states.get(key)
        if state is None or not state.subscribers:
            return
        # Compare by equality, not identity: dialogs access their bound
        # callback afresh when unsubscribing, producing a distinct-but-equal
        # bound-method object. Identity comparison would silently leave the
        # closed dialog subscribed so it still receives later results.
        state.subscribers = [item for item in state.subscribers if item != callback]

    def clear(self, key: str) -> None:
        self._states.pop(key, None)
        if key in self._coalesced_generations:
            self._coalesced_generations[key] += 1
        self._coalesced_callbacks.pop(key, None)
        self._coalesced_pending.discard(key)
        self._deferred_triggers.pop(key, None)

    def post(self, callback: Callable[[], None]) -> None:
        """Deliver one callback onto the UI thread and keep the poll alive.

        The shared delivery path used by discovery events and other long-lived
        event sources: ``deliver`` (thread-safe, schedules on the UI thread) is
        used exactly like every other coordinated completion, and
        ``on_activity`` keeps the application drain poll scheduled while a
        discovery event is in flight.
        """

        self._note_activity()
        self._deliver(callback)

    def post_coalesced(self, key: str, callback: Callable[[], None]) -> None:
        """Schedule at most one pending callback for ``key``."""

        self._note_activity()
        self._coalesced_callbacks[key] = callback
        if key in self._coalesced_pending:
            return

        generation = self._coalesced_generations.get(key, 0) + 1
        self._coalesced_generations[key] = generation
        self._coalesced_pending.add(key)

        def deliver() -> None:
            if self._coalesced_generations.get(key) != generation:
                self._coalesced_pending.discard(key)
                return
            self._coalesced_pending.discard(key)
            current = self._coalesced_callbacks.pop(key, None)
            if current is None:
                return
            current()

        self._deliver(deliver)

    def defer(self, key: str, trigger: Callable[[], None]) -> None:
        """Keep one non-urgent trigger until its owning surface is visible."""

        self._deferred_triggers[key] = trigger

    def flush_deferred(self, key: str) -> None:
        """Run and remove one deferred trigger, if one is pending."""

        trigger = self._deferred_triggers.pop(key, None)
        if trigger is not None:
            trigger()

    def start_discovery(
        self,
        discovery: Any,
        *,
        on_candidate: Callable[[Any], None],
        on_lost: Callable[[str], None],
    ) -> bool:
        """Own the discovery lifecycle: start it once and bridge its events.

        Idempotent: a second ``start_discovery`` with a different component is
        ignored while one is active. All candidate/lost events are delivered
        through ``post`` so registry updates always happen on the UI thread and
        never touch widgets from a transport thread. Returns whether discovery
        became active; a transport that reports unavailable simply stays
        inactive and the app continues as a single-node app.
        """

        if self._discovery is not None:
            LOGGER.warning("Discovery already started; ignoring duplicate start")
            return False

        def bridge(kind: str, payload: Any) -> None:
            if self._discovery is not discovery:
                return  # late transport event after stop is ignored
            generation = self._discovery_generation

            def deliver_event() -> None:
                if (
                    self._discovery is not discovery
                    or self._discovery_generation is not generation
                ):
                    return  # queued event from an old lifecycle generation
                if kind == "candidate":
                    on_candidate(payload)
                else:
                    on_lost(str(payload))

            self.post(deliver_event)

        discovery.on_event = bridge
        self._discovery = discovery
        self._discovery_generation = object()
        self._discovery_handlers = {"candidate": on_candidate, "lost": on_lost}
        if not discovery.start():
            LOGGER.warning(
                "Discovery unavailable: %s", discovery.unavailable_reason or "unknown"
            )
            # A failed transport must not reserve lifecycle ownership forever:
            # callers may retry later after the network or optional dependency
            # becomes available.
            if self._discovery is discovery:
                self._discovery = None
                self._discovery_generation = None
                self._discovery_handlers = {}
                discovery.on_event = None
            return False
        return True

    def discovery_tick(self) -> None:
        """Advance discovery TTL expiry from the application timer.

        Called on the UI thread by the window's periodic timer; any peer that
        expired is dropped and its ``lost`` event is posted through ``post``.
        """

        discovery = self._discovery
        if discovery is None:
            return
        discovery.expire_stale()

    def stop_discovery(self) -> None:
        """Stop advertising/browsing and drop all lifecycle state.

        Idempotent and safe to call during shutdown; late transport callbacks
        are ignored because the bridge is cleared first.
        """

        discovery = self._discovery
        self._discovery = None
        self._discovery_generation = None
        self._discovery_handlers = {}
        if discovery is not None:
            discovery.stop()

    @property
    def discovery(self) -> Any:
        return self._discovery
