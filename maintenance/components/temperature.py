"""Shared thermal telemetry primitives for component scans and detail views."""

from __future__ import annotations

import re
import statistics
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar

from maintenance.models import CapabilityState, ResourceSummary

_DETAIL_TEMPERATURE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)°C")


class TemperatureState(str, Enum):
    VALID = "valid"
    NO_DATA = "no_data"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TemperatureSample:
    component: str
    sensor_id: str
    sensor_name: str
    value_celsius: float
    sampled_at: datetime
    sampled_monotonic: float


@dataclass(frozen=True, slots=True)
class TemperaturePolicy:
    warning_celsius: float | None = 90.0
    critical_celsius: float | None = 95.0
    recovery_celsius: float | None = 85.0
    consecutive_samples: int = 2
    cooldown_seconds: float = 30.0
    pre_event_samples: int = 4
    post_event_samples: int = 4
    rapid_rise_celsius: float | None = 12.0
    rapid_rise_window: int = 4
    history_limit: int = 600
    event_limit: int = 8


@dataclass(frozen=True, slots=True)
class TemperatureEvent:
    component: str
    sensor_id: str
    sensor_name: str
    started_at: datetime
    started_monotonic: float
    peak_celsius: float
    baseline_celsius: float
    severity: str
    samples: tuple[TemperatureSample, ...]
    ended_at: datetime | None = None
    ended_monotonic: float | None = None

    def summary(self) -> str:
        return (
            f"{self.sensor_name} peaked at {self.peak_celsius:.0f}°C"
            if self.sensor_name
            else f"{self.component.upper()} peaked at {self.peak_celsius:.0f}°C"
        )

    def snapshot(self, *, title: str | None = None) -> TemperatureSeriesSnapshot:
        samples = self.samples
        values = [sample.value_celsius for sample in samples]
        return TemperatureSeriesSnapshot(
            component=self.component,
            title=title or self.component.upper(),
            state=TemperatureState.VALID,
            current_celsius=values[-1] if values else None,
            minimum_celsius=min(values) if values else None,
            maximum_celsius=max(values) if values else None,
            warning_celsius=None,
            critical_celsius=None,
            samples=samples,
            events=(),
            severity=self.severity,
        )


@dataclass(frozen=True, slots=True)
class TemperatureSeriesSnapshot:
    component: str
    title: str
    state: TemperatureState
    current_celsius: float | None
    minimum_celsius: float | None
    maximum_celsius: float | None
    warning_celsius: float | None
    critical_celsius: float | None
    samples: tuple[TemperatureSample, ...]
    events: tuple[TemperatureEvent, ...]
    severity: str = "normal"


@dataclass(frozen=True, slots=True)
class TemperatureScan:
    captured_at: datetime
    captured_monotonic: float
    lines: tuple[str, ...]
    samples_by_component: tuple[tuple[str, tuple[TemperatureSample, ...]], ...]

    def samples_for(self, component: str) -> tuple[TemperatureSample, ...]:
        for key, samples in self.samples_by_component:
            if key == component:
                return samples
        return ()


@dataclass(slots=True)
class _ComponentTelemetry:
    policy: TemperaturePolicy
    state: TemperatureState = TemperatureState.NO_DATA
    current: TemperatureSample | None = None
    history: deque[TemperatureSample] = None  # type: ignore[assignment]
    sensor_histories: dict[str, deque[TemperatureSample]] = None  # type: ignore[assignment]
    events: deque[TemperatureEvent] = None  # type: ignore[assignment]
    active_event: dict[str, Any] | None = None
    last_error: str | None = None
    consecutive_hot: int = 0
    cooldown_until: float = 0.0

    def __post_init__(self) -> None:
        self.history = deque(maxlen=self.policy.history_limit)
        self.sensor_histories = {}
        self.events = deque(maxlen=self.policy.event_limit)


