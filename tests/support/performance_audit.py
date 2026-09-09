"""Deterministic scanner and coordinator fixtures for performance-audit tests."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from maintenance.components.coordinator import AppCoordinator

FailureKind = Literal[
    "missing dependency",
    "permission failure",
    "subprocess failure",
    "timeout",
]


@dataclass(frozen=True, slots=True)
class PlatformEvidence:
    """Stable provenance labels used by deterministic workload fixtures."""

    platform: str
    evidence: Literal["native", "simulated", "unavailable"]
    available: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "evidence": self.evidence,
            "available": self.available,
        }


NATIVE_PLATFORM = PlatformEvidence("Linux-x86_64", "native")
SIMULATED_PLATFORM = PlatformEvidence("Windows-x86_64", "simulated")
UNAVAILABLE_PLATFORM = PlatformEvidence("Darwin-arm64", "unavailable", False)


@dataclass(frozen=True, slots=True)
class FixtureProfile:
    """Fixed-size scanner input; profiles contain no host-dependent values."""

    name: str
    items: tuple[str, ...]

    @property
    def size(self) -> int:
        return len(self.items)


EMPTY_PROFILE = FixtureProfile("empty", ())
TYPICAL_PROFILE = FixtureProfile("typical", ("cpu", "memory", "network"))
LARGE_PROFILE = FixtureProfile(
    "large", tuple(f"component-{index:04d}" for index in range(1000))
)


@dataclass(slots=True)
class AuditCounters:
    """Observable calls for one fresh fake environment."""

    probe_calls: int = 0
    cache_hits: int = 0
    cancellation_calls: int = 0
    retries: int = 0
    deliveries: int = 0
    late_results: int = 0
    runs: int = 0


class FakeScanner:
    """Scanner with a stable result contract and injectable failure outcome."""

    def __init__(
        self,
        profile: FixtureProfile,
        *,
        counters: AuditCounters,
        failure: FailureKind | None = None,
    ) -> None:
        self.profile = profile
        self.counters = counters
        self.failure = failure
        self._cache: dict[str, dict[str, object]] = {}

    def probe_optional_dependency(self, available: bool = True) -> bool:
        self.counters.probe_calls += 1
        return available

    def scan(
        self,
        cancel_event: threading.Event | None = None,
        *,
        use_cache: bool = False,
    ) -> dict[str, object]:
        if use_cache and self.profile.name in self._cache:
            self.counters.cache_hits += 1
            return dict(self._cache[self.profile.name])
        if cancel_event is not None and cancel_event.is_set():
            result = self._failure_result("cancellation")
        elif self.failure is not None:
            result = self._failure_result(self.failure)
        else:
            result = {
                "status": "ok",
                "profile": self.profile.name,
                "items": list(self.profile.items),
                "count": self.profile.size,
                "error_classification": None,
            }
        if result["status"] == "ok":
            self._cache[self.profile.name] = dict(result)
        return result

    def _failure_result(self, classification: str) -> dict[str, object]:
        return {
            "status": "failure",
            "profile": self.profile.name,
            "items": [],
            "count": 0,
            "error_classification": classification,
        }


class FakeCoordinator:
    """A manually stepped ``AppCoordinator`` with queued UI delivery."""

    def __init__(self, counters: AuditCounters) -> None:
        self.counters = counters
        self.workers: list[Callable[[], None]] = []
        self.deliveries: list[Callable[[], None]] = []
        self.closed = False
        self._coordinator = AppCoordinator(
            runner=self._queue_worker,
            deliver=self._queue_delivery,
        )

    def _queue_worker(self, worker: Callable[[], None]) -> None:
        if self.counters.runs:
            self.counters.retries += 1
        self.counters.runs += 1
        self.workers.append(worker)

    def _queue_delivery(self, callback: Callable[[], None]) -> None:
        if self.closed:
            self.counters.late_results += 1
        else:
            self.deliveries.append(callback)

    def run(self, key: str, task: Callable[[threading.Event], Any]) -> int | None:
        def task_factory(
            event: threading.Event, _progress: Callable[[str], None]
        ) -> Any:
            return task(event)

        return self._coordinator.run(key, task_factory)

    def cancel(self, key: str) -> None:
        self.counters.cancellation_calls += 1
        self._coordinator.cancel(key)

    def run_worker(self) -> None:
        self.workers.pop(0)()

    def deliver(self) -> None:
        callback = self.deliveries.pop(0)
        if self.closed:
            self.counters.late_results += 1
            return
        self.counters.deliveries += 1
        callback()

    def shutdown(self) -> None:
        self.closed = True
        self._coordinator.shutdown()

    def generation(self, key: str) -> int:
        return self._coordinator.generation(key)

    def in_flight(self, key: str) -> bool:
        return self._coordinator.in_flight(key)

    def finish(self, key: str, generation: int, result: Any) -> bool:
        finished, _rerun = self._coordinator.finish(key, generation, result)
        return finished


def make_fake_scanner(
    profile: FixtureProfile = TYPICAL_PROFILE,
    *,
    failure: FailureKind | None = None,
    counters: AuditCounters | None = None,
) -> FakeScanner:
    """Create a scanner with isolated counters unless shared explicitly."""

    return FakeScanner(
        profile,
        counters=counters if counters is not None else AuditCounters(),
        failure=failure,
    )


def make_fake_coordinator(counters: AuditCounters | None = None) -> FakeCoordinator:
    """Create a coordinator with an isolated delivery queue and counters."""

    return FakeCoordinator(counters if counters is not None else AuditCounters())


def make_performance_fixtures(
    profile: FixtureProfile = TYPICAL_PROFILE,
    *,
    failure: FailureKind | None = None,
) -> tuple[FakeScanner, FakeCoordinator, AuditCounters]:
    """Create a completely fresh scanner/coordinator/counter trio."""

    counters = AuditCounters()
    return (
        make_fake_scanner(profile, failure=failure, counters=counters),
        make_fake_coordinator(counters),
        counters,
    )


def classify_result(result: dict[str, object]) -> str:
    """Return the audit-facing classification without changing result payloads."""

    return str(result["error_classification"] or "success")
