"""Versioned, HMAC-authenticated remote protocol envelope.

Owns the signed request/response envelope (``sign_request``/``sign_response``
and ``verify_request``/``verify_response``), the bounded replay cache, the
freshness window, the operation/role metadata tables, and the hello/operation
validation that never grants unknown capabilities. This is the shared wire
contract used by both the server-side ``RemoteService`` and the client-side
``AuthenticatedNodeProvider``.
"""

import hashlib
import hmac
import json
import math
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from maintenance.nodes import (
    READ_PERMISSIONS,
    NodeCapability,
    NodeId,
    NodePermission,
    ProcessActionKind,
)

REMOTE_PROTOCOL_VERSION = "1"
MAX_ENVELOPE_BYTES = 8 * 1024 * 1024
DEFAULT_FRESHNESS_SECONDS = 60.0
DEFAULT_REPLAY_TTL_SECONDS = 300.0
DEFAULT_REPLAY_MAX_ENTRIES = 4096
DEFAULT_MAX_ACTIVE_HANDLERS = 8

READ_CAPABILITIES = frozenset(
    {
        NodeCapability.DASHBOARD_READ,
        NodeCapability.COMPONENT_READ,
        NodeCapability.PROCESS_REVIEW,
        NodeCapability.STORAGE_REVIEW,
    }
)

OP_REQUIRED_CAPABILITY: dict[str, NodeCapability] = {
    "hello": NodeCapability.DASHBOARD_READ,
    "dashboard_snapshot": NodeCapability.DASHBOARD_READ,
    "component_summary": NodeCapability.COMPONENT_READ,
    "process_candidates": NodeCapability.PROCESS_REVIEW,
    "storage_candidates": NodeCapability.STORAGE_REVIEW,
    "process_request_quit": NodeCapability.PROCESS_TERMINATION,
    "process_force_quit": NodeCapability.PROCESS_FORCE_TERMINATION,
    "consume_invite": NodeCapability.REMOTE_MANAGEMENT,
    "assign_role": NodeCapability.REMOTE_MANAGEMENT,
    "renew_coordinator_lease": NodeCapability.REMOTE_MANAGEMENT,
    "worker_snapshot": NodeCapability.REMOTE_MANAGEMENT,
    "standby_batch": NodeCapability.REMOTE_MANAGEMENT,
    "pause_worker": NodeCapability.REMOTE_MANAGEMENT,
    "revoke_worker": NodeCapability.REMOTE_MANAGEMENT,
    "resume_worker": NodeCapability.REMOTE_MANAGEMENT,
}

OP_REQUIRED_PERMISSION: dict[str, NodePermission] = {
    operation: NodePermission(capability.value)
    for operation, capability in OP_REQUIRED_CAPABILITY.items()
}
OP_REQUIRED_PERMISSION.update(
    {
        "process_request_quit": NodePermission.PROCESS_TERMINATION,
        "process_force_quit": NodePermission.PROCESS_FORCE_TERMINATION,
        "consume_invite": NodePermission.REMOTE_MANAGEMENT,
        "assign_role": NodePermission.REMOTE_MANAGEMENT,
        "renew_coordinator_lease": NodePermission.REMOTE_MANAGEMENT,
        "worker_snapshot": NodePermission.REMOTE_MANAGEMENT,
        "standby_batch": NodePermission.REMOTE_MANAGEMENT,
        "pause_worker": NodePermission.REMOTE_MANAGEMENT,
        "revoke_worker": NodePermission.REMOTE_MANAGEMENT,
        "resume_worker": NodePermission.REMOTE_MANAGEMENT,
    }
)

ROLE_OPERATIONS = frozenset(
    {
        "consume_invite",
        "assign_role",
        "renew_coordinator_lease",
        "worker_snapshot",
        "standby_batch",
        "pause_worker",
        "revoke_worker",
        "resume_worker",
    }
)


