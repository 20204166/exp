"""Tests for outbound endpoint selection and transport timeout behaviour.

Phase 12J — Outbound Endpoint Resolution + Trust Persistence.
Phase 12J-C — Cross-platform compatibility + regression gate.

Covers:
- _preferred_candidate_address selects the physical LAN address over VPN IPs
- SocketRemoteTransport uses full connect timeout, short poll for recv+cancel
- classify_peer_failure maps certificate/fingerprint errors to AUTHENTICATION_FAILED
- NodeRegistry.update_discovered rejects bogus/self/placeholder candidates
- Transport deadline enforced; cancellation responsive within ~0.25 s
"""

import socket
import struct
import threading
import time
import unittest
from typing import Literal, Self
from unittest.mock import patch

from maintenance.nodes import (
    LOCAL_NODE_ID,
    NodeRegistry,
    PeerFailure,
    classify_peer_failure,
)
from maintenance.remote_support.protocol import (
    RemoteExecutionError,
    RemoteTransportError,
)
from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT
from maintenance.remote_support.transport import SocketRemoteTransport, _recv_exact
from maintenance.ui.window_node_actions_impl.pairing import (
    _preferred_candidate_address,
)
from tests.support.nodes import make_candidate


class PreferredAddressTests(unittest.TestCase):
    """_preferred_candidate_address must prefer 192.168/16 over VPN ranges."""

    def test_single_lan_address_returned_unchanged(self) -> None:
        self.assertEqual(
            _preferred_candidate_address(["192.168.55.107"]), "192.168.55.107"
        )

    def test_192_168_preferred_over_10_x(self) -> None:
        self.assertEqual(
            _preferred_candidate_address(["10.0.0.1", "192.168.55.107"]),
            "192.168.55.107",
        )

    def test_192_168_preferred_over_vpn_100_64(self) -> None:
        self.assertEqual(
            _preferred_candidate_address(["100.64.0.1", "192.168.55.107"]),
            "192.168.55.107",
        )

    def test_10_x_preferred_over_vpn_100_64(self) -> None:
        self.assertEqual(
            _preferred_candidate_address(["100.64.0.1", "10.8.0.5"]),
            "10.8.0.5",
        )

    def test_172_16_preferred_over_10_x(self) -> None:
        self.assertEqual(
            _preferred_candidate_address(["10.0.0.1", "172.16.0.5"]),
            "172.16.0.5",
        )

    def test_vpn_address_returned_when_only_option(self) -> None:
        self.assertEqual(_preferred_candidate_address(["100.64.0.1"]), "100.64.0.1")

    def test_address_order_independent(self) -> None:
        addresses = ["100.64.0.1", "10.8.0.5", "192.168.55.107", "172.16.0.5"]
        result = _preferred_candidate_address(addresses)
        self.assertEqual(result, "192.168.55.107")

    def test_first_element_wins_when_ranks_are_equal(self) -> None:
        # Two 192.168 addresses — min() picks the lexicographically first one.
        result = _preferred_candidate_address(["192.168.55.107", "192.168.1.1"])
        self.assertEqual(result, "192.168.55.107")

    def test_non_ipv4_address_treated_as_lowest_preference(self) -> None:
        result = _preferred_candidate_address(["not.an.ip", "192.168.55.107"])
        self.assertEqual(result, "192.168.55.107")


class SocketTransportTimeoutTests(unittest.TestCase):
    """SocketRemoteTransport must use the full self._timeout even with cancel_event.

    The 0.25 s cap was removed in Phase 12J (it caused all coordinator-driven
    connect attempts to fail within ~0.26 s).
    """

    def _make_transport(self, timeout: float = 5.0) -> SocketRemoteTransport:
        return SocketRemoteTransport("127.0.0.1", 9, timeout=timeout)

    def test_full_timeout_used_for_connect_with_cancel_event(self) -> None:
        cancel_event = threading.Event()
        transport = self._make_transport(timeout=5.0)
        connect_calls: list[float] = []

        def fake_create_connection(addr: tuple, timeout: float) -> None:
            connect_calls.append(timeout)
            raise OSError("connection refused")

        with (
            patch(
                "maintenance.remote_support.transport.socket_module.create_connection",
                side_effect=fake_create_connection,
            ),
            self.assertRaises(RemoteTransportError),
        ):
            transport.request("x", cancel_event=cancel_event)

        self.assertEqual(len(connect_calls), 1)
        self.assertAlmostEqual(
            connect_calls[0],
            5.0,
            places=3,
            msg="connect timeout must equal self._timeout, not 0.25",
        )

    def test_full_timeout_used_without_cancel_event(self) -> None:
        transport = self._make_transport(timeout=10.0)
        connect_calls: list[float] = []

        def fake_create_connection(addr: tuple, timeout: float) -> None:
            connect_calls.append(timeout)
            raise OSError("connection refused")

        with (
            patch(
                "maintenance.remote_support.transport.socket_module.create_connection",
                side_effect=fake_create_connection,
            ),
            self.assertRaises(RemoteTransportError),
        ):
            transport.request("x", cancel_event=None)

        self.assertAlmostEqual(connect_calls[0], 10.0, places=3)

    def test_error_message_includes_exception_type(self) -> None:
        transport = self._make_transport()

        with (
            patch(
                "maintenance.remote_support.transport.socket_module.create_connection",
                side_effect=ConnectionRefusedError("Connection refused"),
            ),
            self.assertRaises(RemoteTransportError) as ctx,
        ):
            transport.request("x")

        msg = str(ctx.exception)
        self.assertIn(
            "ConnectionRefusedError",
            msg,
            "error message must include the exception type for diagnosis",
        )
        self.assertIn("Connection refused", msg)


