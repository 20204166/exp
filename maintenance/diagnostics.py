"""Bounded, read-only diagnostics projections for the application UI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

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
class RenderDiagnostic:
    pending: int
    requests: int
    commits: int
    coalesced: int
    stale_rejections: int


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    components: tuple[ComponentDiagnostic, ...]
    operations: tuple[OperationDiagnostic, ...]
    nodes: tuple[NodeDiagnostic, ...]
    render: RenderDiagnostic
    most_recent_failure: str | None = None


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
    return DiagnosticsSnapshot(
        components=tuple(component_rows),
        operations=tuple(operation_rows),
        nodes=tuple(node_rows),
        render=render,
        most_recent_failure=truncate_detail(failures[-1] if failures else None),
    )


def serialize_diagnostics(snapshot: DiagnosticsSnapshot) -> str:
    return json.dumps(asdict(snapshot), sort_keys=True, indent=2)
