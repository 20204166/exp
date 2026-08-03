from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResourceSummary:
    key: str
    title: str
    value: str
    subtitle: str
    percent: float | None
    details: tuple[str, ...]
    actionable: bool = False


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