class PeerFailureClassificationTests(unittest.TestCase):
    """classify_peer_failure must map TLS/certificate errors to AUTHENTICATION_FAILED."""

    def test_certificate_fingerprint_changed_is_auth_failure(self) -> None:
        self.assertIs(
            classify_peer_failure("peer certificate fingerprint changed"),
            PeerFailure.AUTHENTICATION_FAILED,
        )

    def test_certificate_missing_is_auth_failure(self) -> None:
        self.assertIs(
            classify_peer_failure("peer certificate is missing"),
            PeerFailure.AUTHENTICATION_FAILED,
        )

    def test_timeout_error_is_timeout(self) -> None:
        self.assertIs(
            classify_peer_failure("remote transport failed: TimeoutError: timed out"),
            PeerFailure.TIMEOUT,
        )

    def test_connection_refused_is_connection_refused(self) -> None:
        self.assertIs(
            classify_peer_failure(
                "remote transport failed: ConnectionRefusedError: [Errno 111] Connection refused"
            ),
            PeerFailure.CONNECTION_REFUSED,
        )

    def test_remote_auth_error_exception_type_is_auth_failure(self) -> None:
        from maintenance.remote_support.protocol import RemoteAuthError

        self.assertIs(
            classify_peer_failure(
                RemoteAuthError("peer certificate fingerprint changed")
            ),
            PeerFailure.AUTHENTICATION_FAILED,
        )


class AddressSelectionMatrixTests(unittest.TestCase):
    """Spec §10 / §11 / §12 / §13: full address-range coverage.

    All private ranges must work; VPN range must work as last resort.
    No range is "invalid" — ranking is preference only.
    """

    def test_case_a_192_168_only(self) -> None:
        self.assertEqual(_preferred_candidate_address(["192.168.1.5"]), "192.168.1.5")

    def test_case_b_10x_only(self) -> None:
        """10.x is a valid LAN range and must be returned when it is the only option."""
        self.assertEqual(_preferred_candidate_address(["10.0.0.1"]), "10.0.0.1")

    def test_case_c_172_16_only(self) -> None:
        self.assertEqual(_preferred_candidate_address(["172.16.5.1"]), "172.16.5.1")

    def test_case_d_100_64_plus_192_168(self) -> None:
        """CGNAT/VPN + LAN: LAN wins."""
        self.assertEqual(
            _preferred_candidate_address(["100.64.10.1", "192.168.1.5"]),
            "192.168.1.5",
        )

    def test_case_e_10x_plus_192_168(self) -> None:
        """10.x VPN-like + 192.168 LAN: 192.168 wins."""
        self.assertEqual(
            _preferred_candidate_address(["10.8.0.5", "192.168.1.5"]),
            "192.168.1.5",
        )

    def test_case_f_multiple_private_interfaces(self) -> None:
        """Multiple 192.168 addresses: one is returned (stable)."""
        result = _preferred_candidate_address(["192.168.55.1", "192.168.1.100"])
        self.assertIn(result, {"192.168.55.1", "192.168.1.100"})

    def test_case_g_ipv4_and_ipv6(self) -> None:
        """IPv6 address ranks lowest; IPv4 LAN wins."""
        result = _preferred_candidate_address(["::1", "192.168.1.5"])
        self.assertEqual(result, "192.168.1.5")

    def test_case_h_ipv6_only(self) -> None:
        """IPv6-only: must return the address, not crash."""
        result = _preferred_candidate_address(["2001:db8::1"])
        self.assertEqual(result, "2001:db8::1")

    def test_case_i_localhost_candidate(self) -> None:
        """Localhost ranks lowest; LAN wins when both present."""
        result = _preferred_candidate_address(["127.0.0.1", "192.168.1.5"])
        self.assertEqual(result, "192.168.1.5")

    def test_case_j_malformed_address_falls_back_gracefully(self) -> None:
        """Malformed address ranks lowest; valid address wins."""
        result = _preferred_candidate_address(["not.valid", "192.168.1.5"])
        self.assertEqual(result, "192.168.1.5")

    def test_10x_real_lan_preferred_over_100_64(self) -> None:
        """10.x as real LAN must be preferred over CGNAT/VPN 100.64."""
        self.assertEqual(
            _preferred_candidate_address(["100.64.1.1", "10.0.0.1"]),
            "10.0.0.1",
        )

    def test_172_31_is_valid_private(self) -> None:
        """172.31.x is within 172.16/12 and must be accepted as private."""
        self.assertEqual(_preferred_candidate_address(["172.31.0.1"]), "172.31.0.1")

    def test_100_64_returned_when_only_option(self) -> None:
        """CGNAT/VPN as sole address: must return it, not fail."""
        self.assertEqual(_preferred_candidate_address(["100.64.0.1"]), "100.64.0.1")


