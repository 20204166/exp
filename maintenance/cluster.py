"""Secure cluster data contract, trusted-node persistence, and lifecycle glue.

This module owns the versioned ``NodeSnapshot`` envelope (node identity +
schema version + payload), the codecs for the read models that cross the
cluster boundary, and the durable ``ClusterStore`` that persists the
discovery toggle and trusted-node records (credentials, display overrides,
and optional manual host/port) atomically.

It deliberately imports no Tkinter, transport, scanner, or network code, so
the contract is safe to load in any interpreter and inside tests without a
display. The authenticated transport that consumes these envelopes lives in
``maintenance.remote``.
"""

from __future__ import annotations

import json
import logging
import math
import secrets
import time
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from maintenance.components.temperature import (
    temperature_sample_from_dict,
    temperature_sample_to_dict,
)
from maintenance.components.cluster_roles import (
    ClusterRole,
    CoordinatorEpoch,
    RoleAssignment,
    hash_invite,
    new_fencing_token,
)
from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    FileCandidate,
    ProcessActionResult,
    ProcessActionState,
    ProcessCandidate,
    ResourceSummary,
)
from maintenance.nodes import (
    NODE_SNAPSHOT_SCHEMA_VERSION,
    NodeCapability,
    NodeId,
    NodePermission,
    NodeSnapshot,
    NodeStatus,
    generate_node_secret,
    generate_stable_node_id,
)
from maintenance.persistence import atomic_write_text, read_text_or_none
from maintenance.preferences import default_preferences_path

LOGGER = logging.getLogger(__name__)

CLUSTER_SCHEMA_VERSION = 2
CONFIG_FILE_NAME = "cluster.json"


class ClusterDataError(ValueError):
    """Raised when a serialized cluster value cannot be decoded safely."""


class ClusterSaveError(RuntimeError):
    """Raised when cluster settings could not be committed to disk."""


class InviteExpiredError(ValueError):
    """Raised when a pairing-only invite is no longer valid."""


@dataclass(frozen=True, slots=True)
class InviteRecord:
    token_hash: str
    target_node_id: str
    expires_at: float
    token: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        if not math.isfinite(self.expires_at):
            raise ValueError("invite expiry must be finite")


def _initial_roles(local_node_id: str, now: float | None = None) -> tuple[RoleAssignment, ...]:
    return (
        RoleAssignment(
            frozenset({ClusterRole.COORDINATOR, ClusterRole.WORKER}),
            node_id=NodeId(local_node_id),
        ),
    )


def _initial_epoch(local_node_id: str, now: float | None = None) -> CoordinatorEpoch:
    current = time.time() if now is None else now
    return CoordinatorEpoch(
        epoch=1,
        coordinator_id=NodeId(local_node_id),
        fencing_token=new_fencing_token(),
        issued_at=current,
        lease_expires_at=current + 120.0,
    )