class RemoteProtocolError(ValueError):
    """Raised for malformed or unsupported envelopes."""


class RemoteAuthError(RemoteProtocolError):
    """Raised when an envelope fails authentication or replay checks."""


class RemoteAuthorizationError(RemoteProtocolError):
    """Raised when a node is not authorised for the requested operation."""


class RemoteExecutionError(RuntimeError):
    """Raised when the authenticated peer reports an execution failure."""


class RemoteTransportError(RuntimeError):
    """Raised when the transport cannot complete an authenticated exchange."""


class RemoteUnavailableError(RemoteExecutionError):
    """Raised when the authenticated target cannot currently perform an action."""


def parse_hello_capabilities(payload: Any) -> frozenset[NodeCapability]:
    """Decode advertised capabilities without granting unknown values."""

    if not isinstance(payload, dict):
        raise RemoteProtocolError("hello payload must be an object")
    raw_capabilities = payload.get("capabilities", [])
    if not isinstance(raw_capabilities, list):
        raise RemoteProtocolError("hello capabilities must be a list")
    capabilities: set[NodeCapability] = set()
    for raw in raw_capabilities:
        if not isinstance(raw, str):
            raise RemoteProtocolError("hello capability must be a string")
        try:
            capabilities.add(NodeCapability(raw))
        except ValueError:
            # Unknown values are forward metadata, never permissions.
            continue
    return frozenset(capabilities)


def validate_hello_payload(
    payload: Any, *, expected_node_id: NodeId | None = None
) -> frozenset[NodeCapability]:
    """Validate the security-bearing portion of a hello response."""

    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RemoteProtocolError("hello response is invalid")
    if (
        payload.get("protocol_version", REMOTE_PROTOCOL_VERSION)
        != REMOTE_PROTOCOL_VERSION
    ):
        raise RemoteProtocolError("unsupported remote protocol version")
    node_id = payload.get("node_id")
    if not isinstance(node_id, str) or not node_id:
        raise RemoteAuthError("hello node identity is invalid")
    if expected_node_id is not None and node_id != expected_node_id.value:
        raise RemoteAuthError("hello came from the wrong node")
    fingerprint = payload.get("identity_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise RemoteAuthError("hello identity fingerprint is missing")
    return parse_hello_capabilities(payload)


@dataclass(frozen=True, slots=True)
class PeerGrant:
    """Target-owned authorization grant for one authenticated caller."""

    caller_node_id: NodeId
    secret: str
    permissions: frozenset[NodePermission]


@dataclass(frozen=True, slots=True)
class PairingRequest:
    """Unauthenticated, TLS-protected request awaiting target approval."""

    caller_node_id: NodeId
    identity_fingerprint: str
    transport_fingerprint: str
    proposed_secret: str
    permissions: frozenset[NodePermission]

    def __post_init__(self) -> None:
        if not self.caller_node_id.value or not self.identity_fingerprint:
            raise RemoteAuthError("pairing identity is missing")
        if not self.transport_fingerprint:
            raise RemoteAuthError("pairing transport fingerprint is missing")
        _validate_secret(self.proposed_secret)
        if not self.permissions <= frozenset(READ_PERMISSIONS):
            raise RemoteAuthorizationError("pairing is read-only")


def _validate_secret(secret: str) -> None:
    if not isinstance(secret, str) or len(secret) != 64:
        raise ValueError("peer credentials must be 256-bit hex text")
    try:
        bytes.fromhex(secret)
    except ValueError as error:
        raise ValueError("peer credentials must be hexadecimal") from error


@dataclass(frozen=True, slots=True)
class RemoteRequest:
    """One verified authenticated request from a peer node."""

    node_id: NodeId
    caller_node_id: NodeId | None
    op: str
    params: dict[str, Any]
    request_id: str
    nonce: str
    timestamp: float


@dataclass(frozen=True, slots=True)
class RemoteResponse:
    """One verified authenticated response to a request."""

    node_id: NodeId
    request_id: str
    status: str
    payload: dict[str, Any] | None
    error: str | None
    timestamp: float


def _canonical(fields: dict[str, Any]) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))


