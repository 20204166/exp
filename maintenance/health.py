"""Restrained, factual System Health checks over a dashboard snapshot.

Warnings are only produced for conditions backed by reliable existing
metrics: storage genuinely nearing capacity, clearly excessive temperature,
severe memory pressure, and sustained excessive swap pressure. There is no
health score and no CPU-usage/battery/background-process judgement. Anything
unsupported or unavailable simply produces no warning (neutral/healthy).
"""

import re

from maintenance.components.scan_support import BYTE_SCALE_UNITS, detail_line_suffix
from maintenance.models import DashboardSnapshot, ResourceSummary

STORAGE_WARN_PERCENT = 90.0
MEMORY_WARN_PERCENT = 90.0
TEMPERATURE_WARN_C = 90.0
SWAP_WARN_PERCENT = 80.0
CONSECUTIVE_LIMIT = 2

_BYTE_UNITS = {"B": 1, **{unit: scale for scale, unit in BYTE_SCALE_UNITS}}

_SWAP_UNITS = "|".join(("B", *(unit for _scale, unit in reversed(BYTE_SCALE_UNITS))))
_TEMPERATURE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)°C")
_SWAP_PATTERN = re.compile(
    rf"Swap: ([\d.]+) ({_SWAP_UNITS}) used of ([\d.]+) ({_SWAP_UNITS})"
)


def health_warnings(
    snapshot: DashboardSnapshot,
    state: dict[str, int] | None = None,
    *,
    consecutive_limit: int = CONSECUTIVE_LIMIT,
) -> tuple[str, ...]:
    """Return concise warning strings (empty when healthy).

    `state` carries consecutive-count per condition so a single transient
    spike (a hot burst, a one-off pressure reading) never warns; the
    condition must persist across `consecutive_limit` refreshes.
    """

    if state is None:
        state = {}
    warnings: list[str] = []

    storage = _resource(snapshot, "storage")
    if (
        storage is not None
        and storage.percent is not None
        and storage.percent >= STORAGE_WARN_PERCENT
    ):
        warnings.append(f"Storage is {storage.percent:.0f}% full")

    memory = _resource(snapshot, "memory")
    memory_met = (
        memory is not None
        and memory.percent is not None
        and memory.percent >= MEMORY_WARN_PERCENT
    )
    if (
        _sustained(state, "memory", memory_met, consecutive_limit)
        and memory is not None
    ):
        warnings.append(f"Memory pressure is high ({memory.percent:.0f}%)")

    for category, key, prefix in (
        ("CPU", "cpu", "Temperature: "),
        ("GPU", "gpu", "Temperature: "),
        ("NVMe", "storage", "Drive temperature: "),
    ):
        temperature = _temperature(snapshot, key, prefix)
        met = temperature is not None and temperature >= TEMPERATURE_WARN_C
        if _sustained(state, f"temp_{category}", met, consecutive_limit):
            warnings.append(f"{category} temperature is {temperature:.0f}°C")

    swap_used, swap_total = _swap_usage(memory)
    swap_met = swap_total > 0 and (swap_used / swap_total) * 100 >= SWAP_WARN_PERCENT
    if _sustained(state, "swap", swap_met, consecutive_limit):
        warnings.append(f"Swap is {swap_used / swap_total * 100:.0f}% in use")

    return tuple(warnings)


def _resource(snapshot: DashboardSnapshot, key: str) -> ResourceSummary | None:
    return next(
        (resource for resource in snapshot.resources if resource.key == key),
        None,
    )


def _temperature(
    snapshot: DashboardSnapshot,
    key: str,
    prefix: str,
) -> float | None:
    resource = _resource(snapshot, key)
    if resource is None:
        return None
    if resource.temperatures:
        return max(sample.value_celsius for sample in resource.temperatures)
    line = detail_line_suffix(resource.details, prefix)
    if line is None:
        return None
    match = _TEMPERATURE_PATTERN.search(line)
    if match:
        return float(match.group(1))
    return None


def _swap_usage(resource: ResourceSummary | None) -> tuple[float, float]:
    if resource is None:
        return 0, 0
    for line in resource.details:
        match = _SWAP_PATTERN.match(line)
        if match:
            used = float(match.group(1)) * _BYTE_UNITS[match.group(2)]
            total = float(match.group(3)) * _BYTE_UNITS[match.group(4)]
            return used, total
    return 0, 0


def _sustained(
    state: dict[str, int],
    key: str,
    met: bool,
    limit: int,
) -> bool:
    if met:
        state[key] = state.get(key, 0) + 1
        return state[key] >= limit
    state[key] = 0
    return False
