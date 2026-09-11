"""Remote transport mechanics: in-process and socket transports.

``SocketRemoteTransport`` is the length-prefixed JSON client for one TCP
request/response exchange (TLS with optional certificate pinning);
``MemoryRemoteTransport`` hands envelopes straight to a ``RemoteService`` for
in-process/tests; ``build_trusted_transport`` derives a pinned client from a
persisted trusted-node record. Frame helpers are shared with the listening
server.
"""

import hmac
import socket as socket_module
import ssl
import struct
from collections.abc import Callable
from typing import Any

from maintenance.cluster import TrustedNodeRecord
from maintenance.remote_security import certificate_fingerprint

from maintenance.remote_support.protocol import (
    MAX_ENVELOPE_BYTES,
    RemoteAuthError,
    RemoteExecutionError,
    RemoteProtocolError,
    RemoteTransportError,
)


class MemoryRemoteTransport:
    """In-process transport that hands envelopes straight to a ``RemoteService``.

    Used by tests and by any in-app loopback path; the authentication and
    authorization checks run exactly as they would over a socket.
    """

    def __init__(self, service: Any) -> None:
        self._service = service

    def request(self, envelope_text: str, cancel_event: Any | None = None) -> str:
        return self._service.handle(envelope_text)


def _recv_exact(
    sock: Any,
    length: int,
    *,
    closed_message: str = "connection closed before response",
    cancel_event: Any | None = None,
) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        if cancel_event is not None and cancel_event.is_set():
            raise RemoteExecutionError("cancelled")
        try:
            chunk = sock.recv(remaining)
        except TimeoutError:
            if cancel_event is None:
                raise
            continue
        if not chunk:
            raise RemoteTransportError(closed_message)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_frame(
    sock: Any,
    *,
    max_bytes: int,
    closed_message: str,
    cancel_event: Any | None = None,
) -> bytes:
    header = _recv_exact(
        sock,
        4,
        closed_message=closed_message,
        cancel_event=cancel_event,
    )
    length = struct.unpack(">I", header)[0]
    if length > max_bytes:
        raise RemoteTransportError("envelope is too large")
    return _recv_exact(
        sock,
        length,
        closed_message=closed_message,
        cancel_event=cancel_event,
    )


def _send_frame(sock: Any, payload: bytes, *, max_bytes: int) -> None:
    if len(payload) > max_bytes:
        raise RemoteTransportError("envelope is too large")
    sock.sendall(struct.pack(">I", len(payload)) + payload)


class SocketRemoteTransport:
    """Length-prefixed JSON client for one TCP request/response exchange."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: float = 10.0,
        ssl_context: ssl.SSLContext | None = None,
        expected_fingerprint: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._ssl_context = ssl_context
        self._expected_fingerprint = expected_fingerprint

    def request(self, envelope_text: str, cancel_event: Any | None = None) -> str:
        data = envelope_text.encode("utf-8")
        if len(data) > MAX_ENVELOPE_BYTES:
            raise RemoteTransportError("request envelope is too large")
        wrapped_socket: Any | None = None
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise RemoteExecutionError("cancelled")
            connect_timeout = (
                min(self._timeout, 0.25) if cancel_event else self._timeout
            )
            with socket_module.create_connection(
                (self._host, self._port), timeout=connect_timeout
            ) as sock:
                if self._ssl_context is not None:
                    sock = self._ssl_context.wrap_socket(
                        sock, server_hostname=self._host
                    )
                    wrapped_socket = sock
                    certificate = sock.getpeercert(binary_form=True)
                    if certificate is None:
                        raise RemoteAuthError("peer certificate is missing")
                    fingerprint = certificate_fingerprint(certificate)
                    if (
                        self._expected_fingerprint is not None
                        and not hmac.compare_digest(
                            fingerprint, self._expected_fingerprint
                        )
                    ):
                        raise RemoteAuthError("peer certificate fingerprint changed")
                sock.settimeout(
                    min(self._timeout, 0.25) if cancel_event else self._timeout
                )
                _send_frame(sock, data, max_bytes=MAX_ENVELOPE_BYTES)
                body = _recv_frame(
                    sock,
                    max_bytes=MAX_ENVELOPE_BYTES,
                    closed_message="connection closed before response",
                    cancel_event=cancel_event,
                )
        except RemoteTransportError:
            raise
        except RemoteAuthError:
            raise
        except OSError as error:
            if cancel_event is not None and cancel_event.is_set():
                raise RemoteExecutionError("cancelled") from error
            raise RemoteTransportError(f"remote transport failed: {error}") from error
        finally:
            if wrapped_socket is not None:
                wrapped_socket.close()
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RemoteProtocolError("response is not valid UTF-8") from error


class TLSRemoteTransport(SocketRemoteTransport):
    """Socket transport with TLS encryption and optional certificate pinning."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        expected_fingerprint: str,
        timeout: float = 10.0,
    ) -> None:
        from maintenance.remote_security import client_context

        super().__init__(
            host,
            port,
            timeout=timeout,
            ssl_context=client_context(),
            expected_fingerprint=expected_fingerprint,
        )


def build_trusted_transport(
    record: TrustedNodeRecord,
    *,
    transport_cls: Callable[..., Any] = TLSRemoteTransport,
) -> Any:
    """Build a pinned transport from persisted trusted-node data."""

    if not record.host or record.port is None:
        raise RemoteAuthError("trusted peer has no complete endpoint")
    if not record.transport_fingerprint:
        raise RemoteAuthError("trusted peer has no pinned TLS fingerprint")
    return transport_cls(
        record.host,
        record.port,
        expected_fingerprint=record.transport_fingerprint,
    )