def _signature(secret: str, fields: dict[str, Any]) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        _canonical(fields).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def sign_request(
    *,
    node_id: str,
    op: str,
    params: dict[str, Any],
    request_id: str,
    nonce: str,
    timestamp: float,
    secret: str,
    caller_node_id: str | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "v": REMOTE_PROTOCOL_VERSION,
        "node_id": node_id,
        "op": op,
        "params": params,
        "request_id": request_id,
        "nonce": nonce,
        "ts": timestamp,
    }
    if caller_node_id is not None:
        fields["caller_node_id"] = caller_node_id
    envelope = dict(fields)
    envelope["sig"] = _signature(secret, fields)
    return envelope


def sign_response(
    *,
    node_id: str,
    request_id: str,
    status: str,
    secret: str,
    timestamp: float,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "v": REMOTE_PROTOCOL_VERSION,
        "node_id": node_id,
        "request_id": request_id,
        "status": status,
        "payload": payload,
        "error": error,
        "ts": timestamp,
    }
    envelope = dict(fields)
    envelope["sig"] = _signature(secret, fields)
    return envelope


class ReplayCache:
    """Bounded, expiry-pruned record of seen ``(node_id, request_id, nonce)``.

    One entry is kept per authenticated request and evicted after ``ttl`` or
    when the cache grows past ``max_entries``, so memory stays bounded while
    replayed requests are rejected for at least the freshness window.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: float = DEFAULT_REPLAY_TTL_SECONDS,
        max_entries: int = DEFAULT_REPLAY_MAX_ENTRIES,
    ) -> None:
        self._clock = clock
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._seen: dict[tuple[str, str, str], float] = {}
        self._request_ids: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def check_and_record(
        self,
        node_id: str,
        request_id: str,
        nonce: str,
        seen_at: float,
    ) -> bool:
        key = (node_id, request_id, nonce)
        with self._lock:
            self._prune(seen_at)
            if key in self._seen:
                return False
            if len(self._seen) >= self._max_entries:
                return False
            self._seen[key] = seen_at
            return True

    def _prune(self, now: float) -> None:
        expired = [
            key
            for key, recorded_at in self._seen.items()
            if now - recorded_at > self._ttl
        ]
        for replay_key in expired:
            del self._seen[replay_key]
        expired_ids = [
            request_key
            for request_key, recorded_at in self._request_ids.items()
            if now - recorded_at > self._ttl
        ]
        for request_key in expired_ids:
            del self._request_ids[request_key]

    def check_and_record_request_id(
        self, node_id: str, request_id: str, seen_at: float
    ) -> bool:
        """Reject destructive request-ID reuse even when its nonce is fresh."""

        with self._lock:
            self._prune(seen_at)
            key = (node_id, request_id)
            if key in self._request_ids:
                return False
            if len(self._request_ids) >= self._max_entries:
                return False
            self._request_ids[key] = seen_at
            return True

    def __len__(self) -> int:
        return len(self._seen)


def verify_request(
    envelope: Any,
    *,
    secret: str,
    clock: Callable[[], float],
    freshness_seconds: float,
    replay_cache: ReplayCache,
) -> RemoteRequest:
    if not isinstance(envelope, dict):
        raise RemoteProtocolError("request envelope must be an object")
    if envelope.get("v") != REMOTE_PROTOCOL_VERSION:
        raise RemoteProtocolError("unsupported remote protocol version")
    allowed_fields = {
        "v",
        "node_id",
        "caller_node_id",
        "op",
        "params",
        "request_id",
        "nonce",
        "ts",
        "sig",
    }
    if not set(envelope) <= allowed_fields or "sig" not in envelope:
        raise RemoteProtocolError("request envelope fields are invalid")
    signature = envelope.get("sig")
    if not isinstance(signature, str):
        raise RemoteAuthError("request is missing its signature")
    fields = {key: value for key, value in envelope.items() if key != "sig"}
    if not hmac.compare_digest(signature, _signature(secret, fields)):
        raise RemoteAuthError("request signature is invalid")
    node_id = envelope.get("node_id")
    caller_node_id = envelope.get("caller_node_id")
    op = envelope.get("op")
    params = envelope.get("params")
    request_id = envelope.get("request_id")
    nonce = envelope.get("nonce")
    timestamp = envelope.get("ts")
    if not isinstance(node_id, str) or not node_id:
        raise RemoteAuthError("request node_id is invalid")
    if caller_node_id is not None and (
        not isinstance(caller_node_id, str) or not caller_node_id
    ):
        raise RemoteAuthError("request caller_node_id is invalid")
    if not isinstance(op, str):
        raise RemoteProtocolError("request op must be a string")
    if not isinstance(params, dict):
        raise RemoteProtocolError("request params must be an object")
    if not isinstance(request_id, str) or not request_id:
        raise RemoteAuthError("request_id is invalid")
    if not isinstance(nonce, str) or not nonce:
        raise RemoteAuthError("request nonce is invalid")
    if (
        not isinstance(timestamp, (int, float))
        or isinstance(timestamp, bool)
        or not math.isfinite(timestamp)
    ):
        raise RemoteAuthError("request timestamp is invalid")
    now = clock()
    age = now - float(timestamp)
    if age > freshness_seconds or age < -freshness_seconds:
        raise RemoteAuthError("request timestamp is outside the freshness window")
    if not replay_cache.check_and_record(node_id, request_id, nonce, now):
        raise RemoteAuthError("request has been replayed")
    return RemoteRequest(
        node_id=NodeId(node_id),
        caller_node_id=(NodeId(caller_node_id) if caller_node_id else None),
        op=op,
        params=params,
        request_id=request_id,
        nonce=nonce,
        timestamp=float(timestamp),
    )


def verify_response(
    envelope: Any,
    *,
    secret: str,
    clock: Callable[[], float],
    freshness_seconds: float,
) -> RemoteResponse:
    if not isinstance(envelope, dict):
        raise RemoteProtocolError("response envelope must be an object")
    if envelope.get("v") != REMOTE_PROTOCOL_VERSION:
        raise RemoteProtocolError("unsupported remote protocol version")
    allowed_fields = {
        "v",
        "node_id",
        "request_id",
        "status",
        "payload",
        "error",
        "ts",
        "sig",
    }
    if not set(envelope) <= allowed_fields or "sig" not in envelope:
        raise RemoteProtocolError("response envelope fields are invalid")
    signature = envelope.get("sig")
    if not isinstance(signature, str):
        raise RemoteAuthError("response is missing its signature")
    fields = {key: value for key, value in envelope.items() if key != "sig"}
    if not hmac.compare_digest(signature, _signature(secret, fields)):
        raise RemoteAuthError("response signature is invalid")
    node_id = envelope.get("node_id")
    request_id = envelope.get("request_id")
    status = envelope.get("status")
    timestamp = envelope.get("ts")
    if (
        not isinstance(node_id, str)
        or not node_id
        or not isinstance(request_id, str)
        or not request_id
    ):
        raise RemoteAuthError("response identity fields are invalid")
    if status not in ("ok", "error"):
        raise RemoteProtocolError("response status is invalid")
    payload = envelope.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise RemoteProtocolError("response payload must be an object or null")
    error = envelope.get("error")
    if error is not None and not isinstance(error, str):
        raise RemoteProtocolError("response error must be a string or null")
    if (
        not isinstance(timestamp, (int, float))
        or isinstance(timestamp, bool)
        or not math.isfinite(timestamp)
    ):
        raise RemoteAuthError("response timestamp is invalid")
    age = clock() - float(timestamp)
    if age > freshness_seconds or age < -freshness_seconds:
        raise RemoteAuthError("response timestamp is outside the freshness window")
    return RemoteResponse(
        node_id=NodeId(node_id),
        request_id=request_id,
        status=status,
        payload=payload,
        error=error,
        timestamp=float(timestamp),
    )


def validate_operation_params(op: str, params: dict[str, Any]) -> None:
    if op not in OP_REQUIRED_CAPABILITY:
        raise RemoteProtocolError(f"unknown operation: {op}")
    if op == "component_summary":
        key = params.get("key")
        if not isinstance(key, str) or not key:
            raise RemoteProtocolError("component_summary requires a key")
        return
    if op in {"process_request_quit", "process_force_quit"}:
        processes = params.get("processes")
        if not isinstance(processes, list) or not processes:
            raise RemoteProtocolError(f"{op} requires process references")
        for item in processes:
            if not isinstance(item, dict):
                raise RemoteProtocolError("process reference must be an object")
            if (
                not isinstance(item.get("pid"), int)
                or isinstance(item.get("pid"), bool)
                or item["pid"] < 0
            ):
                raise RemoteProtocolError("process reference pid is invalid")
            create_time = item.get("create_time")
            if create_time is None or (
                not isinstance(create_time, (int, float))
                or isinstance(create_time, bool)
                or not math.isfinite(float(create_time))
                or float(create_time) < 0
            ):
                raise RemoteProtocolError("process reference create_time is required")
        expected_action = (
            ProcessActionKind.REQUEST_QUIT.value
            if op == "process_request_quit"
            else ProcessActionKind.FORCE_QUIT.value
        )
        if params.get("action") != expected_action:
            raise RemoteProtocolError("process action is not allowlisted")
        if set(params) != {"processes", "action"}:
            raise RemoteProtocolError(f"{op} has unexpected parameters")
        return
    if op in {
        "consume_invite",
        "assign_role",
        "renew_coordinator_lease",
        "worker_snapshot",
        "standby_batch",
        "pause_worker",
        "revoke_worker",
        "resume_worker",
    }:
        required = {"cluster_id", "epoch", "fencing_token"}
        if not required <= set(params):
            raise RemoteProtocolError(f"{op} requires cluster fencing fields")
        if not isinstance(params["cluster_id"], str) or not params["cluster_id"]:
            raise RemoteProtocolError("cluster_id is invalid")
        if (
            not isinstance(params["epoch"], int)
            or isinstance(params["epoch"], bool)
            or params["epoch"] < 0
        ):
            raise RemoteProtocolError("cluster epoch is invalid")
        if not isinstance(params["fencing_token"], str) or not params["fencing_token"]:
            raise RemoteProtocolError("fencing token is invalid")
        if op in {"renew_coordinator_lease", "consume_invite"}:
            if op == "consume_invite" and not isinstance(params.get("token"), str):
                raise RemoteProtocolError("invite token is invalid")
            return
        if op == "assign_role":
            if not isinstance(params.get("target_node_id"), str):
                raise RemoteProtocolError("role target is invalid")
            roles = params.get("roles")
            if not isinstance(roles, list) or not roles or any(
                not isinstance(role, str) for role in roles
            ):
                raise RemoteProtocolError("role list is invalid")
            return
        if op in {"pause_worker", "resume_worker", "revoke_worker"}:
            if not isinstance(params.get("target_node_id"), str):
                raise RemoteProtocolError("role target is invalid")
            return
        payload = params.get("payload")
        if not isinstance(payload, dict):
            raise RemoteProtocolError("snapshot payload is invalid")
        if len(json.dumps(payload, separators=(",", ":"))) > MAX_ENVELOPE_BYTES // 2:
            raise RemoteProtocolError("snapshot payload is too large")
        return
    if params:
        raise RemoteProtocolError(f"{op} accepts no parameters")
