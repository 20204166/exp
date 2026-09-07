"""Shared cadence and admission policy primitives for component work.

`ClockCoordinator` owns absolute monotonic deadlines and coalesced refresh
requests. `ResourceGovernor` owns bounded admission for background work.
Neither class starts threads or talks to Tkinter.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobProfile:
    """Describe one unit of work for admission purposes."""

    key: str
    kind: str = "periodic"
    node_id: str | None = None
    priority: int = 0
    estimated_cost: float = 1.0


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """Result of a governor admission check."""

    admitted: bool
    retry_at: float | None = None
    reason: str | None = None

    @classmethod
    def admit(cls) -> AdmissionDecision:
        return cls(True)

    @classmethod
    def defer(cls, retry_at: float, reason: str) -> AdmissionDecision:
        return cls(False, retry_at=retry_at, reason=reason)

    @classmethod
    def drop(cls, reason: str) -> AdmissionDecision:
        return cls(False, reason=reason)


@dataclass(frozen=True, slots=True)
class PressureSnapshot:
    """Best-effort pressure readings used by `ResourceGovernor`."""

    sampled_at: float
    memory_percent: float | None = None
    swap_percent: float | None = None
    rss_bytes: int | None = None
    memory_total_bytes: int | None = None
    cpu_percent: float | None = None
    degraded: bool = False
    available: bool = False
    sample_error: str | None = None


@dataclass(slots=True)
class _ClockEntry:
    interval: float
    next_due: float = 0.0
    in_flight: bool = False
    paused: bool = False
    refresh_requested: bool = False
    deferred_until: float | None = None
    missed_periods: int = 0


@dataclass(slots=True)
class _AdmissionState:
    profile: JobProfile
    admitted_at: float


class ClockCoordinator:
    """Track absolute deadlines and coalesced refresh requests."""

    def __init__(
        self,
        intervals: dict[str, float] | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._clock = clock or time.monotonic
        self._records: dict[str, _ClockEntry] = {}
        self.intervals: dict[str, float] = {}
        self._next_due: dict[str, float] = {}
        self._in_flight: set[str] = set()
        self._paused: set[str] = set()
        self._refresh_requested: set[str] = set()
        self._deferred_until: dict[str, float] = {}
        if intervals is not None:
            for key, interval in intervals.items():
                self.register(key, interval)

    def register(self, key: str, interval: float, phase: float = 0.0) -> None:
        if interval <= 0:
            raise ValueError("Interval must be positive")
        record = self._records.get(key)
        if record is None:
            record = _ClockEntry(interval=interval, next_due=max(0.0, phase))
            self._records[key] = record
        else:
            record.interval = interval
            if phase > 0.0:
                record.next_due = phase
        self.intervals[key] = interval
        self._next_due[key] = record.next_due

    def unregister(self, key: str) -> None:
        self._records.pop(key, None)
        self.intervals.pop(key, None)
        self._next_due.pop(key, None)
        self._in_flight.discard(key)
        self._paused.discard(key)
        self._refresh_requested.discard(key)
        self._deferred_until.pop(key, None)

    def update_interval(
        self, key: str, interval: float, now: float | None = None
    ) -> None:
        record = self._records.get(key)
        if record is None:
            self.register(key, interval)
            record = self._records[key]
        if interval <= 0:
            raise ValueError("Interval must be positive")
        now = self._clock() if now is None else now
        record.interval = interval
        record.next_due = now + interval
        self.intervals[key] = interval
        self._next_due[key] = record.next_due

    def begin(self, key: str, now: float, interval: float | None = None) -> bool:
        record = self._records.get(key)
        if record is None:
            if interval is None:
                interval = 5.0
            self.register(key, interval)
            record = self._records[key]
        if record.in_flight or record.paused:
            return False

        ready_at = self._ready_at(record, now)
        if ready_at is None or ready_at > now:
            return False

        record.in_flight = True
        self._in_flight.add(key)
        record.refresh_requested = False
        self._refresh_requested.discard(key)
        record.deferred_until = None
        self._deferred_until.pop(key, None)

        if now >= record.next_due:
            periods = int((now - record.next_due) // record.interval) + 1
            record.next_due += periods * record.interval
            if periods > 1:
                record.missed_periods += periods - 1
        else:
            record.next_due = now + record.interval

        self._next_due[key] = record.next_due
        return True

    def finish(self, key: str, now: float | None = None) -> None:
        record = self._records.get(key)
        if record is None:
            return
        record.in_flight = False
        self._in_flight.discard(key)
        self._next_due[key] = record.next_due
        if (
            now is not None
            and record.deferred_until is not None
            and now >= record.deferred_until
        ):
            self._deferred_until.pop(key, None)
            record.deferred_until = None

    def complete(self, key: str, now: float | None = None) -> None:
        self.finish(key, now)

    def mark_all_refreshed(self, now: float) -> None:
        for key, record in self._records.items():
            record.next_due = now + record.interval
            record.refresh_requested = False
            record.deferred_until = None
            record.missed_periods = 0
            self._next_due[key] = record.next_due
        self._refresh_requested.clear()
        self._deferred_until.clear()

    def due_keys(self, now: float) -> tuple[str, ...]:
        return tuple(
            key for key, record in self._records.items() if self._is_due(record, now)
        )

    def collect_due(self, now: float | None = None) -> tuple[str, ...]:
        now = self._clock() if now is None else now
        return self.due_keys(now)

    def next_deadline(self, now: float | None = None) -> float | None:
        now = self._clock() if now is None else now
        next_deadline: float | None = None
        for record in self._records.values():
            ready_at = self._ready_at(record, now)
            if ready_at is None:
                continue
            if next_deadline is None or ready_at < next_deadline:
                next_deadline = ready_at
        return next_deadline

    def pause(self, key: str) -> None:
        record = self._record_or_raise(key)
        record.paused = True
        self._paused.add(key)

    def resume(self, key: str) -> None:
        record = self._record_or_raise(key)
        record.paused = False
        self._paused.discard(key)

    def cancel(self, key: str) -> None:
        record = self._record_or_raise(key)
        record.in_flight = False
        record.refresh_requested = False
        record.deferred_until = None
        self._in_flight.discard(key)
        self._refresh_requested.discard(key)
        self._deferred_until.pop(key, None)

    def is_paused(self, key: str) -> bool:
        return key in self._paused

    def request_refresh(self, key: str) -> None:
        record = self._record_or_raise(key)
        record.refresh_requested = True
        self._refresh_requested.add(key)

    def defer(self, key: str, retry_at: float) -> None:
        record = self._record_or_raise(key)
        current = self._deferred_until.get(key)
        if current is None or retry_at > current:
            self._deferred_until[key] = retry_at
            record.deferred_until = retry_at

    def state(self, key: str) -> _ClockEntry:
        return self._record_or_raise(key)

    def _record_or_raise(self, key: str) -> _ClockEntry:
        try:
            return self._records[key]
        except KeyError as error:
            raise ValueError(f"Unknown component: {key}") from error

    def _ready_at(self, record: _ClockEntry, now: float) -> float | None:
        if record.paused or record.in_flight:
            return None
        ready_at = record.next_due
        if record.refresh_requested:
            ready_at = min(ready_at, now)
        if record.deferred_until is not None:
            ready_at = max(ready_at, record.deferred_until)
        return ready_at

    def _is_due(self, record: _ClockEntry, now: float) -> bool:
        ready_at = self._ready_at(record, now)
        return ready_at is not None and ready_at <= now


class ResourceGovernor:
    """Bounded admission policy for background work."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        max_active: int = 4,
        max_periodic: int = 2,
        max_per_node: int = 2,
        manual_reserve: int = 1,
        retry_base_seconds: float = 0.25,
        retry_cap_seconds: float = 5.0,
        pressure_sample_seconds: float = 0.5,
        memory_enter_percent: float = 92.0,
        memory_leave_percent: float = 85.0,
        swap_enter_percent: float = 10.0,
        swap_leave_percent: float = 5.0,
        rss_enter_fraction: float = 0.75,
        rss_leave_fraction: float = 0.65,
        pressure_sampler: Callable[[], PressureSnapshot] | None = None,
    ) -> None:
        self._clock = clock or time.monotonic
        self.max_active = max_active
        self.max_periodic = max_periodic
        self.max_per_node = max_per_node
        self.manual_reserve = manual_reserve
        self.retry_base_seconds = retry_base_seconds
        self.retry_cap_seconds = retry_cap_seconds
        self.pressure_sample_seconds = pressure_sample_seconds
        self.memory_enter_percent = memory_enter_percent
        self.memory_leave_percent = memory_leave_percent
        self.swap_enter_percent = swap_enter_percent
        self.swap_leave_percent = swap_leave_percent
        self.rss_enter_fraction = rss_enter_fraction
        self.rss_leave_fraction = rss_leave_fraction
        self._pressure_sampler = pressure_sampler or self._default_pressure_sampler
        self._pressure_lock = threading.Lock()
        self._pressure_sampling = False
        self._active: dict[str, _AdmissionState] = {}
        self._active_by_node: dict[str, int] = {}
        self._active_periodic = 0
        self._defer_counts: dict[str, int] = {}
        self._pressure = PressureSnapshot(sampled_at=self._clock(), available=False)
        self._pressure_degraded = False
        self._last_pressure_sample = float("-inf")

    @property
    def pressure(self) -> PressureSnapshot:
        with self._pressure_lock:
            return self._pressure

    def admit(self, profile: JobProfile, now: float | None = None) -> AdmissionDecision:
        now = self._clock() if now is None else now
        pressure = self.sample_pressure(now)

        if profile.key in self._active:
            return self._defer(profile, now, "already running")

        if profile.kind != "manual" and pressure.degraded:
            return self._defer(profile, now, "resource pressure")

        if self._active_total() >= self.max_active:
            return self._defer(profile, now, "capacity exhausted")

        if profile.kind == "manual":
            if self._active_total() >= self.max_active:
                return self._defer(profile, now, "manual capacity exhausted")
        else:
            background_limit = max(0, self.max_active - self.manual_reserve)
            if self._active_total() >= background_limit:
                return self._defer(profile, now, "background capacity exhausted")
            if self._active_periodic >= self.max_periodic:
                return self._defer(profile, now, "periodic capacity exhausted")

        if (
            profile.node_id is not None
            and self._active_by_node.get(
                profile.node_id,
                0,
            )
            >= self.max_per_node
        ):
            return self._defer(profile, now, "node capacity exhausted")

        self._active[profile.key] = _AdmissionState(profile=profile, admitted_at=now)
        self._active_by_node[profile.node_id or ""] = (
            self._active_by_node.get(profile.node_id or "", 0) + 1
        )
        if profile.kind != "manual":
            self._active_periodic += 1
        self._defer_counts.pop(profile.key, None)
        return AdmissionDecision.admit()

    def release(self, key: str) -> None:
        state = self._active.pop(key, None)
        if state is None:
            return
        node_key = state.profile.node_id or ""
        count = self._active_by_node.get(node_key, 0)
        if count <= 1:
            self._active_by_node.pop(node_key, None)
        else:
            self._active_by_node[node_key] = count - 1
        if state.profile.kind != "manual":
            self._active_periodic = max(0, self._active_periodic - 1)
        self._defer_counts.pop(key, None)

    def sample_pressure(self, now: float | None = None) -> PressureSnapshot:
        now = self._clock() if now is None else now
        self.request_pressure_sample(now)
        return self.pressure

    def refresh_pressure(self, now: float | None = None) -> PressureSnapshot:
        now = self._clock() if now is None else now
        return self._apply_pressure_snapshot(self._collect_pressure_snapshot(now))

    def request_pressure_sample(self, now: float | None = None) -> bool:
        now = self._clock() if now is None else now
        with self._pressure_lock:
            if self._pressure_sampling:
                return False
            if now - self._last_pressure_sample < self.pressure_sample_seconds:
                return False
            self._pressure_sampling = True

        threading.Thread(target=self._pressure_sample_worker, daemon=True).start()
        return True

    def _pressure_sample_worker(self) -> None:
        try:
            self._apply_pressure_snapshot(self._collect_pressure_snapshot())
        finally:
            with self._pressure_lock:
                self._pressure_sampling = False

    def _collect_pressure_snapshot(self, now: float | None = None) -> PressureSnapshot:
        now = self._clock() if now is None else now
        try:
            snapshot = self._pressure_sampler()
        except Exception as error:  # noqa: BLE001 - psutil sampling is best-effort.
            return PressureSnapshot(
                sampled_at=now,
                memory_percent=None,
                swap_percent=None,
                rss_bytes=None,
                memory_total_bytes=None,
                cpu_percent=None,
                degraded=self._pressure_degraded,
                available=False,
                sample_error=str(error),
            )

        if snapshot.sampled_at <= 0:
            snapshot = PressureSnapshot(
                sampled_at=now,
                memory_percent=snapshot.memory_percent,
                swap_percent=snapshot.swap_percent,
                rss_bytes=snapshot.rss_bytes,
                memory_total_bytes=snapshot.memory_total_bytes,
                cpu_percent=snapshot.cpu_percent,
                degraded=snapshot.degraded,
                available=snapshot.available,
                sample_error=snapshot.sample_error,
            )
        return snapshot

    def _default_pressure_sampler(self) -> PressureSnapshot:
        now = self._clock()

        memory_percent: float | None = None
        swap_percent: float | None = None
        rss_bytes: int | None = None
        memory_total_bytes: int | None = None
        cpu_percent: float | None = None

        try:
            import psutil  # type: ignore[import-not-found]
        except Exception as error:  # noqa: BLE001 - psutil sampling is best-effort.
            return PressureSnapshot(
                sampled_at=now,
                memory_percent=None,
                swap_percent=None,
                rss_bytes=None,
                memory_total_bytes=None,
                cpu_percent=None,
                degraded=self._pressure_degraded,
                available=False,
                sample_error=str(error),
            )

        try:
            memory = psutil.virtual_memory()
            memory_percent = float(memory.percent)
            memory_total_bytes = int(memory.total)
        except Exception:  # noqa: BLE001 - psutil sampling is best-effort.
            memory_percent = None
            memory_total_bytes = None

        try:
            swap_percent = float(psutil.swap_memory().percent)
        except Exception:  # noqa: BLE001 - psutil sampling is best-effort.
            swap_percent = None

        try:
            rss_bytes = int(psutil.Process().memory_info().rss)
        except Exception:  # noqa: BLE001 - psutil sampling is best-effort.
            rss_bytes = None

        try:
            cpu_percent = float(psutil.cpu_percent(interval=None))
        except Exception:  # noqa: BLE001 - psutil sampling is best-effort.
            cpu_percent = None

        return PressureSnapshot(
            sampled_at=now,
            memory_percent=memory_percent,
            swap_percent=swap_percent,
            rss_bytes=rss_bytes,
            memory_total_bytes=memory_total_bytes,
            cpu_percent=cpu_percent,
            degraded=self._pressure_degraded,
            available=True,
        )

    def _apply_pressure_snapshot(self, snapshot: PressureSnapshot) -> PressureSnapshot:
        with self._pressure_lock:
            degraded = self._pressure_degraded
            if snapshot.available:
                if degraded:
                    if self._pressure_relaxed(
                        snapshot.memory_percent,
                        snapshot.swap_percent,
                        snapshot.rss_bytes,
                        snapshot.memory_total_bytes,
                    ):
                        degraded = False
                elif self._pressure_entered(
                    snapshot.memory_percent,
                    snapshot.swap_percent,
                    snapshot.rss_bytes,
                    snapshot.memory_total_bytes,
                ):
                    degraded = True

            self._pressure_degraded = degraded
            self._pressure = PressureSnapshot(
                sampled_at=snapshot.sampled_at,
                memory_percent=snapshot.memory_percent,
                swap_percent=snapshot.swap_percent,
                rss_bytes=snapshot.rss_bytes,
                memory_total_bytes=snapshot.memory_total_bytes,
                cpu_percent=snapshot.cpu_percent,
                degraded=degraded,
                available=snapshot.available,
                sample_error=snapshot.sample_error,
            )
            self._last_pressure_sample = snapshot.sampled_at
            return self._pressure

    def _pressure_entered(
        self,
        memory_percent: float | None,
        swap_percent: float | None,
        rss_bytes: int | None,
        memory_total_bytes: int | None,
    ) -> bool:
        if memory_percent is not None and memory_percent >= self.memory_enter_percent:
            return True
        if swap_percent is not None and swap_percent >= self.swap_enter_percent:
            return True
        if rss_bytes is not None and memory_total_bytes:
            return (rss_bytes / float(memory_total_bytes)) >= self.rss_enter_fraction
        return False

    def _pressure_relaxed(
        self,
        memory_percent: float | None,
        swap_percent: float | None,
        rss_bytes: int | None,
        memory_total_bytes: int | None,
    ) -> bool:
        seen = False
        if memory_percent is not None and memory_percent >= self.memory_leave_percent:
            return False
        if memory_percent is not None:
            seen = True
        if swap_percent is not None and swap_percent >= self.swap_leave_percent:
            return False
        if swap_percent is not None:
            seen = True
        if rss_bytes is not None and memory_total_bytes:
            if (rss_bytes / float(memory_total_bytes)) >= self.rss_leave_fraction:
                return False
            seen = True
        return seen

    def _active_total(self) -> int:
        return len(self._active)

    def _defer(self, profile: JobProfile, now: float, reason: str) -> AdmissionDecision:
        count = self._defer_counts.get(profile.key, 0) + 1
        self._defer_counts[profile.key] = count
        delay = min(
            self.retry_cap_seconds, self.retry_base_seconds * (2 ** min(count, 5))
        )
        return AdmissionDecision.defer(now + delay, reason)