def default_cluster_path(
    *,
    environment: dict[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    """Return the standard per-user cluster settings file.

    Reuses the platform-aware preferences directory and keeps cluster data in
    its own ``cluster.json`` beside ``preferences.json``.
    """

    return default_preferences_path(
        environment=environment,
        home=home,
        platform_name=platform_name,
    ).with_name(CONFIG_FILE_NAME)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ClusterDataError(f"{field} must be an ISO timestamp string")
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ClusterDataError(f"{field} is not a valid timestamp") from error


def resource_summary_to_dict(summary: ResourceSummary) -> dict[str, Any]:
    data = {
        "key": summary.key,
        "title": summary.title,
        "value": summary.value,
        "subtitle": summary.subtitle,
        "percent": summary.percent,
        "details": list(summary.details),
        "actionable": summary.actionable,
        "failed": summary.failed,
        # Keep the v1 field readable by older peers. New peers recover the
        # precise state from the additive field below.
        "capability": (
            summary.capability.value
            if summary.capability
            in (
                CapabilityState.SUPPORTED,
                CapabilityState.UNSUPPORTED,
                CapabilityState.UNKNOWN,
            )
            else CapabilityState.UNKNOWN.value
        ),
        "temperatures": [
            temperature_sample_to_dict(sample) for sample in summary.temperatures
        ],
    }
    if summary.capability not in (
        CapabilityState.SUPPORTED,
        CapabilityState.UNSUPPORTED,
        CapabilityState.UNKNOWN,
    ):
        data["capability_state"] = summary.capability.value
    return data


def resource_summary_from_dict(data: Any) -> ResourceSummary:
    if not isinstance(data, dict):
        raise ClusterDataError("resource summary must be an object")
    key = data.get("key")
    if not isinstance(key, str):
        raise ClusterDataError("resource summary key must be a string")
    capability = data.get(
        "capability_state", data.get("capability", CapabilityState.UNKNOWN.value)
    )
    try:
        state = CapabilityState(capability)
    except ValueError as error:
        raise ClusterDataError("resource summary has an unknown capability") from error
    details = data.get("details")
    if not isinstance(details, list) or not all(
        isinstance(item, str) for item in details
    ):
        raise ClusterDataError("resource summary details must be a string list")
    temperatures = data.get("temperatures", [])
    if not isinstance(temperatures, list):
        raise ClusterDataError("resource summary temperatures must be a list")
    percent = data.get("percent")
    if percent is not None and not isinstance(percent, (int, float)):
        raise ClusterDataError("resource summary percent must be a number")
    for field in ("title", "value", "subtitle"):
        if not isinstance(data.get(field), str):
            raise ClusterDataError(f"resource summary {field} must be a string")
    for field in ("actionable", "failed"):
        if not isinstance(data.get(field), bool):
            raise ClusterDataError(f"resource summary {field} must be a boolean")
    decoded_temperatures = []
    for item in temperatures:
        try:
            decoded_temperatures.append(temperature_sample_from_dict(item))
        except (TypeError, ValueError, OverflowError):
            continue
    return ResourceSummary(
        key=key,
        title=data["title"],
        value=data["value"],
        subtitle=data["subtitle"],
        percent=cast(float | None, percent),
        details=tuple(details),
        actionable=bool(data["actionable"]),
        failed=bool(data["failed"]),
        capability=state,
        temperatures=tuple(decoded_temperatures),
    )


def process_action_result_to_dict(result: ProcessActionResult) -> dict[str, Any]:
    """Encode one process-action result for the authenticated wire contract."""

    return {
        "requested": result.requested,
        "stopped": list(result.stopped),
        "force_required": list(result.force_required),
        "errors": list(result.errors),
    }


def process_action_result_from_dict(data: Any) -> ProcessActionResult:
    """Decode one process-action result without applying action policy."""

    if not isinstance(data, dict) or set(data) != {
        "requested",
        "stopped",
        "force_required",
        "errors",
    }:
        raise ClusterDataError("process action result must be an object")
    requested = data["requested"]
    if not isinstance(requested, int) or isinstance(requested, bool) or requested < 0:
        raise ClusterDataError("process action result requested is invalid")

    def pids(value: Any, field: str) -> tuple[int, ...]:
        if not isinstance(value, list):
            raise ClusterDataError(f"process action result {field} must be a list")
        if any(
            not isinstance(pid, int) or isinstance(pid, bool) or pid < 0
            for pid in value
        ):
            raise ClusterDataError(f"process action result {field} has invalid PIDs")
        result = tuple(value)
        if len(set(result)) != len(result):
            raise ClusterDataError(f"process action result {field} has duplicate PIDs")
        return result

    stopped = pids(data["stopped"], "stopped")
    force_required = pids(data["force_required"], "force_required")
    if set(stopped).intersection(force_required):
        raise ClusterDataError("process action result has overlapping PIDs")
    if len(stopped) + len(force_required) > requested:
        raise ClusterDataError("process action result exceeds requested count")
    errors = data["errors"]
    if not isinstance(errors, list) or any(
        not isinstance(error, str) for error in errors
    ):
        raise ClusterDataError("process action result errors must be a string list")
    return ProcessActionResult(
        requested=requested,
        stopped=stopped,
        force_required=force_required,
        errors=tuple(errors),
    )


def dashboard_snapshot_to_dict(snapshot: DashboardSnapshot) -> dict[str, Any]:
    return {
        "system_label": snapshot.system_label,
        "scanned_at": _iso(snapshot.scanned_at),
        "resources": [
            resource_summary_to_dict(resource) for resource in snapshot.resources
        ],
    }


def dashboard_snapshot_from_dict(data: Any) -> DashboardSnapshot:
    if not isinstance(data, dict):
        raise ClusterDataError("dashboard snapshot must be an object")
    system_label = data.get("system_label")
    if not isinstance(system_label, str):
        raise ClusterDataError("dashboard system_label must be a string")
    resources = data.get("resources")
    if not isinstance(resources, list):
        raise ClusterDataError("dashboard resources must be a list")
    return DashboardSnapshot(
        system_label=system_label,
        scanned_at=_parse_datetime(data.get("scanned_at"), "dashboard scanned_at"),
        resources=tuple(resource_summary_from_dict(item) for item in resources),
    )


def node_snapshot_to_dict(snapshot: NodeSnapshot) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": snapshot.schema_version,
        "node_id": snapshot.node_id.value,
        "display_name": snapshot.display_name,
        "hostname": snapshot.hostname,
        "platform": snapshot.platform,
        "status": snapshot.status.value,
        "capabilities": sorted(
            capability.value for capability in snapshot.capabilities
        ),
        "scanned_at": _iso(snapshot.scanned_at),
    }
    if snapshot.dashboard is not None:
        payload["dashboard"] = dashboard_snapshot_to_dict(snapshot.dashboard)
    return payload


def node_snapshot_from_dict(data: Any) -> NodeSnapshot:
    if not isinstance(data, dict):
        raise ClusterDataError("node snapshot must be an object")
    if data.get("schema_version") != NODE_SNAPSHOT_SCHEMA_VERSION:
        raise ClusterDataError(
            f"unsupported node snapshot schema {data.get('schema_version')!r}"
        )
    node_id = data.get("node_id")
    if not isinstance(node_id, str):
        raise ClusterDataError("node snapshot node_id must be a string")
    for field in ("display_name", "hostname"):
        if not isinstance(data.get(field), str):
            raise ClusterDataError(f"node snapshot {field} must be a string")
    platform = data.get("platform")
    if platform is not None and not isinstance(platform, str):
        raise ClusterDataError("node snapshot platform must be a string or null")
    try:
        status = NodeStatus(data["status"])
    except (KeyError, ValueError) as error:
        raise ClusterDataError("node snapshot status is invalid") from error
    capabilities_data = data.get("capabilities")
    if not isinstance(capabilities_data, list):
        raise ClusterDataError("node snapshot capabilities must be a list")
    capabilities: set[NodeCapability] = set()
    for raw in capabilities_data:
        if not isinstance(raw, str):
            raise ClusterDataError("node snapshot capability must be a string")
        try:
            capabilities.add(NodeCapability(raw))
        except ValueError as error:
            raise ClusterDataError("node snapshot has an unknown capability") from error
    dashboard = data.get("dashboard")
    if dashboard is not None:
        dashboard = dashboard_snapshot_from_dict(dashboard)
    return NodeSnapshot(
        node_id=NodeId(node_id),
        display_name=data["display_name"],
        hostname=data["hostname"],
        platform=platform,
        status=status,
        capabilities=frozenset(capabilities),
        scanned_at=_parse_datetime(data.get("scanned_at"), "node snapshot scanned_at"),
        dashboard=dashboard,
        schema_version=NODE_SNAPSHOT_SCHEMA_VERSION,
    )


def node_snapshot_envelope(snapshot: NodeSnapshot) -> str:
    """Serialize one node snapshot to its wire envelope text."""
    return json.dumps(node_snapshot_to_dict(snapshot), sort_keys=True) + "\n"


def parse_node_snapshot_envelope(text: str) -> NodeSnapshot:
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as error:
        raise ClusterDataError("node snapshot envelope is not valid JSON") from error
    return node_snapshot_from_dict(data)


def is_node_snapshot_compatible(version: Any) -> bool:
    return version == NODE_SNAPSHOT_SCHEMA_VERSION


def process_candidate_to_dict(process: ProcessCandidate) -> dict[str, Any]:
    return {
        "pid": process.pid,
        "name": process.name,
        "memory_bytes": process.memory_bytes,
        "memory_percent": process.memory_percent,
        "cpu_percent": process.cpu_percent,
        "activity": process.activity,
        "username": process.username,
        "action_allowed": process.action_allowed,
        "create_time": process.create_time,
        "protected": process.protected,
        "action_state": process.action_state.value,
    }


def process_candidate_from_dict(data: Any) -> ProcessCandidate:
    if not isinstance(data, dict):
        raise ClusterDataError("process candidate must be an object")
    pid = data.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise ClusterDataError("process candidate pid must be an integer")
    for field in ("name", "activity", "username"):
        if not isinstance(data.get(field), str):
            raise ClusterDataError(f"process candidate {field} must be a string")
    for field in ("memory_bytes", "memory_percent", "cpu_percent"):
        value = data.get(field)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or value < 0
        ):
            raise ClusterDataError(f"process candidate {field} must be a number")
    create_time = data.get("create_time")
    if create_time is not None and (
        not isinstance(create_time, (int, float))
        or isinstance(create_time, bool)
        or not math.isfinite(float(create_time))
        or create_time < 0
    ):
        raise ClusterDataError("process candidate create_time must be a number")
    action_allowed = data.get("action_allowed")
    if not isinstance(action_allowed, bool):
        raise ClusterDataError("process candidate action_allowed must be a boolean")
    protected = data.get("protected", not action_allowed)
    if not isinstance(protected, bool):
        raise ClusterDataError("process candidate protected must be a boolean")
    action_state_value = data.get(
        "action_state",
        ProcessActionState.ALLOWED.value
        if action_allowed and not protected
        else ProcessActionState.PROTECTED.value,
    )
    try:
        action_state = ProcessActionState(action_state_value)
    except ValueError as error:
        raise ClusterDataError("process candidate action_state is invalid") from error
    return ProcessCandidate(
        pid=pid,
        name=data["name"],
        memory_bytes=int(data["memory_bytes"]),
        memory_percent=float(data["memory_percent"]),
        cpu_percent=float(data["cpu_percent"]),
        activity=data["activity"],
        username=data["username"],
        action_allowed=action_allowed,
        create_time=cast(float | None, create_time),
        protected=protected,
        action_state=action_state,
    )


