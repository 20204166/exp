"""Listening socket server fronting a ``RemoteService``.

``RemoteSocketServer`` runs one optional loopback/listening TCP server on its
own daemon thread with bounded admission; ``_handle_pairing_request`` serves
the unauthenticated, TLS-protected pairing handshake. Auth failures close the
connection silently, and every authorised response stays signed by the service.
"""

import json
import logging
import socketserver
import ssl
import threading
from collections.abc import Callable
from typing import Any

from maintenance.nodes import NodeId, NodePermission

from maintenance.remote_support.protocol import (
    DEFAULT_MAX_ACTIVE_HANDLERS,
    MAX_ENVELOPE_BYTES,
    PairingRequest,
    PeerGrant,
    RemoteProtocolError,
)
from maintenance.remote_support.transport import _recv_frame, _send_frame

LOGGER = logging.getLogger(__name__)


class RemoteSocketServer:
    """One optional loopback/listening TCP server fronting a ``RemoteService``.

    ``start``/``stop`` are idempotent; the server runs on its own daemon
    thread. Binding is to the caller-supplied host (loopback by default);
    exposing it on a LAN is an explicit, separate deployment decision.
    """

    def __init__(
        self,
        service: Any,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        timeout: float = 10.0,
        max_active_handlers: int = DEFAULT_MAX_ACTIVE_HANDLERS,
        ssl_context: ssl.SSLContext | None = None,
        pairing_handler: Callable[[PairingRequest], bool] | None = None,
    ) -> None:
        if max_active_handlers < 1:
            raise ValueError("max_active_handlers must be positive")
        self._service = service
        self._host = host
        self._port = port
        self._timeout = timeout
        self._max_active_handlers = max_active_handlers
        self._ssl_context = ssl_context
        self._pairing_handler = pairing_handler
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
            service: Any,
            admission: threading.BoundedSemaphore,
        ) -> type[socketserver.BaseRequestHandler]:
            class _Handler(socketserver.BaseRequestHandler):
                def handle(self) -> None:
                    request_socket = self.request
                    try:
                        try:
                            request_socket.settimeout(service_timeout)
                            if ssl_context is not None:
                                request_socket = ssl_context.wrap_socket(
                                    self.request, server_side=True
                                )
                            body = _recv_frame(
                                request_socket,
                                max_bytes=MAX_ENVELOPE_BYTES,
                                closed_message="connection closed before request",
                            )
                            text = body.decode("utf-8")
                            raw = json.loads(text)
                            if (
                                isinstance(raw, dict)
                                and raw.get("op") == "pair_request"
                            ):
                                response = _handle_pairing_request(raw, pairing_handler)
                            else:
                                response = service.handle(text)
                        except Exception:  # noqa: BLE001 - auth failures close silently.
                            return
                        payload = response.encode("utf-8")
                        _send_frame(
                            request_socket,
                            payload,
                            max_bytes=MAX_ENVELOPE_BYTES,
                        )
                    finally:
                        if request_socket is not self.request:
                            request_socket.close()
                        admission.release()

            return _Handler

        service_timeout = self._timeout
        ssl_context = self._ssl_context
        pairing_handler = self._pairing_handler

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

    def update_cluster_fence(
        self, *, cluster_id: str, coordinator_epoch: int, fencing_token: str
    ) -> None:
        self._service.update_cluster_fence(
            cluster_id=cluster_id,
            coordinator_epoch=coordinator_epoch,
            fencing_token=fencing_token,
        )


def _handle_pairing_request(
    raw: dict[str, Any], handler: Callable[[PairingRequest], bool] | None
) -> str:
    if handler is None or set(raw) != {
        "op",
        "caller_node_id",
        "identity_fingerprint",
        "transport_fingerprint",
        "secret",
        "permissions",
    }:
        return json.dumps({"approved": False, "error": "pairing_unavailable"})
    permissions = raw["permissions"]
    if not isinstance(permissions, list) or any(
        not isinstance(item, str) for item in permissions
    ):
        return json.dumps({"approved": False, "error": "invalid_pairing"})
    try:
        request = PairingRequest(
            caller_node_id=NodeId(raw["caller_node_id"]),
            identity_fingerprint=raw["identity_fingerprint"],
            transport_fingerprint=raw["transport_fingerprint"],
            proposed_secret=raw["secret"],
            permissions=frozenset(NodePermission(item) for item in permissions),
        )
        approved = handler(request)
    except (KeyError, TypeError, ValueError, RemoteProtocolError):
        approved = False
    return json.dumps(
        {"approved": bool(approved), "error": None if approved else "denied"}
    )