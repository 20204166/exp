"""Authenticated read contract for secure cluster management.

Owns the versioned, HMAC-authenticated request/response envelope, the
freshness window, the bounded replay cache, idempotent request IDs, read-only
authorization, the server-side ``RemoteService`` (validates and solves via an
injected provider), and the client-side ``AuthenticatedNodeProvider`` that
implements ``NodeProvider`` over an injectable ``RemoteTransport``.

The transport is injected so tests and the GUI never depend on sockets; a
concrete loopback ``RemoteSocketServer``/``SocketRemoteTransport`` pair is
provided for real manual-host connections. Live remote data features
(dashboard/process/storage browsing) remain intentionally deferred elsewhere:
this module provides the secure contract and provider infrastructure, not the
feature wiring.
"""

import hashlib
import hmac
import inspect
import json
import logging
import math
import secrets
import socket as socket_module
import socketserver
import struct
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from maintenance.cluster import (
    ClusterDataError,
    file_candidate_from_dict,
    file_candidate_to_dict,
    node_snapshot_from_dict,
    node_snapshot_to_dict,
    process_action_result_from_dict,
    process_action_result_to_dict,
    process_candidate_from_dict,
    process_candidate_to_dict,
    resource_summary_from_dict,
    resource_summary_to_dict,
)
from maintenance.models import ProcessActionResult, ProcessCandidate, ResourceSummary
from maintenance.nodes import (
    NodeCapability,
    NodeId,
    NodePermission,
    NodeSnapshot,
    NodeStatus,
    ProcessActionKind,
    ProcessRef,
    ProcessTerminationRequest,
    node_identity_fingerprint,
)

LOGGER = logging.getLogger(__name__)

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
}

