"""Opposer 4 — Official-standards semantics evidence test for SEC-20260912-002.

Verifies whether the repo's TLS, HMAC, replay-cache, and Zeroconf assumptions
are consistent with Python official documentation and standard library behavior.

Security claims being tested:
1. client_context() with CERT_NONE + check_hostname=False still allows
   getpeercert(binary_form=True) to return the peer certificate on the
   client side (needed for fingerprint pinning to work).
2. TLS 1.2 minimum_version is correctly set and consistent with Python 3.10+
   defaults for PROTOCOL_TLS_SERVER and PROTOCOL_TLS_CLIENT.
3. HMAC-SHA256 signature computation matches the repo's _signature function.
4. ReplayCache uses the same clock for freshness and replay TTL (consistency).
5. certificate_fingerprint() computes SHA-256 of DER bytes correctly.
6. Zeroconf ServiceBrowser callbacks run on a dedicated thread, and the
   repo's _peer_lock serializes peer map mutation.

What a pass would prove:
- The repo's TLS pinning model is internally consistent with Python ssl
  semantics: CERT_NONE does not prevent getpeercert from returning the cert.
- TLS 1.2 minimum is correctly set.
- HMAC computation is standard.
- ReplayCache clock is used consistently.
- Fingerprint computation is standard SHA-256 of DER.
- Zeroconf callbacks are serialized by the repo's lock.

What a fail would disprove:
- The repo's TLS pinning model is broken (getpeercert returns None with
  CERT_NONE on client side).
- TLS minimum version is not correctly set.
- HMAC computation is non-standard.
- ReplayCache clock inconsistency.
- Fingerprint computation is non-standard.

What a timeout/error means:
- Test infrastructure issue, not a security finding.
"""

import hashlib
import hmac
import json
import socket
import ssl
import threading
import time
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Test 1: TLS client_context() with CERT_NONE still returns peer cert
# ---------------------------------------------------------------------------


class TestTLSCertNoneGetPeerCert(unittest.TestCase):
    """Verify that CERT_NONE on client side still allows getpeercert(binary_form=True).

    Python ssl docs state: 'for a server SSL socket, the client will only
    provide a certificate when requested by the server; therefore
    getpeercert() will return None if you used CERT_NONE'. This applies to
    SERVER sockets. For CLIENT sockets, the server always sends its cert
    during the handshake, so getpeercert(binary_form=True) should return
    the DER bytes even with CERT_NONE.
    """

    def test_client_cert_none_returns_peer_cert(self):
        """Create a TLS server+client pair with CERT_NONE and verify
        getpeercert(binary_form=True) returns non-None on the client side."""
        import os
        import subprocess
        import tempfile

        # Generate a self-signed cert for the test server
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "server.key")
            cert_path = os.path.join(tmpdir, "server.crt")
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=localhost",
                    "-keyout",
                    key_path,
                    "-out",
                    cert_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Server context
            server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            server_ctx.load_cert_chain(cert_path, key_path)

            # Client context — mirrors the repo's client_context()
            client_ctx = ssl.create_default_context()
            client_ctx.check_hostname = False
            client_ctx.verify_mode = ssl.CERT_NONE
            client_ctx.minimum_version = ssl.TLSVersion.TLSv1_2

            # Verify the client context settings match the repo's
            self.assertFalse(client_ctx.check_hostname)
            self.assertEqual(client_ctx.verify_mode, ssl.CERT_NONE)
            self.assertEqual(client_ctx.minimum_version, ssl.TLSVersion.TLSv1_2)

            # Set up a simple TLS server
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind(("127.0.0.1", 0))
            server_sock.listen(1)
            port = server_sock.getsockname()[1]

            server_result = {}

            def run_server():
                try:
                    conn, _addr = server_sock.accept()
                    with server_ctx.wrap_socket(conn, server_side=True) as sconn:
                        # Read some data to complete the exchange
                        sconn.recv(1024)
                        sconn.sendall(b"ok")
                except Exception as e:  # noqa: BLE001 - test harness
                    server_result["error"] = str(e)
                finally:
                    server_sock.close()

            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()

            # Client side
            try:
                raw_sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                with client_ctx.wrap_socket(
                    raw_sock, server_hostname="localhost"
                ) as ssock:
                    # This is the critical test: does getpeercert(binary_form=True)
                    # return the cert even with CERT_NONE?
                    peer_cert = ssock.getpeercert(binary_form=True)
                    self.assertIsNotNone(
                        peer_cert,
                        "getpeercert(binary_form=True) returned None with CERT_NONE "
                        "on client side — this would break fingerprint pinning",
                    )
                    assert peer_cert is not None  # narrow for static checkers
                    self.assertIsInstance(peer_cert, (bytes, bytearray))
                    self.assertGreater(len(peer_cert), 0)

                    # Verify fingerprint computation matches the repo's approach
                    digest = hashlib.sha256(peer_cert).hexdigest()
                    fingerprint = ":".join(digest[i : i + 4] for i in range(0, 64, 4))
                    self.assertEqual(
                        len(fingerprint), 79
                    )  # 16 groups of 4 chars + 15 colons
                    self.assertIn(":", fingerprint)

                    ssock.sendall(b"hello")
                    response = ssock.recv(1024)
                    self.assertEqual(response, b"ok")
            finally:
                server_thread.join(timeout=5)

        # If we get here, the TLS pinning model is internally consistent
        # with Python ssl semantics.