class SelfDiscoveryFilterTests(unittest.TestCase):
    """Spec §5 / §6: NodeRegistry must reject bogus and self candidates.

    Observation A (wheel 1.6.1.6): NodeId='local', port=0 appeared in the UI.
    These must be rejected at update_discovered, never presented.
    """

    def _registry(self, local_id: str = "node-real-abc123") -> NodeRegistry:
        from maintenance.nodes import NodeId

        registry = NodeRegistry()
        registry._local_id = NodeId(local_id)
        return registry

    def test_stable_id_local_placeholder_rejected(self) -> None:
        """stable_id='local' must NEVER appear as a remote peer."""
        registry = self._registry()
        candidate = make_candidate(stable_id=LOCAL_NODE_ID, port=0)
        result = registry.update_discovered(candidate)
        self.assertIsNone(result, "placeholder 'local' must be rejected")
        self.assertEqual(
            len(registry.discovered_candidates()),
            0,
            "placeholder must not enter discovered list",
        )

    def test_empty_stable_id_rejected(self) -> None:
        registry = self._registry()
        candidate = make_candidate(stable_id="", port=5000)
        result = registry.update_discovered(candidate)
        self.assertIsNone(result)
        self.assertEqual(len(registry.discovered_candidates()), 0)

    def test_port_zero_rejected(self) -> None:
        """port=0 is an invalid advertisement and must be rejected."""
        registry = self._registry()
        candidate = make_candidate(stable_id="peer-b", port=0)
        result = registry.update_discovered(candidate)
        self.assertIsNone(result)
        self.assertEqual(len(registry.discovered_candidates()), 0)

    def test_port_negative_rejected(self) -> None:
        registry = self._registry()
        candidate = make_candidate(stable_id="peer-b", port=-1)
        result = registry.update_discovered(candidate)
        self.assertIsNone(result)

    def test_port_out_of_range_rejected(self) -> None:
        registry = self._registry()
        candidate = make_candidate(stable_id="peer-b", port=65536)
        result = registry.update_discovered(candidate)
        self.assertIsNone(result)

    def test_self_node_id_rejected(self) -> None:
        """The local node's own stable_id must be filtered out."""
        registry = self._registry(local_id="node-real-abc123")
        candidate = make_candidate(
            stable_id="node-real-abc123", port=PEER_SERVICE_DEFAULT_PORT
        )
        result = registry.update_discovered(candidate)
        self.assertIsNone(result)
        self.assertEqual(len(registry.discovered_candidates()), 0)

    def test_valid_remote_candidate_accepted(self) -> None:
        registry = self._registry()
        candidate = make_candidate(
            stable_id="node-peer-xyz", port=PEER_SERVICE_DEFAULT_PORT
        )
        result = registry.update_discovered(candidate)
        self.assertIsNotNone(result)
        self.assertEqual(len(registry.discovered_candidates()), 1)

    def test_port_none_accepted_for_non_connectable(self) -> None:
        """port=None is valid for a non-connectable advertisement."""
        registry = self._registry()
        candidate = make_candidate(
            stable_id="node-peer-xyz", port=None, connectable=False
        )
        result = registry.update_discovered(candidate)
        self.assertIsNotNone(result)

    def test_valid_10x_candidate_accepted(self) -> None:
        """10.x addresses must not be rejected as VPN."""
        from maintenance.nodes import DiscoveredNodeCandidate

        registry = self._registry()
        candidate = DiscoveredNodeCandidate(
            stable_id="node-10x-peer",
            hostname="server-10",
            addresses=("10.0.0.5",),
            port=PEER_SERVICE_DEFAULT_PORT,
            service_name="node-10x-peer._tcp.local.",
            app_version="1.6.1.6",
            protocol_version="1",
            platform="Linux",
            connectable=True,
            compatible=True,
            last_seen=time.monotonic(),
        )
        result = registry.update_discovered(candidate)
        self.assertIsNotNone(result)

    def test_valid_172_16_candidate_accepted(self) -> None:
        from maintenance.nodes import DiscoveredNodeCandidate

        registry = self._registry()
        candidate = DiscoveredNodeCandidate(
            stable_id="node-172-peer",
            hostname="server-172",
            addresses=("172.20.0.5",),
            port=PEER_SERVICE_DEFAULT_PORT,
            service_name="node-172-peer._tcp.local.",
            app_version="1.6.1.6",
            protocol_version="1",
            platform="Linux",
            connectable=True,
            compatible=True,
            last_seen=time.monotonic(),
        )
        result = registry.update_discovered(candidate)
        self.assertIsNotNone(result)


