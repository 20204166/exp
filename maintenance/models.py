from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class CapabilityState(str, Enum):
    """Typed hardware-capability state carried by a component result.

    ``SUPPORTED`` means the component genuinely exists and was read.
    ``UNSUPPORTED`` means an authoritative probe proved the capability is
    absent (e.g. no battery). ``UNKNOWN`` means the read failed or the probe
    could not distinguish absence from a transient failure, so the capability
    must never be auto-hidden on that basis.
    """

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ResourceSummary:
    key: str
    title: str
    value: str
    subtitle: str
    percent: float | None
    details: tuple[str, ...]
    actionable: bool = False
    failed: bool = False
    capability: CapabilityState = CapabilityState.UNKNOWN


def unavailable_summary(key: str, title: str) -> ResourceSummary:
    """Return the standard "Unavailable" summary for a failed component.

    Shared by the scanner (one card builder raised) and the window (a
    component worker raised), so the failure presentation never drifts
    between the two paths.
    """

    return ResourceSummary(
        key=key,
        title=title,
        value="Unavailable",
        subtitle="Information unavailable",
        percent=None,
        details=(f"{title} information is unavailable.",),
        actionable=key in ("cpu", "memory", "storage"),
        failed=True,
    )


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    system_label: str
    scanned_at: datetime
    resources: tuple[ResourceSummary, ...]

    def get(self, key: str) -> ResourceSummary:
        for resource in self.resources:
            if resource.key == key:
                return resource

        raise KeyError(f"Unknown resource: {key}")


@dataclass(frozen=True, slots=True)
class ProcessCandidate:
    pid: int
    name: str
    memory_bytes: int
    memory_percent: float
    cpu_percent: float
    activity: str
    username: str
    action_allowed: bool
    create_time: float | None = None


@dataclass(frozen=True, slots=True)
class FileCandidate:
    path: Path
    size_bytes: int
    modified_at: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class ProcessActionResult:
    requested: int
    stopped: tuple[int, ...]
    force_required: tuple[int, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FileActionResult:
    requested: int
    moved: tuple[Path, ...]
    errors: tuple[str, ...]