def file_candidate_to_dict(candidate: FileCandidate) -> dict[str, Any]:
    return {
        "path": str(candidate.path),
        "size_bytes": candidate.size_bytes,
        "modified_at": _iso(candidate.modified_at),
        "reason": candidate.reason,
    }


def file_candidate_from_dict(data: Any) -> FileCandidate:
    if not isinstance(data, dict):
        raise ClusterDataError("file candidate must be an object")
    path = data.get("path")
    if not isinstance(path, str):
        raise ClusterDataError("file candidate path must be a string")
    size = data.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool):
        raise ClusterDataError("file candidate size_bytes must be an integer")
    reason = data.get("reason")
    if not isinstance(reason, str):
        raise ClusterDataError("file candidate reason must be a string")
    return FileCandidate(
        path=Path(path),
        size_bytes=size,
        modified_at=_parse_datetime(
            data.get("modified_at"), "file candidate modified_at"
        ),
        reason=reason,
    )


@dataclass(frozen=True, slots=True)
class TrustedNodeRecord:
    """One persisted trusted/authorised node plus its connection metadata.

    ``host``/``port`` record where the node's authenticated service may be
    reached (a discovered peer or a manually configured host); ``secret`` is
    the 256-bit pairing credential that authenticates every request.
    """

    node_id: str
    display_name: str
    hostname: str
    platform: str | None
    color: str | None
    host: str
    port: int | None
    capabilities: frozenset[NodeCapability]
    secret: str
    trusted_at: float
    identity_fingerprint: str | None = None
    transport_fingerprint: str | None = None
    permissions: frozenset[NodePermission] = frozenset()


