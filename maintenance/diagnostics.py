"""Bounded, read-only diagnostics projections for the application UI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from maintenance.components.placement import PlacementDecision

MAX_DETAIL_LENGTH = 160


def truncate_detail(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value)[:MAX_DETAIL_LENGTH]


def display_value(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def format_timestamp(value: float | None) -> str:
    """Format an internal epoch timestamp for the visible diagnostics page."""

    if value is None:
        return "No data yet"
    return (
        datetime.fromtimestamp(value, tz=timezone.utc).astimezone().strftime("%H:%M:%S")
    )


@dataclass(frozen=True, slots=True)
class ComponentDiagnostic:
    key: str
    state: str
    capability: str
    in_flight: bool
    last_success: float | None
    last_error_category: str | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class OperationDiagnostic:
    key: str
    generation: int
    in_flight: bool
    has_result: bool
    last_success: float | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class NodeDiagnostic:
    node_id: str
    display_name: str
    trust: str
    pairing: str
    connection: str
    reason: str | None
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClusterDiagnostic:
    role: str
    coordinator_id: str
    epoch: int
    heartbeat_age_seconds: float | None
    database_bytes: int
    database_cap_bytes: int
    standby_bytes: int
    standby_cap_bytes: int
    retention_pressure: str
    last_snapshot_at: float | None
    history_writes_paused: bool
    failure: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", truncate_detail(self.role) or "unknown")
        object.__setattr__(
            self, "coordinator_id", truncate_detail(self.coordinator_id) or "unknown"
        )
        object.__setattr__(self, "failure", truncate_detail(self.failure))


@dataclass(frozen=True, slots=True)
class RenderDiagnostic:
    pending: int
    requests: int
    commits: int
    coalesced: int
    stale_rejections: int


@dataclass(frozen=True, slots=True)
class PlacementDiagnostic:
    job_type: str
    selected_worker: str
    eligible_count: int
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "job_type", truncate_detail(self.job_type) or "unknown"
        )
        object.__setattr__(
            self,
            "selected_worker",
            truncate_detail(self.selected_worker) or "No worker selected",
        )
        object.__setattr__(
            self, "reason", truncate_detail(self.reason) or "No reason provided"
        )


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    components: tuple[ComponentDiagnostic, ...]
    operations: tuple[OperationDiagnostic, ...]
    nodes: tuple[NodeDiagnostic, ...]
    render: RenderDiagnostic
    most_recent_failure: str | None = None
    placement: PlacementDiagnostic | None = None
    cluster: ClusterDiagnostic | None = None


def _component_state(in_flight: bool, paused: bool, error: Any) -> str:
    if in_flight:
        return "in_flight"
    if paused:
        return "paused"
    return "failed" if error is not None else "idle"


def build_diagnostics_snapshot(
    *,
    scheduler: Any,
    coordinator: Any,
    registry: Any,
    ui_coordinator: Any,
    capabilities: dict[str, Any] | None = None,
    discovery_reason: str | None = None,
    placement: PlacementDecision | None = None,
    cluster: ClusterDiagnostic | None = None,
) -> DiagnosticsSnapshot:
    component_rows: list[ComponentDiagnostic] = []
    for key in scheduler.intervals:
        in_flight, paused, last_success, last_error = scheduler.diagnostic_state(key)
        category, detail = last_error or (None, None)
        component_rows.append(
            ComponentDiagnostic(
                key=key,
                state=_component_state(in_flight, paused, last_error),
                capability=display_value((capabilities or {}).get(key, "unknown")),
                in_flight=in_flight,
                last_success=last_success,
                last_error_category=category,
                last_error=truncate_detail(detail),
            )
        )

    operation_rows: list[OperationDiagnostic] = []
    for key, state in coordinator.diagnostic_states():
        operation_rows.append(
            OperationDiagnostic(
                key=key,
                generation=state.generation,
                in_flight=state.in_flight,
                has_result=state.last_result is not None,
                last_success=state.last_success,
                last_error=truncate_detail(state.last_error),
            )
        )

    node_rows: list[NodeDiagnostic] = []
    for context in registry.contexts():
        descriptor = context.descriptor
        reason = context.connection.reason or discovery_reason
        node_rows.append(
            NodeDiagnostic(
                node_id=descriptor.id.value,
                display_name=descriptor.display_name,
                trust=display_value(descriptor.trust),
                pairing=display_value(descriptor.pairing_state),
                connection=display_value(context.connection.status),
                reason=truncate_detail(reason),
                capabilities=tuple(
                    sorted(display_value(item) for item in descriptor.capabilities)
                ),
            )
        )

    render = RenderDiagnostic(
        pending=ui_coordinator.pending_count,
        requests=ui_coordinator.render_requests,
        commits=ui_coordinator.render_commits,
        coalesced=ui_coordinator.coalesced_requests,
        stale_rejections=ui_coordinator.stale_rejections,
    )
    failures = [
        f"{row.key}: {row.last_error}"
        for row in component_rows
        if row.last_error is not None
    ] + [row.last_error for row in operation_rows if row.last_error is not None]
    placement_diagnostic = (
        PlacementDiagnostic(
            job_type=truncate_detail("placement") or "placement",
            selected_worker=truncate_detail(
                placement.selected_node_id.value
                if placement is not None and placement.selected_node_id is not None
                else "No worker selected"
            )
            or "No worker selected",
            eligible_count=len(placement.eligible_node_ids),
            reason=truncate_detail(placement.reason) or "No reason provided",
        )
        if placement is not None
        else None
    )
    return DiagnosticsSnapshot(
        components=tuple(component_rows),
        operations=tuple(operation_rows),
        nodes=tuple(node_rows),
        render=render,
        most_recent_failure=truncate_detail(failures[-1] if failures else None),
        placement=placement_diagnostic,
        cluster=cluster,
    )


def serialize_diagnostics(snapshot: DiagnosticsSnapshot) -> str:
    return json.dumps(asdict(snapshot), sort_keys=True, indent=2)


def serialize_cluster_diagnostic(diagnostic: ClusterDiagnostic) -> str:
    """Serialize only the bounded, non-secret cluster projection."""

    return json.dumps(asdict(diagnostic), sort_keys=True)
