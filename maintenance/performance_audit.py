"""Immutable data contracts for scanner performance audit evidence."""

from __future__ import annotations

import statistics
import time
import tracemalloc
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Literal

from maintenance.components.catalog import ResourceFeatureCatalog

Evidence = Literal["native", "simulated", "unavailable"]
MeasurementState = Literal["cold", "warm"]
FindingStatus = Literal["confirmed", "noise", "not actionable", "requires design"]


@dataclass(frozen=True, slots=True)
class OperationTiming:
    """One operation result with scanner/coordinator attribution."""

    value: object
    total_seconds: float
    scanner_seconds: float
    coordinator_seconds: float
    cpu_seconds: float
    peak_memory_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class CoordinationMetrics:
    """Deterministic coordination evidence, separate from timing records."""

    platform: str
    evidence: Evidence
    callback_delivery_count: int
    duplicate_task_starts: int
    hidden_work_starts: int
    visible_refresh_latency_seconds: float
    burst_render_count: int
    event_count: int
    rendered_update_count: int
    provenance: str = (
        "Fixed deterministic queue/render fixture; does not measure a native path."
    )

    def __post_init__(self) -> None:
        _require_non_empty(self.platform, "platform")
        if self.evidence not in ("native", "simulated", "unavailable"):
            raise ValueError(f"invalid evidence: {self.evidence}")
        for name in (
            "callback_delivery_count",
            "duplicate_task_starts",
            "hidden_work_starts",
            "burst_render_count",
            "event_count",
            "rendered_update_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.visible_refresh_latency_seconds < 0:
            raise ValueError("visible_refresh_latency_seconds cannot be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "evidence": self.evidence,
            "callback_delivery_count": self.callback_delivery_count,
            "duplicate_task_starts": self.duplicate_task_starts,
            "hidden_work_starts": self.hidden_work_starts,
            "visible_refresh_latency_seconds": self.visible_refresh_latency_seconds,
            "burst_render_count": self.burst_render_count,
            "event_count": self.event_count,
            "rendered_update_count": self.rendered_update_count,
            "provenance": self.provenance,
        }


def deterministic_coordination_metrics(
    *, platform: str, evidence: Evidence
) -> CoordinationMetrics:
    """Return fixed coordination scenarios without making platform claims.

    The fake queue receives five callbacks and five discovery events, while
    keyed delivery and burst presentation each render only the latest state.
    The latency uses a fixed fake-clock interval rather than host time.
    """

    pending_callbacks = list(range(5))
    callback_delivery_count = len(pending_callbacks[-1:])

    task_in_flight = False
    task_starts = 0
    for _ in range(3):
        if task_in_flight:
            continue
        else:
            task_in_flight = True
            task_starts += 1

    hidden_work_starts = 0
    fake_clock = iter((10.0, 10.125))
    visible_refresh_latency_seconds = next(fake_clock)
    visible_refresh_latency_seconds = next(fake_clock) - visible_refresh_latency_seconds
    event_count = 5
    burst_render_count = len((event_count,)[-1:])

    coordination_evidence: Evidence = "simulated" if evidence == "native" else evidence
    return CoordinationMetrics(
        platform=platform,
        evidence=coordination_evidence,
        callback_delivery_count=callback_delivery_count,
        duplicate_task_starts=max(task_starts - 1, 0),
        hidden_work_starts=hidden_work_starts,
        visible_refresh_latency_seconds=visible_refresh_latency_seconds,
        burst_render_count=burst_render_count,
        event_count=event_count,
        rendered_update_count=burst_render_count,
    )


def _percentile(ordered: list[float], fraction: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def summarize_samples(samples: tuple[float, ...]) -> dict[str, float | int]:
    """Return robust distribution statistics for one measured sample set."""

    if not samples:
        raise ValueError("at least one sample is required")
    ordered = sorted(samples)
    lower = ordered[0]
    upper = ordered[-1]
    spread = upper - lower
    p25 = _percentile(ordered, 0.25)
    p75 = _percentile(ordered, 0.75)
    outlier_ceiling = p75 + 1.5 * (p75 - p25)
    return {
        "minimum": lower,
        "p25": p25,
        "median": statistics.median(ordered),
        "p75": p75,
        "p95": _percentile(ordered, 0.95),
        "maximum": upper,
        "spread": spread,
        "outliers": sum(value > outlier_ceiling for value in ordered),
    }


def interleave_modes(modes: tuple[str, ...], repetitions: int) -> Iterator[str]:
    """Yield each mode once per round to reduce temporal benchmark bias."""

    if not modes:
        raise ValueError("at least one mode is required")
    if repetitions <= 0:
        raise ValueError("repetitions must be positive")
    for _ in range(repetitions):
        yield from modes


class AuditRunner:
    """Measure injected operations without owning application state."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.perf_counter,
        cpu_clock: Callable[[], float] = time.process_time,
        include_memory: bool = False,
    ) -> None:
        self._clock = clock
        self._cpu_clock = cpu_clock
        self._include_memory = include_memory

    def measure(
        self,
        operation: Callable[[], object],
        *,
        split_timing: Callable[[object], tuple[float, float]] | None = None,
    ) -> OperationTiming:
        started = self._clock()
        cpu_started = self._cpu_clock()
        if self._include_memory:
            tracemalloc.start()
        value = operation()
        total_seconds = self._clock() - started
        cpu_seconds = self._cpu_clock() - cpu_started
        peak_memory_bytes: int | None = None
        if self._include_memory:
            _, peak_memory_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        scanner_seconds, coordinator_seconds = (
            split_timing(value) if split_timing is not None else (total_seconds, 0.0)
        )
        return OperationTiming(
            value=value,
            total_seconds=total_seconds,
            scanner_seconds=scanner_seconds,
            coordinator_seconds=coordinator_seconds,
            cpu_seconds=cpu_seconds,
            peak_memory_bytes=peak_memory_bytes,
        )

    def run_interleaved(
        self,
        operations: Mapping[str, Callable[[], object]],
        repetitions: int,
    ) -> dict[str, tuple[OperationTiming, ...]]:
        """Measure each operation in alternating rounds."""

        if not operations:
            raise ValueError("at least one operation is required")
        results: dict[str, list[OperationTiming]] = {name: [] for name in operations}
        for name in interleave_modes(tuple(operations), repetitions):
            results[name].append(self.measure(operations[name]))
        return {name: tuple(values) for name, values in results.items()}


def default_workloads() -> tuple[WorkloadSpec, ...]:
    """Return the complete scanner/coordinator workload matrix."""

    scenarios = ("cold", "warm", "failure", "cancelled", "timeout")
    component_workloads = tuple(
        WorkloadSpec(f"component:{feature.key}", scenarios, feature.title)
        for feature in ResourceFeatureCatalog().all()
    )
    return (
        WorkloadSpec("dashboard", scenarios, "Full dashboard refresh"),
        *component_workloads,
        WorkloadSpec("gpu-telemetry", scenarios, "GPU and temperature telemetry"),
        WorkloadSpec("temperature-telemetry", scenarios, "Temperature telemetry state"),
        WorkloadSpec("network-discovery", scenarios, "Network discovery lifecycle"),
        WorkloadSpec("downloads", scenarios, "Downloads scan and hashing"),
        WorkloadSpec("processes", scenarios, "Process scan"),
        WorkloadSpec("background-delivery", scenarios, "Background task delivery"),
        WorkloadSpec("app-coordinator", scenarios, "Coordinator lifecycle"),
    )


def report_payload(
    records: tuple[MeasurementRecord, ...],
    findings: tuple[CandidateFinding, ...],
    coordination: CoordinationMetrics | None = None,
) -> dict[str, object]:
    """Build the stable machine-readable report envelope."""

    return {
        "records": [record.to_dict() for record in records],
        "findings": [finding.to_dict() for finding in findings],
        "workloads": [workload.to_dict() for workload in default_workloads()],
        "coordination_metrics": (
            coordination.to_dict() if coordination is not None else None
        ),
    }


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} is required")


@dataclass(frozen=True, slots=True)
class WorkloadSpec:
    """A named audit workload and the scenarios it must exercise."""

    key: str
    scenarios: tuple[str, ...]
    description: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.key, "workload key")
        if not self.scenarios or any(
            not scenario.strip() for scenario in self.scenarios
        ):
            raise ValueError("at least one required scenario is required")

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "scenarios": list(self.scenarios),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ResourceCounters:
    """Resource measurements attributable to one audit record."""

    cpu_seconds: float = 0.0
    peak_memory_bytes: int | None = None
    allocations: int | None = None
    io_read_bytes: int | None = None
    io_write_bytes: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "cpu_seconds": self.cpu_seconds,
            "peak_memory_bytes": self.peak_memory_bytes,
            "allocations": self.allocations,
            "io_read_bytes": self.io_read_bytes,
            "io_write_bytes": self.io_write_bytes,
        }


@dataclass(frozen=True, slots=True)
class MeasurementRecord:
    """One workload observation, including scanner/coordinator attribution."""

    workload: str
    scenario: str
    platform: str
    evidence: Evidence
    state: MeasurementState
    samples: tuple[float, ...]
    resources: ResourceCounters
    error_classification: str | None = None
    scanner_seconds: tuple[float, ...] = ()
    coordinator_seconds: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.workload, "workload")
        _require_non_empty(self.scenario, "scenario")
        _require_non_empty(self.platform, "platform")
        if self.evidence not in ("native", "simulated", "unavailable"):
            raise ValueError(f"invalid evidence: {self.evidence}")
        if self.state not in ("cold", "warm"):
            raise ValueError(f"invalid measurement state: {self.state}")

    def to_dict(self) -> dict[str, object]:
        return {
            "workload": self.workload,
            "scenario": self.scenario,
            "platform": self.platform,
            "evidence": self.evidence,
            "state": self.state,
            "samples": list(self.samples),
            "resources": self.resources.to_dict(),
            "error_classification": self.error_classification,
            "scanner_seconds": list(self.scanner_seconds),
            "coordinator_seconds": list(self.coordinator_seconds),
        }


@dataclass(frozen=True, slots=True)
class CandidateFinding:
    """A ranked audit candidate and its evidence-based disposition."""

    workload: str
    candidate: str
    status: FindingStatus
    rationale: str
    operation: str = ""
    median_seconds: float | None = None
    p95_seconds: float | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.workload, "workload")
        _require_non_empty(self.candidate, "candidate")
        if self.status not in (
            "confirmed",
            "noise",
            "not actionable",
            "requires design",
        ):
            raise ValueError(f"invalid finding status: {self.status}")

    def to_dict(self) -> dict[str, object]:
        return {
            "workload": self.workload,
            "candidate": self.candidate,
            "status": self.status,
            "rationale": self.rationale,
            "operation": self.operation,
            "median_seconds": self.median_seconds,
            "p95_seconds": self.p95_seconds,
        }
