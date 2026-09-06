"""Live scan-state coordination for the dashboard window.

Includes the dashboard ``ScanCoordinator``, the per-component refresh
``ComponentRefreshScheduler``, and the universal ``AppCoordinator`` — the
single "shock absorber" between slow background work (scans, page loads)
and the Tkinter UI thread.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)


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


class ComponentRefreshScheduler:
    """Track per-component refresh due times and prevent overlapping scans.

    Each component has its own interval and in-flight flag, so a slow or
    failing component never delays the others and the same component is never
    scanned twice concurrently.
    """

    def __init__(self, intervals: dict[str, int] | None = None) -> None:
        self.intervals = (
            dict(intervals) if intervals is not None else RefreshIntervals().as_dict()
        )
        self._next_due: dict[str, float] = {}
        self._in_flight: set[str] = set()
        self._paused: set[str] = set()
        self._refresh_requested: set[str] = set()

    def begin(self, key: str, now: float) -> bool:
        """Claim a component scan if it is due and not already running."""

        if key in self._in_flight:
            return False
        if key in self._paused:
            return False
        if key not in self._refresh_requested and now < self._next_due.get(key, 0.0):
            return False
        self._in_flight.add(key)
        self._refresh_requested.discard(key)
        self._next_due[key] = now + self.intervals.get(key, 5000) / 1000.0
        return True

    def finish(self, key: str) -> None:
        self._in_flight.discard(key)

    def mark_all_refreshed(self, now: float) -> None:
        """Push every component's next due time past its interval.

        Called after a full snapshot so the scheduler does not immediately
        re-scan every component, and so a queued refresh request is satisfied
        by the snapshot rather than launching another scan.
        """

        for key in self.intervals:
            self._next_due[key] = now + self.intervals[key] / 1000.0
        self._refresh_requested.clear()

    def due_keys(self, now: float) -> tuple[str, ...]:
        """Return the keys that are due now and not already running."""

        return tuple(
            key
            for key in self.intervals
            if key not in self._in_flight
            and key not in self._paused
            and (key in self._refresh_requested or now >= self._next_due.get(key, 0.0))
        )

    def in_flight(self, key: str) -> bool:
        return key in self._in_flight

    def set_interval(self, key: str, milliseconds: int, now: float) -> None:
        """Change one component's refresh interval and reset its deadline.

        Only the named component is touched: its next due time is pushed out
        by the new interval from ``now`` and any in-flight scan is preserved.
        This never launches a worker itself.
        """

        if key not in self.intervals:
            raise ValueError(f"Unknown component: {key}")
        if not isinstance(milliseconds, int) or isinstance(milliseconds, bool):
            raise TypeError("Interval must be an integer number of milliseconds")
        if milliseconds <= 0:
            raise ValueError("Interval must be positive")
        self.intervals[key] = milliseconds
        self._next_due[key] = now + milliseconds / 1000.0

    def pause(self, key: str) -> None:
        """Prevent new scans of a component without disturbing a running one."""

        if key not in self.intervals:
            raise ValueError(f"Unknown component: {key}")
        self._paused.add(key)

    def resume(self, key: str) -> None:
        """Allow a paused component to be scanned again."""

        if key not in self.intervals:
            raise ValueError(f"Unknown component: {key}")
        self._paused.discard(key)

    def is_paused(self, key: str) -> bool:
        return key in self._paused

    def request_refresh(self, key: str) -> None:
        """Queue one coalesced immediate refresh for a component.

        Repeated requests collapse into one. A request made while the
        component is in flight or paused becomes due as soon as the worker
        finishes or the component is resumed, without ever overlapping.
        """

        if key not in self.intervals:
            raise ValueError(f"Unknown component: {key}")
        self._refresh_requested.add(key)


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
        """Clear the active state without scheduling another scan."""

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
    task_factory: Callable[..., Any] | None = None


def _default_runner(worker: Callable[[], None]) -> None:
    threading.Thread(target=worker, daemon=True).start()


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
        self._runner = runner or _default_runner
        self._deliver = deliver or (lambda callback: callback())
        self._on_activity = on_activity
        self._states: dict[str, AppRunState] = {}

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
        if rerun_requested:
            self._replay(key, state)

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