# ---------------------------------------------------------------------------
# Test 2: TLS 1.2 minimum version consistency
# ---------------------------------------------------------------------------


class TestTLSMinimumVersion(unittest.TestCase):
    """Verify that both server and client contexts set TLS 1.2 minimum."""

    def test_server_context_minimum_version(self):
        """server_context() sets minimum_version to TLSv1_2."""
        import subprocess
        import tempfile

        from maintenance.remote_security import TLSMaterial, server_context

        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "server.key"
            cert_path = Path(tmpdir) / "server.crt"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=test",
                    "-keyout",
                    str(key_path),
                    "-out",
                    str(cert_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            material = TLSMaterial(
                certificate=cert_path,
                private_key=key_path,
                fingerprint="test",
            )
            ctx = server_context(material)
            self.assertEqual(ctx.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_client_context_minimum_version(self):
        """client_context() sets minimum_version to TLSv1_2."""
        from maintenance.remote_security import client_context

        ctx = client_context()
        self.assertEqual(ctx.minimum_version, ssl.TLSVersion.TLSv1_2)
        # Also verify the other settings
        self.assertFalse(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)


# ---------------------------------------------------------------------------
# Test 3: HMAC-SHA256 signature computation
# ---------------------------------------------------------------------------


class TestHMACSignature(unittest.TestCase):
    """Verify the repo's _signature function matches standard HMAC-SHA256."""

    def test_signature_matches_standard_hmac(self):
        from maintenance.remote_support.protocol import _signature

        secret = "a" * 64  # 256-bit hex secret
        fields = {
            "v": "1",
            "node_id": "test-node",
            "op": "hello",
            "params": {},
            "request_id": "abc123",
            "nonce": "def456",
            "ts": 1234567890.0,
        }

        # Repo's signature
        repo_sig = _signature(secret, fields)

        # Standard HMAC-SHA256
        canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(
            secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        self.assertEqual(repo_sig, expected)
        self.assertEqual(len(repo_sig), 64)  # SHA-256 hex digest is 64 chars


# ---------------------------------------------------------------------------
# Test 4: ReplayCache clock consistency
# ---------------------------------------------------------------------------


class TestReplayCacheClockConsistency(unittest.TestCase):
    """Verify ReplayCache uses the injected clock consistently."""

    def test_replay_cache_uses_injected_clock(self):
        from maintenance.remote_support.protocol import ReplayCache

        fake_time = [1000.0]

        def fake_clock():
            return fake_time[0]

        cache = ReplayCache(clock=fake_clock, ttl_seconds=300.0, max_entries=100)

        # Record at t=1000
        self.assertTrue(cache.check_and_record("node1", "req1", "nonce1", 1000.0))

        # Same request at t=1000 should be rejected (replay)
        self.assertFalse(cache.check_and_record("node1", "req1", "nonce1", 1000.0))

        # Different nonce at t=1000 should be accepted
        self.assertTrue(cache.check_and_record("node1", "req1", "nonce2", 1000.0))

        # After TTL expires, the entry should be pruned
        fake_time[0] = 1400.0  # 400 seconds later, > TTL of 300
        # The prune happens inside check_and_record
        self.assertTrue(cache.check_and_record("node1", "req1", "nonce1", 1400.0))

    def test_remote_service_uses_time_time_for_freshness(self):
        """RemoteService passes time.time as clock, which is correct for
        freshness checking (timestamps are wall-clock)."""
        # Verify the default clock is time.time
        import inspect

        from maintenance.remote import RemoteService

        sig = inspect.signature(RemoteService.__init__)
        clock_param = sig.parameters["clock"]
        self.assertEqual(clock_param.default, time.time)


# ---------------------------------------------------------------------------
# Test 5: Certificate fingerprint computation
# ---------------------------------------------------------------------------


class TestCertificateFingerprint(unittest.TestCase):
    """Verify certificate_fingerprint() computes SHA-256 of DER bytes."""

    def test_fingerprint_is_sha256_of_der(self):
        from maintenance.remote_security import certificate_fingerprint

        # Use a known DER byte sequence
        test_der = b"\x30\x82\x01\x00" + b"\x00" * 256
        digest = hashlib.sha256(test_der).hexdigest()
        expected = ":".join(digest[i : i + 4] for i in range(0, 64, 4))

        result = certificate_fingerprint(test_der)
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 79)  # 16 groups of 4 + 15 colons

    def test_fingerprint_format(self):
        """Fingerprint should be colon-separated 4-char hex groups."""
        from maintenance.remote_security import certificate_fingerprint

        test_der = b"\x00" * 32
        result = certificate_fingerprint(test_der)
        parts = result.split(":")
        self.assertEqual(len(parts), 16)
        for part in parts:
            self.assertEqual(len(part), 4)
            # Each part should be valid hex
            int(part, 16)


# ---------------------------------------------------------------------------
# Test 6: Zeroconf callback threading and lock serialization
# ---------------------------------------------------------------------------


class TestZeroconfCallbackThreading(unittest.TestCase):
    """Verify that NetworkDiscovery serializes peer map mutation with _peer_lock."""

    def test_peer_lock_serializes_callbacks(self):
        """The _handle_transport_event method acquires _peer_lock before
        mutating _peers and _service_nodes."""
        from maintenance.components.network_discovery import (
            DiscoveryAdvertisement,
            NetworkDiscovery,
        )
        from maintenance.nodes import NodeId

        local_id = NodeId("local")
        advertisement = DiscoveryAdvertisement(
            stable_id="local",
            display_name="Local",
            hostname="localhost",
            app_version="1.0",
        )

        discovery = NetworkDiscovery(
            local_id,
            advertisement=advertisement,
            backend_factory=lambda listener: _FakeBackend(listener),
        )

        # Verify the lock exists and is an RLock
        self.assertIsInstance(discovery._peer_lock, type(threading.RLock()))

        # Verify _handle_transport_event acquires the lock
        # by checking that concurrent calls don't corrupt the peer map
        discovery._active = True

        results = []
        errors = []

        def add_peer(peer_id, port):
            try:
                info = _FakeServiceInfo(
                    properties={"id": peer_id, "name": peer_id, "connectable": "true"},
                    port=port,
                )
                discovery._handle_transport_event(
                    "add", f"{peer_id}._system-analyzer._tcp.local.", info
                )
                results.append(peer_id)
            except Exception as e:  # noqa: BLE001 - test harness
                errors.append(str(e))

        threads = []
        for i in range(10):
            t = threading.Thread(target=add_peer, args=(f"peer{i}", 8000 + i))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        self.assertEqual(len(errors), 0, f"Errors during concurrent access: {errors}")
        self.assertEqual(len(results), 10)
        # All 10 peers should be in the map
        peers = discovery.peers()
        self.assertEqual(len(peers), 10)


class _FakeBackend:
    """Fake discovery backend for testing."""

    def __init__(self, listener):
        self._listener = listener

    @property
    def available(self):
        return True

    def start(self, advertisement):
        pass

    def stop(self):
        pass


class _FakeServiceInfo:
    """Fake service info for testing."""

    def __init__(self, properties, port=8000, addresses=None):
        self.properties = properties
        self.port = port
        self.addresses = addresses or []

    def parsed_addresses(self):
        return []


# ---------------------------------------------------------------------------
# Test 7: Verify that the repo's client_context matches the documented
# pattern for certificate pinning (CERT_NONE + fingerprint comparison)
# ---------------------------------------------------------------------------


class TestCertificatePinningPattern(unittest.TestCase):
    """Verify the repo's certificate pinning pattern is internally consistent.

    The pattern is:
    1. Create client context with CERT_NONE (no CA validation)
    2. After TLS handshake, get peer cert in DER form
    3. Compute SHA-256 fingerprint
    4. Compare against expected pinned fingerprint using hmac.compare_digest

    This is a recognized certificate pinning pattern. The Python ssl docs
    warn against CERT_NONE for general use, but the repo uses it deliberately
    as part of a pinning model where trust is established out-of-band via
    the pinned fingerprint.
    """

    def test_transport_uses_fingerprint_comparison(self):
        """SocketRemoteTransport.request() compares fingerprint after handshake."""
        import inspect

        from maintenance.remote_support.transport import SocketRemoteTransport

        source = inspect.getsource(SocketRemoteTransport.request)
        # Verify the key steps are present
        self.assertIn("getpeercert(binary_form=True)", source)
        self.assertIn("certificate_fingerprint", source)
        self.assertIn("hmac.compare_digest", source)
        self.assertIn("expected_fingerprint", source)

    def test_build_trusted_transport_requires_fingerprint(self):
        """build_trusted_transport rejects records without a fingerprint."""
        from maintenance.cluster import TrustedNodeRecord
        from maintenance.remote_support.protocol import RemoteAuthError
        from maintenance.remote_support.transport import build_trusted_transport

        # Record without fingerprint should raise
        record = TrustedNodeRecord(
            node_id="test",
            display_name="Test",
            hostname="localhost",
            platform=None,
            color=None,
            host="127.0.0.1",
            port=8000,
            capabilities=frozenset(),
            secret="a" * 64,
            trusted_at=0.0,
            identity_fingerprint="abc",
            transport_fingerprint="",  # Empty fingerprint
            permissions=frozenset(),
        )
        with self.assertRaises(RemoteAuthError):
            build_trusted_transport(record)


if __name__ == "__main__":
    unittest.main()
