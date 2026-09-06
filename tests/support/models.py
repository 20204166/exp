"""Shared deterministic builders for the model objects used across tests.

Each factory returns fresh immutable model instances. Defaults deliberately
avoid inferring health, capability or actionability from the resource key;
those fields are explicit overrides so a test can target one condition
without copying a full structure.
"""

from datetime import datetime, timezone

from maintenance.models import CapabilityState, DashboardSnapshot, ResourceSummary

FIXED_SCANNED_AT = datetime(2026, 9, 5, 3, 42, 52, tzinfo=timezone.utc)


def make_summary(
    key: str,
    title: str,
    *,
    value: str = "10%",
    subtitle: str = "subtitle",
    percent: float | None = 5.0,
    details: tuple[str, ...] = (),
    actionable: bool = False,
    failed: bool = False,
    capability: CapabilityState = CapabilityState.UNKNOWN,
) -> ResourceSummary:
    """Build a valid :class:`ResourceSummary` with explicit overrides."""

    return ResourceSummary(
        key=key,
        title=title,
        value=value,
        subtitle=subtitle,
        percent=percent,
        details=details,
        actionable=actionable,
        failed=failed,
        capability=capability,
    )


def make_snapshot(
    *resources: ResourceSummary,
    system_label: str = "Linux 6.1 • x86_64",
    scanned_at: datetime = FIXED_SCANNED_AT,
) -> DashboardSnapshot:
    """Build a valid :class:`DashboardSnapshot` with a deterministic time."""

    return DashboardSnapshot(
        system_label=system_label,
        scanned_at=scanned_at,
        resources=tuple(resources),
    )