class TemperatureTelemetry:
    """Bounded in-memory thermal telemetry for one node."""

    DEFAULT_POLICIES: ClassVar[dict[str, TemperaturePolicy]] = {
        "cpu": TemperaturePolicy(),
        "gpu": TemperaturePolicy(),
        "storage": TemperaturePolicy(),
        "battery": TemperaturePolicy(
            warning_celsius=None, critical_celsius=None, rapid_rise_celsius=None
        ),
    }

    def __init__(self, *, policies: dict[str, TemperaturePolicy] | None = None) -> None:
        self._policies = dict(self.DEFAULT_POLICIES)
        if policies is not None:
            self._policies.update(policies)
        self._components: dict[str, _ComponentTelemetry] = {}

    def policy_for(self, component: str) -> TemperaturePolicy:
        return self._policies.get(component, TemperaturePolicy())

    def record_summary(self, component: str, summary: ResourceSummary) -> None:
        component = component.casefold()
        telemetry = self._component(component)
        telemetry.last_error = None
        samples = tuple(summary.temperatures)
        if not samples:
            samples = self._legacy_samples(component, summary)

        if samples:
            self._record_samples(telemetry, samples)
            telemetry.state = TemperatureState.VALID
            telemetry.current = samples[-1]
            return

        if summary.capability == CapabilityState.UNSUPPORTED:
            telemetry.state = TemperatureState.UNSUPPORTED
        elif summary.failed:
            telemetry.state = TemperatureState.ERROR
        else:
            telemetry.state = TemperatureState.NO_DATA

    def series_snapshot(
        self, component: str, *, title: str | None = None
    ) -> TemperatureSeriesSnapshot:
        component = component.casefold()
        telemetry = self._component(component)
        self._prune_component(telemetry)
        values = [sample.value_celsius for sample in telemetry.history]
        policy = telemetry.policy
        return TemperatureSeriesSnapshot(
            component=component,
            title=title or component.upper(),
            state=telemetry.state,
            current_celsius=telemetry.current.value_celsius
            if telemetry.current
            else None,
            minimum_celsius=min(values) if values else None,
            maximum_celsius=max(values) if values else None,
            warning_celsius=policy.warning_celsius,
            critical_celsius=policy.critical_celsius,
            samples=tuple(telemetry.history),
            events=tuple(telemetry.events),
            severity=self._severity_for(telemetry, values),
        )

    def recent_events(self, component: str) -> tuple[TemperatureEvent, ...]:
        return tuple(self._component(component.casefold()).events)

    def history(self, component: str) -> tuple[TemperatureSample, ...]:
        telemetry = self._component(component.casefold())
        self._prune_component(telemetry)
        return tuple(telemetry.history)

    def current(self, component: str) -> TemperatureSample | None:
        return self._component(component.casefold()).current

    def record_scan(self, scan: TemperatureScan) -> None:
        for component, samples in scan.samples_by_component:
            telemetry = self._component(component)
            telemetry.last_error = None
            if samples:
                self._record_samples(telemetry, samples)
                telemetry.state = TemperatureState.VALID
                telemetry.current = samples[-1]

    def _component(self, component: str) -> _ComponentTelemetry:
        telemetry = self._components.get(component)
        if telemetry is None:
            telemetry = _ComponentTelemetry(policy=self.policy_for(component))
            self._components[component] = telemetry
        return telemetry

    def _record_samples(
        self,
        telemetry: _ComponentTelemetry,
        samples: tuple[TemperatureSample, ...],
    ) -> None:
        now = samples[-1].sampled_monotonic
        history_before = tuple(telemetry.history)
        aggregate = max(samples, key=lambda sample: sample.value_celsius)
        for sample in samples:
            sensor_history = telemetry.sensor_histories.setdefault(
                sample.sensor_id, deque(maxlen=telemetry.policy.history_limit)
            )
            sensor_history.append(sample)
        telemetry.history.append(aggregate)
        telemetry.current = aggregate
        self._prune_component(telemetry, now=now)
        self._update_event_state(telemetry, aggregate, history_before)

    def _prune_component(
        self,
        telemetry: _ComponentTelemetry,
        *,
        now: float | None = None,
    ) -> None:
        if now is None:
            if telemetry.history:
                now = telemetry.history[-1].sampled_monotonic
            else:
                return
        cutoff = now - 600.0
        while telemetry.history and telemetry.history[0].sampled_monotonic < cutoff:
            telemetry.history.popleft()
        for sensor_id in tuple(telemetry.sensor_histories):
            history = telemetry.sensor_histories[sensor_id]
            while history and history[0].sampled_monotonic < cutoff:
                history.popleft()
            if not history:
                telemetry.sensor_histories.pop(sensor_id, None)

    def _update_event_state(
        self,
        telemetry: _ComponentTelemetry,
        sample: TemperatureSample,
        previous_history: tuple[TemperatureSample, ...],
    ) -> None:
        policy = telemetry.policy
        warning = policy.warning_celsius
        if warning is None:
            return
        if telemetry.active_event is not None:
            event = telemetry.active_event
            event["samples"].append(sample)
            limit = policy.pre_event_samples + policy.post_event_samples + 2
            if len(event["samples"]) > limit:
                event["samples"].pop(0)
            event["peak"] = max(event["peak"], sample.value_celsius)
            recovery = (
                policy.recovery_celsius
                if policy.recovery_celsius is not None
                else warning - 5.0
            )
            if sample.value_celsius <= recovery:
                telemetry.events.append(
                    TemperatureEvent(
                        component=event["component"],
                        sensor_id=event["sensor_id"],
                        sensor_name=event["sensor_name"],
                        started_at=event["started_at"],
                        started_monotonic=event["started_monotonic"],
                        peak_celsius=event["peak"],
                        baseline_celsius=event["baseline"],
                        severity=event["severity"],
                        samples=tuple(event["samples"]),
                        ended_at=sample.sampled_at,
                        ended_monotonic=sample.sampled_monotonic,
                    )
                )
                telemetry.active_event = None
                telemetry.consecutive_hot = 0
                telemetry.cooldown_until = (
                    sample.sampled_monotonic + policy.cooldown_seconds
                )
            return

        if sample.sampled_monotonic < telemetry.cooldown_until:
            return

        baseline = self._baseline(previous_history, policy.rapid_rise_window)
        rapid_rise = (
            policy.rapid_rise_celsius is not None
            and baseline is not None
            and sample.value_celsius - baseline >= policy.rapid_rise_celsius
            and sample.value_celsius >= warning - 5.0
        )
        if sample.value_celsius >= warning:
            telemetry.consecutive_hot += 1
        else:
            telemetry.consecutive_hot = 0

        critical = (
            policy.critical_celsius is not None
            and sample.value_celsius >= policy.critical_celsius
        )
        if (
            critical
            or telemetry.consecutive_hot >= policy.consecutive_samples
            or rapid_rise
        ):
            prelude = previous_history[-policy.pre_event_samples :]
            start_samples = tuple(prelude) + (sample,)
            telemetry.active_event = {
                "component": sample.component,
                "sensor_id": sample.sensor_id,
                "sensor_name": sample.sensor_name,
                "started_at": sample.sampled_at,
                "started_monotonic": sample.sampled_monotonic,
                "peak": sample.value_celsius,
                "baseline": baseline if baseline is not None else sample.value_celsius,
                "severity": "critical"
                if critical
                else "spike"
                if rapid_rise
                else "warning",
                "samples": list(
                    start_samples[
                        -(policy.pre_event_samples + policy.post_event_samples + 2) :
                    ]
                ),
            }

    @staticmethod
    def _baseline(history: tuple[TemperatureSample, ...], window: int) -> float | None:
        if not history:
            return None
        tail = history[-window:]
        if not tail:
            return None
        return float(statistics.fmean(sample.value_celsius for sample in tail))

    @staticmethod
    def _severity_for(
        telemetry: _ComponentTelemetry,
        values: list[float],
    ) -> str:
        policy = telemetry.policy
        if not values:
            return telemetry.state.value
        latest = values[-1]
        if policy.critical_celsius is not None and latest >= policy.critical_celsius:
            return "critical"
        if policy.warning_celsius is not None and latest >= policy.warning_celsius:
            return "warning"
        return "normal"

    @staticmethod
    def _legacy_samples(
        component: str,
        summary: ResourceSummary,
    ) -> tuple[TemperatureSample, ...]:
        prefixes = {
            "cpu": "Temperature: ",
            "gpu": "Temperature: ",
            "storage": "Drive temperature: ",
        }
        prefix = prefixes.get(component)
        if prefix is None:
            return ()
        for line in summary.details:
            if not line.startswith(prefix):
                continue
            match = _DETAIL_TEMPERATURE_PATTERN.search(line)
            if match:
                now = datetime.now(timezone.utc).astimezone()
                value = float(match.group(1))
                return (
                    TemperatureSample(
                        component=component,
                        sensor_id=f"{component}:legacy",
                        sensor_name=summary.title,
                        value_celsius=value,
                        sampled_at=now,
                        sampled_monotonic=time.monotonic(),
                    ),
                )
        return ()