OP_REQUIRED_PERMISSION: dict[str, NodePermission] = {
    operation: NodePermission(capability.value)
    for operation, capability in OP_REQUIRED_CAPABILITY.items()
}
OP_REQUIRED_PERMISSION.update(
    {
        "process_request_quit": NodePermission.PROCESS_TERMINATION,
        "process_force_quit": NodePermission.PROCESS_FORCE_TERMINATION,
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
    if params:
        raise RemoteProtocolError(f"{op} accepts no parameters")


class RemoteService:
    """Server-side boundary: verify, authorize, and solve one request.

    Serves one machine's read data through an injected ``NodeProvider``. Every
    response is signed with the peer's secret, so a client can always tell an
    authentic denial from a forgery. Auth failures raise (the transport closes
    silently); authorised-but-failed executions return a signed error envelope.
    """

    def __init__(
        self,
        *,
        node_id: NodeId,
        display_name: str,
        hostname: str,
        platform: str | None,
        status: NodeStatus,
        capabilities: frozenset[NodeCapability],
        provider: Any,
        secret: str,
        app_version: str = "",
        clock: Callable[[], float] = time.time,
        freshness_seconds: float = DEFAULT_FRESHNESS_SECONDS,
        replay_cache: ReplayCache | None = None,
        permissions: frozenset[NodePermission] | None = None,
        process_manager: Any | None = None,
        expected_caller_id: NodeId | None = None,
        grants: dict[NodeId, PeerGrant] | None = None,
        identity_fingerprint: str | None = None,
    ) -> None:
        self._node_id = node_id
        self._display_name = display_name
        self._hostname = hostname
        self._platform = platform
        self._status = status
        self._capabilities = capabilities
        self._provider = provider
        self._process_manager = process_manager
        self._expected_caller_id = expected_caller_id
        self._identity_fingerprint = identity_fingerprint or node_identity_fingerprint(
            node_id
        )
        _validate_secret(secret)
        self._secret = secret
        self._grant_mode = grants is not None
        self._grant_lock = threading.RLock()
        self._grants = dict(grants or {})
        for grant in self._grants.values():
            _validate_secret(grant.secret)
        self._app_version = app_version
        self._clock = clock
        self._freshness_seconds = freshness_seconds
        self._replay_cache = (
            replay_cache if replay_cache is not None else ReplayCache(clock=clock)
        )
        self._permissions = (
            frozenset(permissions)
            if permissions is not None
            else frozenset(
                permission
                for permission in NodePermission
                if permission.value in {capability.value for capability in capabilities}
                and permission
                not in {
                    NodePermission.PROCESS_TERMINATION,
                    NodePermission.PROCESS_FORCE_TERMINATION,
                    NodePermission.CLEANUP,
                }
            )
        )

    def handle(self, envelope_text: str) -> str:
        try:
            envelope = json.loads(envelope_text)
        except (ValueError, TypeError) as error:
            raise RemoteProtocolError("envelope is not valid JSON") from error
        caller_node_id = self._caller_from_json(envelope)
        credential = self._secret
        grant: PeerGrant | None = None
        with self._grant_lock:
            if self._grant_mode:
                if caller_node_id is None:
                    raise RemoteAuthError("request caller identity is required")
                grant = self._grants.get(caller_node_id)
                if grant is None:
                    raise RemoteAuthError("request caller identity is unknown")
                credential = grant.secret
        request = verify_request(
            envelope,
            secret=credential,
            clock=self._clock,
            freshness_seconds=self._freshness_seconds,
            replay_cache=self._replay_cache,
        )
        response_secret = grant.secret if grant is not None else self._secret
        if (
            self._expected_caller_id is not None
            and request.caller_node_id != self._expected_caller_id
        ):
            raise RemoteAuthError("request caller identity is invalid")
        if request.node_id != self._node_id:
            raise RemoteAuthError("request target identity is invalid")
        if request.op in {
            "process_request_quit",
            "process_force_quit",
        } and not self._replay_cache.check_and_record_request_id(
            request.node_id.value, request.request_id, self._clock()
        ):
            raise RemoteAuthError("destructive request_id has already been used")
        try:
            payload = self._solve(request, grant=grant)
        except RemoteAuthorizationError as error:
            response = sign_response(
                node_id=self._node_id.value,
                request_id=request.request_id,
                status="error",
                error=(
                    "capability_unavailable"
                    if "not authorised" in str(error)
                    else "permission_denied"
                ),
                timestamp=self._clock(),
                secret=response_secret,
            )
            return json.dumps(response)
        except RemoteUnavailableError:
            response = sign_response(
                node_id=self._node_id.value,
                request_id=request.request_id,
                status="error",
                error="target_offline",
                timestamp=self._clock(),
                secret=response_secret,
            )
            return json.dumps(response)
        except RemoteProtocolError:
            raise
        except Exception:  # noqa: BLE001 - failures become stable signed errors.
            LOGGER.warning(
                "Remote operation %s failed on %s",
                request.op,
                self._node_id,
            )
            response = sign_response(
                node_id=self._node_id.value,
                request_id=request.request_id,
                status="error",
                error="execution_failed",
                timestamp=self._clock(),
                secret=response_secret,
            )
            return json.dumps(response)
        response = sign_response(
            node_id=self._node_id.value,
            request_id=request.request_id,
            status="ok",
            payload=payload,
            timestamp=self._clock(),
            secret=response_secret,
        )
        return json.dumps(response)

    def update_grants(self, grants: dict[NodeId, PeerGrant]) -> None:
        """Replace the live target ACL after an atomic settings update."""

        validated = dict(grants)
        for grant in validated.values():
            _validate_secret(grant.secret)
        with self._grant_lock:
            self._grant_mode = True
            self._grants = validated

    @staticmethod
    def _caller_from_json(envelope: Any) -> NodeId | None:
        if not isinstance(envelope, dict):
            return None
        caller = envelope.get("caller_node_id")
        return NodeId(caller) if isinstance(caller, str) and caller else None

    def _solve(
        self, request: RemoteRequest, *, grant: PeerGrant | None = None
    ) -> dict[str, Any]:
        required = OP_REQUIRED_CAPABILITY.get(request.op)
        if required is None:
            raise RemoteProtocolError(f"unknown operation: {request.op}")
        if required not in self._capabilities:
            raise RemoteAuthorizationError(f"node is not authorised for {request.op}")
        permission = OP_REQUIRED_PERMISSION[request.op]
        permissions = grant.permissions if grant is not None else self._permissions
        if permission not in permissions:
            raise RemoteAuthorizationError(f"caller lacks permission for {request.op}")
        validate_operation_params(request.op, request.params)
        if request.op == "hello":
            return {
                "ok": True,
                "node_id": self._node_id.value,
                "identity_fingerprint": self._identity_fingerprint,
                "protocol_version": REMOTE_PROTOCOL_VERSION,
                "app_version": self._app_version,
                "capabilities": sorted(
                    capability.value for capability in self._capabilities
                ),
            }
        if request.op == "dashboard_snapshot":
            snapshot = self._dashboard_snapshot()
            return {"snapshot": node_snapshot_to_dict(snapshot)}
        if request.op == "component_summary":
            resource = self._provider.component_summary(request.params["key"])
            return {
                "node_id": self._node_id.value,
                "resource": resource_summary_to_dict(resource),
            }
        if request.op == "process_candidates":
            processes = self._provider.process_candidates()
            return {"processes": [process_candidate_to_dict(p) for p in processes]}
        if request.op in {"process_request_quit", "process_force_quit"}:
            if self._status is not NodeStatus.ONLINE:
                raise RemoteUnavailableError("target is offline")
            if self._process_manager is None:
                raise RemoteExecutionError("process actions are unavailable")
            refs = request.params["processes"]
            action_kind = ProcessActionKind(request.params["action"])
            termination = ProcessTerminationRequest(
                target_node_id=self._node_id,
                processes=tuple(
                    ProcessRef(
                        node_id=self._node_id,
                        pid=int(item["pid"]),
                        create_time=float(item["create_time"]),
                    )
                    for item in refs
                ),
                action=action_kind,
            )
            if hasattr(self._process_manager, "terminate"):
                result = self._process_manager.terminate(termination)
            else:
                pids = [process.pid for process in termination.processes]
                create_times = {
                    process.pid: process.create_time
                    for process in termination.processes
                    if process.create_time is not None
                }
                action = (
                    self._process_manager.force_quit
                    if action_kind is ProcessActionKind.FORCE_QUIT
                    else self._process_manager.request_quit
                )
                result = action(pids, create_times)
            if not isinstance(result, ProcessActionResult):
                raise RemoteExecutionError("target returned an invalid action result")
            return process_action_result_to_dict(result)
        if request.op == "storage_candidates":
            candidates = self._provider.storage_candidates()
            return {"files": [file_candidate_to_dict(c) for c in candidates]}
        raise RemoteProtocolError(f"unknown operation: {request.op}")

    def _dashboard_snapshot(self) -> NodeSnapshot:
        dashboard = self._provider.dashboard_snapshot()
        return NodeSnapshot(
            node_id=self._node_id,
            display_name=self._display_name,
            hostname=self._hostname,
            platform=self._platform,
            status=self._status,
            capabilities=self._capabilities,
            scanned_at=dashboard.scanned_at,
            dashboard=dashboard,
        )


class MemoryRemoteTransport:
    """In-process transport that hands envelopes straight to a ``RemoteService``.

    Used by tests and by any in-app loopback path; the authentication and
    authorization checks run exactly as they would over a socket.
    """

    def __init__(self, service: RemoteService) -> None:
        self._service = service

    def request(self, envelope_text: str, cancel_event: Any | None = None) -> str:
        return self._service.handle(envelope_text)


def _recv_exact(
    sock: Any,
    length: int,
    *,
    closed_message: str = "connection closed before response",
) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RemoteTransportError(closed_message)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_frame(sock: Any, *, max_bytes: int, closed_message: str) -> bytes:
    header = _recv_exact(sock, 4, closed_message=closed_message)
    length = struct.unpack(">I", header)[0]
    if length > max_bytes:
        raise RemoteTransportError("envelope is too large")
    return _recv_exact(sock, length, closed_message=closed_message)


def _send_frame(sock: Any, payload: bytes, *, max_bytes: int) -> None:
    if len(payload) > max_bytes:
        raise RemoteTransportError("envelope is too large")
    sock.sendall(struct.pack(">I", len(payload)) + payload)


class SocketRemoteTransport:
    """Length-prefixed JSON client for one TCP request/response exchange."""

    def __init__(self, host: str, port: int, *, timeout: float = 10.0) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout

    def request(self, envelope_text: str, cancel_event: Any | None = None) -> str:
        data = envelope_text.encode("utf-8")
        if len(data) > MAX_ENVELOPE_BYTES:
            raise RemoteTransportError("request envelope is too large")
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise RemoteExecutionError("cancelled")
            connect_timeout = (
                min(self._timeout, 0.25) if cancel_event else self._timeout
            )
            with socket_module.create_connection(
                (self._host, self._port), timeout=connect_timeout
            ) as sock:
                sock.settimeout(
                    min(self._timeout, 0.25) if cancel_event else self._timeout
                )
                _send_frame(sock, data, max_bytes=MAX_ENVELOPE_BYTES)
                if cancel_event is None:
                    body = _recv_frame(
                        sock,
                        max_bytes=MAX_ENVELOPE_BYTES,
                        closed_message="connection closed before response",
                    )
                else:
                    header = _recv_exact_with_cancel(sock, 4, cancel_event)
                    length = struct.unpack(">I", header)[0]
                    if length > MAX_ENVELOPE_BYTES:
                        raise RemoteTransportError("envelope is too large")
                    body = _recv_exact_with_cancel(sock, length, cancel_event)
        except RemoteTransportError:
            raise
        except OSError as error:
            if cancel_event is not None and cancel_event.is_set():
                raise RemoteExecutionError("cancelled") from error
            raise RemoteTransportError(f"remote transport failed: {error}") from error
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RemoteProtocolError("response is not valid UTF-8") from error


def _recv_exact_with_cancel(sock: Any, length: int, cancel_event: Any) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        if cancel_event.is_set():
            raise RemoteExecutionError("cancelled")
        try:
            chunk = sock.recv(remaining)
        except TimeoutError:
            continue
        if not chunk:
            raise RemoteTransportError("connection closed before response")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class RemoteSocketServer:
    """One optional loopback/listening TCP server fronting a ``RemoteService``.

    ``start``/``stop`` are idempotent; the server runs on its own daemon
    thread. Binding is to the caller-supplied host (loopback by default);
    exposing it on a LAN is an explicit, separate deployment decision.
    """

    def __init__(
        self,
        service: RemoteService,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        timeout: float = 10.0,
        max_active_handlers: int = DEFAULT_MAX_ACTIVE_HANDLERS,
    ) -> None:
        if max_active_handlers < 1:
            raise ValueError("max_active_handlers must be positive")
        self._service = service
        self._host = host
        self._port = port
        self._timeout = timeout
        self._max_active_handlers = max_active_handlers
        self._server: Any = None
        self._thread: Any = None
        self._admission: threading.BoundedSemaphore | None = None

    @property
    def bound_port(self) -> int | None:
        if self._server is None:
            return None
        return int(self._server.server_address[1])

    def start(self) -> None:
        if self._server is not None:
            return

        def make_handler(
            service: RemoteService,
            admission: threading.BoundedSemaphore,
        ) -> type[socketserver.BaseRequestHandler]:
            class _Handler(socketserver.BaseRequestHandler):
                def handle(self) -> None:
                    try:
                        try:
                            self.request.settimeout(service_timeout)
                            body = _recv_frame(
                                self.request,
                                max_bytes=MAX_ENVELOPE_BYTES,
                                closed_message="connection closed before request",
                            )
                            response = service.handle(body.decode("utf-8"))
                        except Exception:  # noqa: BLE001 - auth failures close silently.
                            return
                        payload = response.encode("utf-8")
                        _send_frame(
                            self.request,
                            payload,
                            max_bytes=MAX_ENVELOPE_BYTES,
                        )
                    finally:
                        admission.release()

            return _Handler

        service_timeout = self._timeout

        class _Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            request_queue_size = 16

            def process_request(self, request: Any, client_address: Any) -> None:
                if not admission.acquire(blocking=False):
                    request.close()
                    return
                try:
                    super().process_request(request, client_address)
                except BaseException:
                    admission.release()
                    request.close()
                    raise

        admission = threading.BoundedSemaphore(self._max_active_handlers)
        self._admission = admission
        server = _Server(
            (self._host, self._port),
            make_handler(self._service, admission),
        )
        # A provider may not honour cooperative cancellation. Daemon handlers
        # and non-blocking close keep application shutdown bounded; idle and
        # malformed clients remain bounded by the socket timeout.
        server.daemon_threads = True
        server.block_on_close = False
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        server = self._server
        self._server = None
        self._thread = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:  # shutdown is best-effort.
                LOGGER.debug("Remote socket server shutdown failed", exc_info=True)
            server.server_close()

    def update_grants(self, grants: dict[NodeId, PeerGrant]) -> None:
        """Update authorization without restarting the listening socket."""

        self._service.update_grants(grants)


class AuthenticatedNodeProvider:
    """Client-side ``NodeProvider`` over one authenticated remote node.

    Builds and signs every request, verifies every response, enforces
    freshness and request-id correlation, and maps transport/auth failures to
    clear exceptions. ``reset_component_sample``/``stop_background_workers``
    are local-only concerns and are read-only no-ops here.
    """

    def __init__(
        self,
        *,
        node_id: NodeId,
        secret: str,
        transport: Any,
        clock: Callable[[], float] = time.time,
        freshness_seconds: float = DEFAULT_FRESHNESS_SECONDS,
        caller_node_id: NodeId | None = None,
    ) -> None:
        self._node_id = node_id
        self._caller_node_id = caller_node_id
        self._secret = secret
        self._transport = transport
        self._clock = clock
        self._freshness_seconds = freshness_seconds

    def hello(self, cancel_event: Any | None = None) -> dict[str, Any]:
        payload = self._request("hello", {}, cancel_event)
        validate_hello_payload(payload, expected_node_id=self._node_id)
        return payload

    def dashboard_snapshot(
        self,
        cancel_event: Any | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Any:
        self._check_cancel(cancel_event)
        payload = self._request("dashboard_snapshot", {}, cancel_event)
        try:
            snapshot = node_snapshot_from_dict(payload["snapshot"])
        except (KeyError, ClusterDataError) as error:
            raise RemoteExecutionError("remote sent an invalid snapshot") from error
        if snapshot.dashboard is None:
            raise RemoteExecutionError("remote sent no dashboard data")
        if snapshot.node_id != self._node_id:
            raise RemoteAuthError("remote snapshot came from the wrong node")
        return snapshot.dashboard

    def node_snapshot(
        self,
        cancel_event: Any | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> NodeSnapshot:
        self._check_cancel(cancel_event)
        payload = self._request("dashboard_snapshot", {}, cancel_event)
        try:
            snapshot = node_snapshot_from_dict(payload["snapshot"])
        except (KeyError, ClusterDataError) as error:
            raise RemoteExecutionError("remote sent an invalid snapshot") from error
        if snapshot.node_id != self._node_id:
            raise RemoteAuthError("remote snapshot came from the wrong node")
        return snapshot

    def component_summary(
        self,
        key: str,
        cancel_event: Any | None = None,
    ) -> ResourceSummary:
        self._check_cancel(cancel_event)
        payload = self._request("component_summary", {"key": key}, cancel_event)
        if payload.get("node_id") != self._node_id.value:
            raise RemoteAuthError("remote resource came from the wrong node")
        try:
            return resource_summary_from_dict(payload["resource"])
        except ClusterDataError as error:
            raise RemoteExecutionError("remote sent an invalid resource") from error

    def process_candidates(
        self,
        cancel_event: Any | None = None,
    ) -> list[ProcessCandidate]:
        self._check_cancel(cancel_event)
        payload = self._request("process_candidates", {}, cancel_event)
        try:
            return [process_candidate_from_dict(item) for item in payload["processes"]]
        except (KeyError, TypeError, ClusterDataError) as error:
            raise RemoteExecutionError("remote sent invalid process data") from error

    def storage_candidates(
        self,
        progress_callback: Callable[[str], None] | None = None,
        cancel_event: Any | None = None,
    ) -> list[Any]:
        self._check_cancel(cancel_event)
        payload = self._request("storage_candidates", {}, cancel_event)
        try:
            return [file_candidate_from_dict(item) for item in payload["files"]]
        except (KeyError, TypeError, ClusterDataError) as error:
            raise RemoteExecutionError("remote sent invalid storage data") from error

    def request_quit(self, refs: list[dict[str, Any]]) -> ProcessActionResult:
        return self.terminate(self._typed_request(refs, ProcessActionKind.REQUEST_QUIT))

    def force_quit(self, refs: list[dict[str, Any]]) -> ProcessActionResult:
        return self.terminate(self._typed_request(refs, ProcessActionKind.FORCE_QUIT))

    def terminate(self, request: ProcessTerminationRequest) -> ProcessActionResult:
        if request.target_node_id != self._node_id:
            raise RemoteAuthError("process request target does not match provider")
        return self._process_action(
            "process_request_quit"
            if request.action is ProcessActionKind.REQUEST_QUIT
            else "process_force_quit",
            {
                "action": request.action.value,
                "processes": [
                    {"pid": ref.pid, "create_time": ref.create_time}
                    for ref in request.processes
                ],
            },
        )

    def _typed_request(
        self, refs: list[dict[str, Any]], action: ProcessActionKind
    ) -> ProcessTerminationRequest:
        return ProcessTerminationRequest(
            target_node_id=self._node_id,
            processes=tuple(
                ProcessRef(
                    node_id=self._node_id,
                    pid=ref["pid"],
                    create_time=ref["create_time"],
                )
                for ref in refs
            ),
            action=action,
        )

    def _process_action(
        self, operation: str, refs: dict[str, Any]
    ) -> ProcessActionResult:
        payload = self._request(operation, refs)
        try:
            return process_action_result_from_dict(payload)
        except (ClusterDataError, TypeError, ValueError) as error:
            raise RemoteExecutionError(
                "remote sent invalid process action data"
            ) from error

    def reset_component_sample(self, key: str) -> None:
        return None

    def stop_background_workers(self) -> None:
        return None

    def _check_cancel(self, cancel_event: Any | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise RemoteExecutionError("cancelled")

    def _request(
        self,
        op: str,
        params: dict[str, Any],
        cancel_event: Any | None = None,
    ) -> dict[str, Any]:
        self._check_cancel(cancel_event)
        request_id = secrets.token_hex(16)
        nonce = secrets.token_hex(16)
        envelope = sign_request(
            node_id=self._node_id.value,
            op=op,
            params=params,
            request_id=request_id,
            nonce=nonce,
            timestamp=self._clock(),
            secret=self._secret,
            caller_node_id=(
                self._caller_node_id.value if self._caller_node_id is not None else None
            ),
        )
        envelope_text = json.dumps(envelope)
        request = self._transport.request
        try:
            inspect.signature(request).bind(envelope_text, cancel_event)
        except (TypeError, ValueError):
            response_text = request(envelope_text)
        else:
            response_text = request(envelope_text, cancel_event)
        try:
            response_envelope = json.loads(response_text)
        except (TypeError, ValueError) as error:
            raise RemoteProtocolError("response is not valid JSON") from error
        response = verify_response(
            response_envelope,
            secret=self._secret,
            clock=self._clock,
            freshness_seconds=self._freshness_seconds,
        )
        if response.node_id != self._node_id:
            raise RemoteAuthError("response came from the wrong node")
        if response.request_id != request_id:
            raise RemoteAuthError("response request id does not match")
        if response.status == "error":
            if response.error == "permission_denied":
                raise RemoteAuthorizationError("caller lacks permission")
            if response.error == "capability_unavailable":
                raise RemoteAuthorizationError("node capability is unavailable")
            if response.error == "target_offline":
                raise RemoteUnavailableError("target is offline")
            raise RemoteExecutionError(response.error or "remote operation failed")
        if response.payload is None:
            raise RemoteProtocolError("successful response has no payload")
        return response.payload


class RemoteProcessActionBackend:
    """Target-bound process action adapter over an authenticated provider."""

    def __init__(self, provider: AuthenticatedNodeProvider) -> None:
        self._provider = provider

    def request_quit(
        self,
        pids: list[int],
        expected_create_times: dict[int, float] | None = None,
    ) -> ProcessActionResult:
        return self._provider.request_quit(
            [
                {"pid": pid, "create_time": (expected_create_times or {}).get(pid)}
                for pid in pids
            ]
        )

    def force_quit(
        self,
        pids: list[int],
        expected_create_times: dict[int, float] | None = None,
    ) -> ProcessActionResult:
        return self._provider.force_quit(
            [
                {"pid": pid, "create_time": (expected_create_times or {}).get(pid)}
                for pid in pids
            ]
        )
