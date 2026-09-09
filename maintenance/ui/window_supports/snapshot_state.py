"""Pure dashboard snapshot state transformations used by ``AppWindow``."""

from __future__ import annotations

from maintenance.models import DashboardSnapshot, ResourceSummary


def merge_resource(
    *,
    previous_snapshot: DashboardSnapshot | None,
    failed_counts: dict[str, int],
    key: str,
    resource: ResourceSummary,
    failed_card_keep_limit: int,
) -> ResourceSummary:
    """Merge one incoming card against its last valid value."""

    prior = (
        next(
            (item for item in previous_snapshot.resources if item.key == key),
            None,
        )
        if previous_snapshot is not None
        else None
    )

    if not resource.failed:
        failed_counts[key] = 0
        return resource
    if prior is None:
        return resource

    failed_counts[key] = failed_counts.get(key, 0) + 1
    if failed_counts[key] >= failed_card_keep_limit:
        return resource
    return prior


def merge_snapshot(
    *,
    previous_snapshot: DashboardSnapshot | None,
    failed_counts: dict[str, int],
    snapshot: DashboardSnapshot,
    failed_card_keep_limit: int,
) -> DashboardSnapshot:
    """Keep last-valid card values while a refresh fails transiently."""

    return DashboardSnapshot(
        system_label=snapshot.system_label,
        scanned_at=snapshot.scanned_at,
        resources=tuple(
            merge_resource(
                previous_snapshot=previous_snapshot,
                failed_counts=failed_counts,
                key=resource.key,
                resource=resource,
                failed_card_keep_limit=failed_card_keep_limit,
            )
            for resource in snapshot.resources
        ),
    )


def replace_snapshot_resource(
    snapshot: DashboardSnapshot | None,
    key: str,
    resource: ResourceSummary,
) -> DashboardSnapshot | None:
    """Replace one resource in a snapshot, preserving all other resources."""

    if snapshot is None:
        return None
    return DashboardSnapshot(
        system_label=snapshot.system_label,
        scanned_at=snapshot.scanned_at,
        resources=tuple(
            resource if current.key == key else current
            for current in snapshot.resources
        ),
    )