def temperature_sample_to_dict(sample: TemperatureSample) -> dict[str, Any]:
    return {
        "component": sample.component,
        "sensor_id": sample.sensor_id,
        "sensor_name": sample.sensor_name,
        "value_celsius": sample.value_celsius,
        "sampled_at": sample.sampled_at.isoformat(),
        "sampled_monotonic": sample.sampled_monotonic,
    }


def temperature_sample_from_dict(data: Any) -> TemperatureSample:
    if not isinstance(data, dict):
        raise TypeError("temperature sample must be an object")
    component = data.get("component")
    sensor_id = data.get("sensor_id")
    sensor_name = data.get("sensor_name")
    value_celsius = data.get("value_celsius")
    sampled_at = data.get("sampled_at")
    sampled_monotonic = data.get("sampled_monotonic")
    if not isinstance(component, str):
        raise TypeError("temperature sample component must be a string")
    if not isinstance(sensor_id, str):
        raise TypeError("temperature sample sensor_id must be a string")
    if not isinstance(sensor_name, str):
        raise TypeError("temperature sample sensor_name must be a string")
    if not isinstance(value_celsius, (int, float)):
        raise TypeError("temperature sample value must be a number")
    if not isinstance(sampled_at, str):
        raise TypeError("temperature sample timestamp must be a string")
    if not isinstance(sampled_monotonic, (int, float)):
        raise TypeError("temperature sample monotonic time must be a number")
    return TemperatureSample(
        component=component,
        sensor_id=sensor_id,
        sensor_name=sensor_name,
        value_celsius=float(value_celsius),
        sampled_at=datetime.fromisoformat(sampled_at),
        sampled_monotonic=float(sampled_monotonic),
    )
