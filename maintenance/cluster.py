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

import contextlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    FileCandidate,
    ProcessCandidate,
    ResourceSummary,
)
from maintenance.nodes import (
    NODE_SNAPSHOT_SCHEMA_VERSION,
    NodeCapability,
    NodeId,
    NodeSnapshot,
    NodeStatus,
    generate_node_secret,
)
from maintenance.preferences import default_preferences_path

LOGGER = logging.getLogger(__name__)

CLUSTER_SCHEMA_VERSION = 1
CONFIG_FILE_NAME = "cluster.json"


class ClusterDataError(ValueError):
    """Raised when a serialized cluster value cannot be decoded safely."""


class ClusterSaveError(RuntimeError):
    """Raised when cluster settings could not be committed to disk."""


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
    return {
        "key": summary.key,
        "title": summary.title,
        "value": summary.value,
        "subtitle": summary.subtitle,
        "percent": summary.percent,
        "details": list(summary.details),
        "actionable": summary.actionable,
        "failed": summary.failed,
        "capability": summary.capability.value,
    }


def resource_summary_from_dict(data: Any) -> ResourceSummary:
    if not isinstance(data, dict):
        raise ClusterDataError("resource summary must be an object")
    key = data.get("key")
    if not isinstance(key, str):
        raise ClusterDataError("resource summary key must be a string")
    capability = data.get("capability", CapabilityState.UNKNOWN.value)
    try:
        state = CapabilityState(capability)
    except ValueError as error:
        raise ClusterDataError("resource summary has an unknown capability") from error
    details = data.get("details")
    if not isinstance(details, list) or not all(
        isinstance(item, str) for item in details
    ):
        raise ClusterDataError("resource summary details must be a string list")
    percent = data.get("percent")
    if percent is not None and not isinstance(percent, (int, float)):
        raise ClusterDataError("resource summary percent must be a number")
    for field in ("title", "value", "subtitle"):
        if not isinstance(data.get(field), str):
            raise ClusterDataError(f"resource summary {field} must be a string")
    for field in ("actionable", "failed"):
        if not isinstance(data.get(field), bool):
            raise ClusterDataError(f"resource summary {field} must be a boolean")
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
    }


def process_candidate_from_dict(data: Any) -> ProcessCandidate:
    if not isinstance(data, dict):
        raise ClusterDataError("process candidate must be an object")
    pid = data.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool):
        raise ClusterDataError("process candidate pid must be an integer")
    for field in ("name", "activity", "username"):
        if not isinstance(data.get(field), str):
            raise ClusterDataError(f"process candidate {field} must be a string")
    for field in ("memory_bytes", "memory_percent", "cpu_percent"):
        if not isinstance(data.get(field), (int, float)):
            raise ClusterDataError(f"process candidate {field} must be a number")
    create_time = data.get("create_time")
    if create_time is not None and not isinstance(create_time, (int, float)):
        raise ClusterDataError("process candidate create_time must be a number")
    return ProcessCandidate(
        pid=pid,
        name=data["name"],
        memory_bytes=int(data["memory_bytes"]),
        memory_percent=float(data["memory_percent"]),
        cpu_percent=float(data["cpu_percent"]),
        activity=data["activity"],
        username=data["username"],
        action_allowed=bool(data["action_allowed"]),
        create_time=cast(float | None, create_time),
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


@dataclass(frozen=True, slots=True)
class ClusterState:
    """The persisted cluster settings and trusted-node records."""

    discovery_enabled: bool = True
    trusted_nodes: tuple[TrustedNodeRecord, ...] = ()

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
        text = self._read_raw()
        if text is None:
            return ClusterState()
        return self._parse(text)

    def save(self, state: ClusterState) -> None:
        """Validate and persist ``state`` atomically.

        A uniquely named temporary file is written in the destination
        directory, flushed and fsynced, then committed with ``os.replace``.
        Runtime state must only be published by the caller after this returns.
        """

        payload = self._serialize(state)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ClusterSaveError(
                f"Cannot create cluster settings directory: {error}"
            ) from error

        temp_name: str | None = None
        try:
            fd, temp_name = tempfile.mkstemp(
                prefix=".cluster-",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            try:
                handle = os.fdopen(fd, "w", encoding="utf-8")
            except OSError:
                with contextlib.suppress(OSError):
                    os.close(fd)
                raise
            try:
                with handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
                temp_name = None
            finally:
                if temp_name is not None:
                    with contextlib.suppress(OSError):
                        os.unlink(temp_name)
        except OSError as error:
            raise ClusterSaveError(
                f"Failed to save cluster settings: {error}"
            ) from error

        self._fsync_directory()

    def _read_raw(self) -> str | None:
        try:
            return self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as error:
            LOGGER.warning("Failed to read cluster settings: %s", error)
            return None

    def _parse(self, text: str) -> ClusterState:
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            LOGGER.warning("Malformed cluster settings JSON; using defaults")
            return ClusterState()
        if not isinstance(data, dict):
            LOGGER.warning("Cluster settings root must be an object; using defaults")
            return ClusterState()
        if data.get("schema_version") != CLUSTER_SCHEMA_VERSION:
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
        return ClusterState(
            discovery_enabled=discovery,
            trusted_nodes=records,
        )

    @staticmethod
    def _parse_record(item: Any) -> TrustedNodeRecord | None:
        if not isinstance(item, dict):
            LOGGER.warning("Ignoring malformed trusted-node record")
            return None
        node_id = item.get("node_id")
        if not isinstance(node_id, str):
            LOGGER.warning("Ignoring trusted-node record without an id")
            return None
        for field in ("display_name", "hostname", "host"):
            if not isinstance(item.get(field), str):
                LOGGER.warning("Ignoring malformed trusted-node record %s", node_id)
                return None
        port = item.get("port")
        if port is not None and not isinstance(port, int):
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
            host=item["host"],
            port=port,
            capabilities=frozenset(capabilities),
            secret=secret,
            trusted_at=float(trusted_at),
        )

    @staticmethod
    def _serialize(state: ClusterState) -> str:
        payload: dict[str, Any] = {
            "schema_version": CLUSTER_SCHEMA_VERSION,
            "discovery_enabled": state.discovery_enabled,
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
                }
                for record in state.trusted_nodes
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    def _fsync_directory(self) -> None:
        if not hasattr(os, "O_DIRECTORY"):
            return
        try:
            dir_fd = os.open(
                self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            LOGGER.warning(
                "Cluster settings committed but directory fsync failed: %s",
                self.path.parent,
            )
        finally:
            with contextlib.suppress(OSError):
                os.close(dir_fd)