@dataclass(frozen=True, slots=True)
class PeerGrantRecord:
    """Target-owned credential and permission grant for one caller."""

    caller_node_id: str
    secret: str
    permissions: frozenset[NodePermission]


@dataclass(slots=True)
class ClusterState:
    """The persisted cluster settings and trusted-node records."""

    discovery_enabled: bool = True
    trusted_nodes: tuple[TrustedNodeRecord, ...] = ()
    local_node_id: str = "local"
    local_identity_persisted: bool = True
    peer_grants: tuple[PeerGrantRecord, ...] = ()
    cluster_id: str = "local-cluster"
    role_assignments: tuple[RoleAssignment, ...] = ()
    coordinator_epoch: CoordinatorEpoch | None = None
    active_invites: tuple[InviteRecord, ...] = ()
    promotion_epochs: frozenset[int] = frozenset()

    @classmethod
    def create_local(cls, *, local_node_id: str | None = None) -> ClusterState:
        node_id = local_node_id or generate_stable_node_id()
        return cls(
            local_node_id=node_id,
            cluster_id=secrets.token_urlsafe(18),
            role_assignments=_initial_roles(node_id),
            coordinator_epoch=_initial_epoch(node_id),
        )

    @property
    def local_assignment(self) -> RoleAssignment:
        assignment = next(
            (
                item
                for item in self.role_assignments
                if item.node_id is not None and item.node_id.value == self.local_node_id
            ),
            None,
        )
        return assignment or RoleAssignment(
            frozenset({ClusterRole.WORKER}), node_id=NodeId(self.local_node_id)
        )

    def create_invite(
        self, *, target_node_id: str = "", now: float | None = None, ttl_seconds: float = 300.0
    ) -> InviteRecord:
        if ttl_seconds <= 0:
            raise ValueError("invite TTL must be positive")
        token = secrets.token_urlsafe(32)
        record = InviteRecord(
            hash_invite(token),
            target_node_id,
            (time.time() if now is None else now) + ttl_seconds,
        )
        self.active_invites = self.active_invites + (record,)
        # The token is returned to the caller but is never persisted.
        return replace(record, token=token)

    def consume_invite(self, token: str, *, now: float | None = None) -> InviteRecord:
        current = time.time() if now is None else now
        token_hash = hash_invite(token)
        for record in self.active_invites:
            if record.token_hash == token_hash:
                self.active_invites = tuple(
                    item for item in self.active_invites if item != record
                )
                if current > record.expires_at:
                    raise InviteExpiredError("pairing invite has expired")
                return record
        raise InviteExpiredError("pairing invite is unknown or expired")

    def grant(self, caller_node_id: str) -> PeerGrantRecord | None:
        for grant in self.peer_grants:
            if grant.caller_node_id == caller_node_id:
                return grant
        return None

    def record(self, node_id: str) -> TrustedNodeRecord | None:
        for record in self.trusted_nodes:
            if record.node_id == node_id:
                return record
        return None


