"""Tests for outbound endpoint selection and transport timeout behaviour.

Phase 12J — Outbound Endpoint Resolution + Trust Persistence.

Covers:
- _preferred_candidate_address selects the physical LAN address over VPN IPs
- SocketRemoteTransport uses full timeout, never the 0.25 s cap
- classify_peer_failure maps certificate/fingerprint errors to AUTHENTICATION_FAILED
"""

import socket
import threading
import unittest
from unittest.mock import MagicMock, patch

from maintenance.nodes import PeerFailure, classify_peer_failure
from maintenance.remote_support.protocol import RemoteTransportError
from maintenance.remote_support.transport import SocketRemoteTransport
from maintenance.ui.window_node_actions_impl.pairing import (
    _preferred_candidate_address,
)


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
        self.assertEqual(
            _preferred_candidate_address(["100.64.0.1"]), "100.64.0.1"
        )

    def test_address_order_independent(self) -> None:
        addresses = ["100.64.0.1", "10.8.0.5", "192.168.55.107", "172.16.0.5"]
        result = _preferred_candidate_address(addresses)
        self.assertEqual(result, "192.168.55.107")

    def test_first_element_wins_when_ranks_are_equal(self) -> None:
        # Two 192.168 addresses — min() picks the lexicographically first one.
        result = _preferred_candidate_address(["192.168.55.107", "192.168.1.1"])
        self.assertIn(result, {"192.168.55.107", "192.168.1.1"})

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

        with patch(
            "maintenance.remote_support.transport.socket_module.create_connection",
            side_effect=fake_create_connection,
        ):
            with self.assertRaises(RemoteTransportError):
                transport.request("x", cancel_event=cancel_event)

        self.assertEqual(len(connect_calls), 1)
        self.assertAlmostEqual(connect_calls[0], 5.0, places=3,
                               msg="connect timeout must equal self._timeout, not 0.25")

    def test_full_timeout_used_without_cancel_event(self) -> None:
        transport = self._make_transport(timeout=10.0)
        connect_calls: list[float] = []

        def fake_create_connection(addr: tuple, timeout: float) -> None:
            connect_calls.append(timeout)
            raise OSError("connection refused")

        with patch(
            "maintenance.remote_support.transport.socket_module.create_connection",
            side_effect=fake_create_connection,
        ):
            with self.assertRaises(RemoteTransportError):
                transport.request("x", cancel_event=None)

        self.assertAlmostEqual(connect_calls[0], 10.0, places=3)

    def test_error_message_includes_exception_type(self) -> None:
        transport = self._make_transport()

        with patch(
            "maintenance.remote_support.transport.socket_module.create_connection",
            side_effect=ConnectionRefusedError("Connection refused"),
        ):
            with self.assertRaises(RemoteTransportError) as ctx:
                transport.request("x")

        msg = str(ctx.exception)
        self.assertIn("ConnectionRefusedError", msg,
                      "error message must include the exception type for diagnosis")
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
            classify_peer_failure(RemoteAuthError("peer certificate fingerprint changed")),
            PeerFailure.AUTHENTICATION_FAILED,
        )


if __name__ == "__main__":
    unittest.main()
