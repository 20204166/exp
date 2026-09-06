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
import json
import logging
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
    process_candidate_from_dict,
    process_candidate_to_dict,
    resource_summary_from_dict,
    resource_summary_to_dict,
)
from maintenance.models import ResourceSummary
from maintenance.nodes import (
    NodeCapability,
    NodeId,
    NodeSnapshot,
    NodeStatus,
)

LOGGER = logging.getLogger(__name__)

REMOTE_PROTOCOL_VERSION = "1"
MAX_ENVELOPE_BYTES = 8 * 1024 * 1024
DEFAULT_FRESHNESS_SECONDS = 60.0
DEFAULT_REPLAY_TTL_SECONDS = 300.0
DEFAULT_REPLAY_MAX_ENTRIES = 4096

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
}


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


@dataclass(frozen=True, slots=True)
class RemoteRequest:
    """One verified authenticated request from a peer node."""

    node_id: NodeId
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

    def check_and_record(
        self,
        node_id: str,
        request_id: str,
        nonce: str,
        seen_at: float,
    ) -> bool:
        key = (node_id, request_id, nonce)
        if key in self._seen:
            return False
        self._prune(seen_at)
        if len(self._seen) >= self._max_entries:
            self._prune(seen_at)
        self._seen[key] = seen_at
        return True

    def _prune(self, now: float) -> None:
        expired = [
            key
            for key, recorded_at in self._seen.items()
            if now - recorded_at > self._ttl
        ]
        for key in expired:
            del self._seen[key]

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
    signature = envelope.get("sig")
    if not isinstance(signature, str):
        raise RemoteAuthError("request is missing its signature")
    fields = {key: value for key, value in envelope.items() if key != "sig"}
    if not hmac.compare_digest(signature, _signature(secret, fields)):
        raise RemoteAuthError("request signature is invalid")
    node_id = envelope.get("node_id")
    op = envelope.get("op")
    params = envelope.get("params")
    request_id = envelope.get("request_id")
    nonce = envelope.get("nonce")
    timestamp = envelope.get("ts")
    if not isinstance(node_id, str) or not node_id:
        raise RemoteAuthError("request node_id is invalid")
    if not isinstance(op, str):
        raise RemoteProtocolError("request op must be a string")
    if not isinstance(params, dict):
        raise RemoteProtocolError("request params must be an object")
    if not isinstance(request_id, str) or not request_id:
        raise RemoteAuthError("request_id is invalid")
    if not isinstance(nonce, str) or not nonce:
        raise RemoteAuthError("request nonce is invalid")
    if not isinstance(timestamp, (int, float)):
        raise RemoteAuthError("request timestamp is invalid")
    now = clock()
    age = now - float(timestamp)
    if age > freshness_seconds or age < -freshness_seconds:
        raise RemoteAuthError("request timestamp is outside the freshness window")
    if not replay_cache.check_and_record(node_id, request_id, nonce, now):
        raise RemoteAuthError("request has been replayed")
    return RemoteRequest(
        node_id=NodeId(node_id),
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
    if not isinstance(node_id, str) or not isinstance(request_id, str):
        raise RemoteAuthError("response identity fields are invalid")
    if status not in ("ok", "error"):
        raise RemoteProtocolError("response status is invalid")
    if not isinstance(timestamp, (int, float)):
        raise RemoteAuthError("response timestamp is invalid")
    age = clock() - float(timestamp)
    if age > freshness_seconds or age < -freshness_seconds:
        raise RemoteAuthError("response timestamp is outside the freshness window")
    return RemoteResponse(
        node_id=NodeId(node_id),
        request_id=request_id,
        status=status,
        payload=envelope.get("payload"),
        error=envelope.get("error"),
        timestamp=float(timestamp),
    )


def validate_operation_params(op: str, params: dict[str, Any]) -> None:
    if op == "component_summary":
        key = params.get("key")
        if not isinstance(key, str) or not key:
            raise RemoteProtocolError("component_summary requires a key")
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
    ) -> None:
        self._node_id = node_id
        self._display_name = display_name
        self._hostname = hostname
        self._platform = platform
        self._status = status
        self._capabilities = capabilities
        self._provider = provider
        self._secret = secret
        self._app_version = app_version
        self._clock = clock
        self._freshness_seconds = freshness_seconds
        self._replay_cache = replay_cache or ReplayCache(clock=clock)

    def handle(self, envelope_text: str) -> str:
        try:
            envelope = json.loads(envelope_text)
        except (ValueError, TypeError) as error:
            raise RemoteProtocolError("envelope is not valid JSON") from error
        request = verify_request(
            envelope,
            secret=self._secret,
            clock=self._clock,
            freshness_seconds=self._freshness_seconds,
            replay_cache=self._replay_cache,
        )
        try:
            payload = self._solve(request)
        except RemoteProtocolError:
            raise
        except Exception as error:  # noqa: BLE001 - failures become signed errors.
            LOGGER.warning(
                "Remote operation %s failed on %s: %s",
                request.op,
                self._node_id,
                error,
            )
            response = sign_response(
                node_id=self._node_id.value,
                request_id=request.request_id,
                status="error",
                error=str(error),
                timestamp=self._clock(),
                secret=self._secret,
            )
            return json.dumps(response)
        response = sign_response(
            node_id=self._node_id.value,
            request_id=request.request_id,
            status="ok",
            payload=payload,
            timestamp=self._clock(),
            secret=self._secret,
        )
        return json.dumps(response)

    def _solve(self, request: RemoteRequest) -> dict[str, Any]:
        required = OP_REQUIRED_CAPABILITY.get(request.op)
        if required is None:
            raise RemoteProtocolError(f"unknown operation: {request.op}")
        if required not in self._capabilities:
            raise RemoteAuthorizationError(f"node is not authorised for {request.op}")
        validate_operation_params(request.op, request.params)
        if request.op == "hello":
            return {
                "ok": True,
                "node_id": self._node_id.value,
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
            return {"resource": resource_summary_to_dict(resource)}
        if request.op == "process_candidates":
            processes = self._provider.process_candidates()
            return {"processes": [process_candidate_to_dict(p) for p in processes]}
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

    def request(self, envelope_text: str) -> str:
        return self._service.handle(envelope_text)


def _recv_exact(sock: Any, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RemoteTransportError("connection closed before response")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class SocketRemoteTransport:
    """Length-prefixed JSON client for one TCP request/response exchange."""

    def __init__(self, host: str, port: int, *, timeout: float = 10.0) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout

    def request(self, envelope_text: str) -> str:
        data = envelope_text.encode("utf-8")
        if len(data) > MAX_ENVELOPE_BYTES:
            raise RemoteTransportError("request envelope is too large")
        try:
            with socket_module.create_connection(
                (self._host, self._port), timeout=self._timeout
            ) as sock:
                sock.settimeout(self._timeout)
                sock.sendall(struct.pack(">I", len(data)) + data)
                header = _recv_exact(sock, 4)
                length = struct.unpack(">I", header)[0]
                if length > MAX_ENVELOPE_BYTES:
                    raise RemoteTransportError("response envelope is too large")
                body = _recv_exact(sock, length)
        except RemoteTransportError:
            raise
        except OSError as error:
            raise RemoteTransportError(f"remote transport failed: {error}") from error
        return body.decode("utf-8")


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
    ) -> None:
        self._service = service
        self._host = host
        self._port = port
        self._server: Any = None
        self._thread: Any = None

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
        ) -> type[socketserver.BaseRequestHandler]:
            class _Handler(socketserver.BaseRequestHandler):
                def handle(self) -> None:
                    try:
                        header = _recv_exact(self.request, 4)
                        length = struct.unpack(">I", header)[0]
                        if length > MAX_ENVELOPE_BYTES:
                            return
                        body = _recv_exact(self.request, length)
                        response = service.handle(body.decode("utf-8"))
                    except Exception:  # noqa: BLE001 - auth failures close silently.
                        return
                    payload = response.encode("utf-8")
                    self.request.sendall(struct.pack(">I", len(payload)) + payload)

            return _Handler

        server = socketserver.ThreadingTCPServer(
            (self._host, self._port),
            make_handler(self._service),
        )
        server.daemon_threads = True
        server.allow_reuse_address = True
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
    ) -> None:
        self._node_id = node_id
        self._secret = secret
        self._transport = transport
        self._clock = clock
        self._freshness_seconds = freshness_seconds

    def hello(self) -> dict[str, Any]:
        return self._request("hello", {})

    def dashboard_snapshot(
        self,
        cancel_event: Any | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Any:
        self._check_cancel(cancel_event)
        payload = self._request("dashboard_snapshot", {})
        try:
            snapshot = node_snapshot_from_dict(payload["snapshot"])
        except (KeyError, ClusterDataError) as error:
            raise RemoteExecutionError("remote sent an invalid snapshot") from error
        if snapshot.dashboard is None:
            raise RemoteExecutionError("remote sent no dashboard data")
        return snapshot.dashboard

    def component_summary(
        self,
        key: str,
        cancel_event: Any | None = None,
    ) -> ResourceSummary:
        self._check_cancel(cancel_event)
        payload = self._request("component_summary", {"key": key})
        try:
            return resource_summary_from_dict(payload["resource"])
        except ClusterDataError as error:
            raise RemoteExecutionError("remote sent an invalid resource") from error

    def process_candidates(
        self,
        cancel_event: Any | None = None,
    ) -> list[Any]:
        self._check_cancel(cancel_event)
        payload = self._request("process_candidates", {})
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
        payload = self._request("storage_candidates", {})
        try:
            return [file_candidate_from_dict(item) for item in payload["files"]]
        except (KeyError, TypeError, ClusterDataError) as error:
            raise RemoteExecutionError("remote sent invalid storage data") from error

    def reset_component_sample(self, key: str) -> None:
        return None

    def stop_background_workers(self) -> None:
        return None

    def _check_cancel(self, cancel_event: Any | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise RemoteExecutionError("cancelled")

    def _request(self, op: str, params: dict[str, Any]) -> dict[str, Any]:
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
        )
        envelope_text = json.dumps(envelope)
        response_text = self._transport.request(envelope_text)
        response = verify_response(
            json.loads(response_text),
            secret=self._secret,
            clock=self._clock,
            freshness_seconds=self._freshness_seconds,
        )
        if response.node_id != self._node_id:
            raise RemoteAuthError("response came from the wrong node")
        if response.request_id != request_id:
            raise RemoteAuthError("response request id does not match")
        if response.status == "error":
            raise RemoteExecutionError(response.error or "remote operation failed")
        if response.payload is None:
            raise RemoteProtocolError("successful response has no payload")
        return response.payload