def trusted_node_record(
    *,
    node_id: str,
    display_name: str,
    hostname: str,
    host: str,
    platform: str | None = None,
    color: str | None = None,
    port: int | None = None,
    capabilities: Iterable[NodeCapability] = (),
    secret: str | None = None,
    trusted_at: float | None = None,
    identity_fingerprint: str | None = None,
    transport_fingerprint: str | None = None,
    permissions: Iterable[NodePermission] = (),
) -> TrustedNodeRecord:
    """Build one trusted-node record, generating a fresh secret when absent."""

    return TrustedNodeRecord(
        node_id=node_id,
        display_name=display_name,
        hostname=hostname,
        platform=platform,
        color=color,
        host=host,
        port=port,
        capabilities=frozenset(capabilities),
        secret=secret or generate_node_secret(),
        trusted_at=trusted_at if trusted_at is not None else time.time(),
        identity_fingerprint=identity_fingerprint,
        transport_fingerprint=transport_fingerprint,
        permissions=frozenset(permissions),
    )


class ClusterStore:
    """Load and atomically save a ``ClusterState`` document.

    ``load()`` always returns valid state; malformed documents fall back to
    defaults (logged) and are never allowed to block startup, exactly like the
    preferences store. A later successful edit replaces them.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> ClusterState:
        text = read_text_or_none(
            self.path,
            logger=LOGGER,
            warning_template="Failed to read cluster settings: %s",
        )
        if text is None:
            state = ClusterState.create_local()
            return replace(
                state,
                local_identity_persisted=self._save_identity_migration(state),
            )
        state = self._parse(text)
        if state.local_node_id == "local":
            local_node_id = generate_stable_node_id()
            state = replace(
                state,
                local_node_id=local_node_id,
                role_assignments=_initial_roles(local_node_id),
                coordinator_epoch=_initial_epoch(local_node_id),
            )
            state = replace(
                state,
                local_identity_persisted=self._save_identity_migration(state),
            )
        elif not state.role_assignments:
            state = replace(
                state,
                role_assignments=_initial_roles(state.local_node_id),
                coordinator_epoch=_initial_epoch(state.local_node_id),
            )
        elif state.coordinator_epoch is None:
            state = replace(state, coordinator_epoch=_initial_epoch(state.local_node_id))
        return state

    def _save_identity_migration(self, state: ClusterState) -> bool:
        try:
            self.save(state)
        except ClusterSaveError as error:
            LOGGER.warning("Could not persist local node identity: %s", error)
            return False
        return True

    def save(self, state: ClusterState) -> None:
        """Validate and persist ``state`` atomically.

        A uniquely named temporary file is written in the destination
        directory, flushed and fsynced, then committed with ``os.replace``.
        Runtime state must only be published by the caller after this returns.
        """

        payload = self._serialize(state)
        atomic_write_text(
            self.path,
            payload,
            temp_prefix=".cluster-",
            create_directory_message="Cannot create cluster settings directory",
            save_message="Failed to save cluster settings",
            save_error_factory=ClusterSaveError,
            fsync_warning_template=(
                "Cluster settings committed but directory fsync failed: %s"
            ),
            logger=LOGGER,
        )

    def _parse(self, text: str) -> ClusterState:
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            LOGGER.warning("Malformed cluster settings JSON; using defaults")
            return ClusterState()
        if not isinstance(data, dict):
            LOGGER.warning("Cluster settings root must be an object; using defaults")
            return ClusterState()
        schema_version = data.get("schema_version")
        if schema_version not in (1, CLUSTER_SCHEMA_VERSION):
            LOGGER.warning("Unsupported cluster settings schema; using defaults")
            return ClusterState()
        discovery = data.get("discovery_enabled", True)
        if not isinstance(discovery, bool):
            LOGGER.warning("Cluster discovery flag is malformed; using defaults")
            return ClusterState()
        records_data = data.get("trusted_nodes", [])
        if not isinstance(records_data, list):
            LOGGER.warning("Cluster trusted nodes are malformed; using defaults")
            return ClusterState()
        records = tuple(
            record
            for item in records_data
            if (record := self._parse_record(item)) is not None
        )
        grants_data = data.get("peer_grants", [])
        grants = (
            tuple(
                grant
                for item in grants_data
                if (grant := self._parse_grant(item)) is not None
            )
            if isinstance(grants_data, list)
            else ()
        )
        grant_counts: dict[str, int] = {}
        for grant in grants:
            grant_counts[grant.caller_node_id] = (
                grant_counts.get(grant.caller_node_id, 0) + 1
            )
        grants = tuple(
            grant for grant in grants if grant_counts[grant.caller_node_id] == 1
        )
        local_node_id = data.get("local_node_id", "local")
        if not isinstance(local_node_id, str) or not local_node_id:
            LOGGER.warning("Cluster local node identity is malformed; using a new id")
            local_node_id = "local"
        role_assignments = self._parse_roles(data.get("role_assignments"), local_node_id)
        epoch = self._parse_epoch(data.get("coordinator_epoch"))
        invites = self._parse_invites(data.get("active_invites"))
        raw_promotion_epochs = data.get("promotion_epochs", [])
        promotion_epochs = (
            frozenset(
                item
                for item in raw_promotion_epochs
                if isinstance(item, int)
                and not isinstance(item, bool)
                and item >= 0
            )
            if isinstance(raw_promotion_epochs, list)
            else frozenset()
        )
        return ClusterState(
            discovery_enabled=discovery,
            trusted_nodes=records,
            local_node_id=local_node_id,
            peer_grants=grants,
            cluster_id=(
                data.get("cluster_id", "local-cluster")
                if isinstance(data.get("cluster_id", "local-cluster"), str)
                else "local-cluster"
            ),
            role_assignments=role_assignments,
            coordinator_epoch=epoch,
            active_invites=invites,
            promotion_epochs=promotion_epochs,
        )

    @staticmethod
    def _parse_roles(value: Any, local_node_id: str) -> tuple[RoleAssignment, ...]:
        if value is None:
            return _initial_roles(local_node_id)
        if not isinstance(value, list):
            return ()
        assignments: list[RoleAssignment] = []
        for item in value:
            if not isinstance(item, dict) or not isinstance(item.get("node_id"), str):
                continue
            raw_roles = item.get("roles", [])
            if not isinstance(raw_roles, list):
                continue
            try:
                roles = frozenset(ClusterRole(raw) for raw in raw_roles)
                assignment = RoleAssignment(
                    roles,
                    node_id=NodeId(item["node_id"]),
                    paused=bool(item.get("paused", False)),
                    revoked=bool(item.get("revoked", False)),
                    has_active_job=bool(item.get("has_active_job", True)),
                )
            except (TypeError, ValueError):
                continue
            if any(
                (
                    ClusterRole.SUBCOORDINATOR in current.roles
                    and ClusterRole.SUBCOORDINATOR in assignment.roles
                )
                or (
                    ClusterRole.COORDINATOR in current.roles
                    and ClusterRole.COORDINATOR in assignment.roles
                )
                for current in assignments
            ):
                continue
            assignments.append(assignment)
        return tuple(assignments) or _initial_roles(local_node_id)

    @staticmethod
    def _parse_epoch(value: Any) -> CoordinatorEpoch | None:
        if not isinstance(value, dict):
            return None
        try:
            epoch = int(value["epoch"])
            issued_at = float(value["issued_at"])
            expiry = float(value["lease_expires_at"])
            coordinator = value["coordinator_id"]
            token = value["fencing_token"]
            if not isinstance(coordinator, str) or not isinstance(token, str):
                return None
            return CoordinatorEpoch(
                epoch, NodeId(coordinator), token, issued_at, expiry
            )
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _parse_invites(value: Any) -> tuple[InviteRecord, ...]:
        if not isinstance(value, list):
            return ()
        records: list[InviteRecord] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            token_hash = item.get("token_hash")
            target = item.get("target_node_id", "")
            expiry = item.get("expires_at")
            if isinstance(token_hash, str) and isinstance(target, str) and isinstance(
                expiry, (int, float)
            ):
                try:
                    records.append(InviteRecord(token_hash, target, float(expiry)))
                except ValueError:
                    continue
        return tuple(records)

    @staticmethod
    def _parse_record(item: Any) -> TrustedNodeRecord | None:
        if not isinstance(item, dict):
            LOGGER.warning("Ignoring malformed trusted-node record")
            return None
        node_id = item.get("node_id")
        if not isinstance(node_id, str):
            LOGGER.warning("Ignoring trusted-node record without an id")
            return None
        for field in ("display_name", "hostname"):
            if not isinstance(item.get(field), str):
                LOGGER.warning("Ignoring malformed trusted-node record %s", node_id)
                return None
        host = item.get("host", "")
        if not isinstance(host, str):
            LOGGER.warning("Ignoring malformed trusted-node record %s", node_id)
            return None
        port = item.get("port")
        if port is not None and (
            not isinstance(port, int)
            or isinstance(port, bool)
            or not 0 <= port <= 65535
        ):
            LOGGER.warning("Ignoring malformed trusted-node port for %s", node_id)
            return None
        secret = item.get("secret")
        if not isinstance(secret, str) or not secret:
            LOGGER.warning("Ignoring trusted-node record without a secret: %s", node_id)
            return None
        capabilities_data = item.get("capabilities", [])
        capabilities: set[NodeCapability] = set()
        if isinstance(capabilities_data, list):
            for raw in capabilities_data:
                if isinstance(raw, str):
                    try:
                        capabilities.add(NodeCapability(raw))
                    except ValueError:
                        LOGGER.warning(
                            "Ignoring unknown capability %r for %s", raw, node_id
                        )
        platform = item.get("platform")
        if platform is not None and not isinstance(platform, str):
            platform = None
        color = item.get("color")
        if color is not None and not isinstance(color, str):
            color = None
        trusted_at = item.get("trusted_at")
        if not isinstance(trusted_at, (int, float)):
            trusted_at = time.time()
        return TrustedNodeRecord(
            node_id=node_id,
            display_name=item["display_name"],
            hostname=item["hostname"],
            platform=platform,
            color=color,
            host=host,
            port=port,
            capabilities=frozenset(capabilities),
            secret=secret,
            trusted_at=float(trusted_at),
            identity_fingerprint=(
                item.get("identity_fingerprint")
                if isinstance(item.get("identity_fingerprint"), str)
                else None
            ),
            transport_fingerprint=(
                item.get("transport_fingerprint")
                if isinstance(item.get("transport_fingerprint"), str)
                else None
            ),
            permissions=ClusterStore._parse_permissions(item.get("permissions")),
        )

    @staticmethod
    def _parse_permissions(value: Any) -> frozenset[NodePermission]:
        if value is None:
            return frozenset()
        if not isinstance(value, list):
            return frozenset()
        permissions: set[NodePermission] = set()
        for raw in value:
            if not isinstance(raw, str):
                return frozenset()
            try:
                permissions.add(NodePermission(raw))
            except ValueError:
                LOGGER.warning("Ignoring unknown node permission %r", raw)
                return frozenset()
        return frozenset(permissions)

    @staticmethod
    def _parse_grant(item: Any) -> PeerGrantRecord | None:
        if not isinstance(item, dict):
            LOGGER.warning("Ignoring malformed peer grant")
            return None
        caller = item.get("caller_node_id")
        secret = item.get("secret")
        if not isinstance(caller, str) or not caller:
            return None
        if not isinstance(secret, str) or len(secret) != 64:
            LOGGER.warning("Ignoring malformed peer grant for %s", caller)
            return None
        try:
            bytes.fromhex(secret)
        except ValueError:
            LOGGER.warning("Ignoring non-hex peer grant for %s", caller)
            return None
        raw_permissions = item.get("permissions")
        known_permissions = {permission.value for permission in NodePermission}
        if not isinstance(raw_permissions, list) or any(
            not isinstance(raw, str) or raw not in known_permissions
            for raw in raw_permissions
        ):
            LOGGER.warning("Ignoring malformed permissions for peer grant %s", caller)
            return None
        return PeerGrantRecord(
            caller_node_id=caller,
            secret=secret,
            permissions=frozenset(NodePermission(raw) for raw in raw_permissions),
        )

    @staticmethod
    def _serialize(state: ClusterState) -> str:
        payload: dict[str, Any] = {
            "schema_version": CLUSTER_SCHEMA_VERSION,
            "discovery_enabled": state.discovery_enabled,
            "local_node_id": state.local_node_id,
            "cluster_id": state.cluster_id,
            "role_assignments": [
                {
                    "node_id": item.node_id.value if item.node_id is not None else "",
                    "roles": sorted(role.value for role in item.roles),
                    "paused": item.paused,
                    "revoked": item.revoked,
                    "has_active_job": item.has_active_job,
                }
                for item in state.role_assignments
                if item.node_id is not None
            ],
            "coordinator_epoch": (
                {
                    "epoch": state.coordinator_epoch.epoch,
                    "coordinator_id": state.coordinator_epoch.coordinator_id.value,
                    "fencing_token": state.coordinator_epoch.fencing_token,
                    "issued_at": state.coordinator_epoch.issued_at,
                    "lease_expires_at": state.coordinator_epoch.lease_expires_at,
                }
                if state.coordinator_epoch is not None
                else None
            ),
            "active_invites": [
                {
                    "token_hash": invite.token_hash,
                    "target_node_id": invite.target_node_id,
                    "expires_at": invite.expires_at,
                }
                for invite in state.active_invites
            ],
            "promotion_epochs": sorted(state.promotion_epochs),
            "trusted_nodes": [
                {
                    "node_id": record.node_id,
                    "display_name": record.display_name,
                    "hostname": record.hostname,
                    "platform": record.platform,
                    "color": record.color,
                    "host": record.host,
                    "port": record.port,
                    "capabilities": sorted(
                        capability.value for capability in record.capabilities
                    ),
                    "secret": record.secret,
                    "trusted_at": record.trusted_at,
                    "identity_fingerprint": record.identity_fingerprint,
                    "transport_fingerprint": record.transport_fingerprint,
                    "permissions": sorted(
                        permission.value for permission in record.permissions
                    ),
                }
                for record in state.trusted_nodes
            ],
            "peer_grants": [
                {
                    "caller_node_id": grant.caller_node_id,
                    "secret": grant.secret,
                    "permissions": sorted(
                        permission.value for permission in grant.permissions
                    ),
                }
                for grant in state.peer_grants
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