class SocketTransportCancellationTests(unittest.TestCase):
    """Spec §7 / §8: cancellation semantics after removing the 0.25 s cap.

    connect() uses the full configured timeout.
    recv() polls with a short (0.25 s) interval when cancel_event is provided
    so cancellation is responsive, while the total budget is still self._timeout.
    """

    def _make_transport(self, timeout: float = 10.0) -> SocketRemoteTransport:
        return SocketRemoteTransport("127.0.0.1", 9, timeout=timeout)

    def test_recv_uses_short_poll_timeout_when_cancel_event_provided(self) -> None:
        cancel_event = threading.Event()
        transport = self._make_transport(timeout=10.0)
        settimeout_calls: list[float] = []

        class FakeSocket:
            def __enter__(self) -> Self:
                return self

            def __exit__(self, *_: object) -> Literal[False]:
                return False

            def settimeout(self, t: float) -> None:
                settimeout_calls.append(t)

            def sendall(self, _: bytes) -> None:
                pass

            def recv(self, _: int) -> bytes:
                cancel_event.set()
                raise TimeoutError

        with (
            patch(
                "maintenance.remote_support.transport.socket_module.create_connection",
                return_value=FakeSocket(),
            ),
            self.assertRaises(RemoteExecutionError),
        ):
            transport.request("x", cancel_event=cancel_event)

        self.assertTrue(
            any(abs(t - 0.25) < 0.01 for t in settimeout_calls),
            f"recv poll timeout must be ~0.25 s when cancel_event provided; got {settimeout_calls}",
        )
        self.assertFalse(
            any(abs(t - 10.0) < 0.01 for t in settimeout_calls),
            "full 10 s must not be used for per-recv timeout when cancel_event provided",
        )

    def test_recv_uses_full_timeout_without_cancel_event(self) -> None:
        transport = self._make_transport(timeout=7.0)
        settimeout_calls: list[float] = []

        class FakeSocket:
            def __enter__(self) -> Self:
                return self

            def __exit__(self, *_: object) -> Literal[False]:
                return False

            def settimeout(self, t: float) -> None:
                settimeout_calls.append(t)

            def sendall(self, _: bytes) -> None:
                raise OSError("abort")

        with (
            patch(
                "maintenance.remote_support.transport.socket_module.create_connection",
                return_value=FakeSocket(),
            ),
            self.assertRaises(RemoteTransportError),
        ):
            transport.request("x", cancel_event=None)

        self.assertTrue(
            any(abs(t - 7.0) < 0.01 for t in settimeout_calls),
            f"full timeout must be used for settimeout without cancel_event; got {settimeout_calls}",
        )

    def test_connect_still_uses_full_timeout_with_cancel_event(self) -> None:
        """Regression: connect must NOT be capped at 0.25 s even when cancel_event given."""
        cancel_event = threading.Event()
        transport = self._make_transport(timeout=5.0)
        connect_calls: list[float] = []

        def fake_connect(addr: tuple, timeout: float) -> None:
            connect_calls.append(timeout)
            raise OSError("refused")

        with (
            patch(
                "maintenance.remote_support.transport.socket_module.create_connection",
                side_effect=fake_connect,
            ),
            self.assertRaises(RemoteTransportError),
        ):
            transport.request("x", cancel_event=cancel_event)

        self.assertEqual(len(connect_calls), 1)
        self.assertAlmostEqual(
            connect_calls[0],
            5.0,
            places=3,
            msg="connect must use full timeout even when cancel_event is present",
        )

    def test_deadline_enforced_during_prolonged_recv(self) -> None:
        """Total operation time must not exceed configured timeout significantly."""
        cancel_event = threading.Event()
        transport = self._make_transport(timeout=0.35)
        start = time.monotonic()

        class SlowSocket:
            def __enter__(self) -> Self:
                return self

            def __exit__(self, *_: object) -> Literal[False]:
                return False

            def settimeout(self, _: float) -> None:
                pass

            def sendall(self, _: bytes) -> None:
                pass

            def recv(self, _: int) -> bytes:
                time.sleep(0.12)
                raise TimeoutError

        with (
            patch(
                "maintenance.remote_support.transport.socket_module.create_connection",
                return_value=SlowSocket(),
            ),
            self.assertRaises(
                (TimeoutError, RemoteTransportError, RemoteExecutionError)
            ),
        ):
            transport.request("x", cancel_event=cancel_event)

        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.5, "deadline must terminate loop; got long wait")

    def test_cancel_before_connect_raises_immediately(self) -> None:
        cancel_event = threading.Event()
        cancel_event.set()
        transport = self._make_transport()

        with self.assertRaises(RemoteExecutionError):
            transport.request("x", cancel_event=cancel_event)

    def test_recv_exact_deadline_check(self) -> None:
        """_recv_exact raises TimeoutError when deadline has already passed."""
        past_deadline = time.monotonic() - 1.0

        class NeverResponds:
            def recv(self, _: int) -> bytes:
                raise AssertionError("recv should not be called after deadline")

        with self.assertRaises(TimeoutError):
            _recv_exact(
                NeverResponds(),
                4,
                closed_message="test",
                cancel_event=threading.Event(),
                deadline=past_deadline,
            )


class SocketTransportRealSocketTests(unittest.TestCase):
    """Spec §9: real-socket matrix — the critical regression is that a legitimate
    response arriving after 0.25 s must now SUCCEED (old cap would fail it)."""

    @staticmethod
    def _echo_server(
        delay_s: float, response_payload: bytes
    ) -> tuple[int, threading.Thread]:
        """Start a server that sends one framed response after delay_s, returns port."""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        def serve() -> None:
            try:
                server_sock.settimeout(5)
                conn, _ = server_sock.accept()
                # drain the client request frame
                try:
                    hdr = conn.recv(4)
                    if len(hdr) == 4:
                        length = struct.unpack(">I", hdr)[0]
                        conn.recv(length)
                except OSError:
                    pass
                time.sleep(delay_s)
                # send framed response
                frame = struct.pack(">I", len(response_payload)) + response_payload
                with suppress_os_error():
                    conn.sendall(frame)
                conn.close()
            except OSError:
                pass
            finally:
                server_sock.close()

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        return port, t

    def test_response_after_300ms_succeeds(self) -> None:
        """Critical regression: response at 300 ms must succeed with timeout=5.

        Old 0.25 s cap would fail this; current code must pass it.
        """
        payload = b'{"ok": true}'
        port, t = self._echo_server(0.3, payload)
        try:
            transport = SocketRemoteTransport("127.0.0.1", port, timeout=5.0)
            result = transport.request("hello")
            self.assertEqual(result, payload.decode())
        finally:
            t.join(timeout=3)

    def test_response_after_500ms_succeeds_with_cancel_event(self) -> None:
        """Cancel event must not shorten the deadline when not set."""
        cancel_event = threading.Event()
        payload = b'{"ok": true}'
        port, t = self._echo_server(0.5, payload)
        try:
            transport = SocketRemoteTransport("127.0.0.1", port, timeout=5.0)
            result = transport.request("hello", cancel_event=cancel_event)
            self.assertEqual(result, payload.decode())
        finally:
            t.join(timeout=3)

    def test_cancelled_before_connect_does_not_connect(self) -> None:
        cancel_event = threading.Event()
        cancel_event.set()
        transport = SocketRemoteTransport("127.0.0.1", 19999, timeout=5.0)
        with self.assertRaises(RemoteExecutionError):
            transport.request("hello", cancel_event=cancel_event)

    def test_unreachable_endpoint_raises_transport_error(self) -> None:
        transport = SocketRemoteTransport("127.0.0.1", 19998, timeout=0.2)
        with self.assertRaises(RemoteTransportError):
            transport.request("hello")


def suppress_os_error():
    """Inline contextlib.suppress(OSError) for server helper."""
    from contextlib import suppress

    return suppress(OSError)


if __name__ == "__main__":
    unittest.main()
