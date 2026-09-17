"""Tests for RemoteSocketServer port contract and PEER_SERVICE_DEFAULT_PORT."""

import unittest


class PeerServicePortTests(unittest.TestCase):
    def test_default_port_constant_exists(self) -> None:
        from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT
        self.assertIsInstance(PEER_SERVICE_DEFAULT_PORT, int)
        self.assertGreater(PEER_SERVICE_DEFAULT_PORT, 1023)
        self.assertLess(PEER_SERVICE_DEFAULT_PORT, 32768)  # below Linux ephemeral range

    def test_default_port_re_exported_from_remote(self) -> None:
        from maintenance import remote
        self.assertTrue(hasattr(remote, "PEER_SERVICE_DEFAULT_PORT"))
        from maintenance.remote import PEER_SERVICE_DEFAULT_PORT
        from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT as src
        self.assertEqual(PEER_SERVICE_DEFAULT_PORT, src)

    def test_default_port_value(self) -> None:
        from maintenance.remote_support.server import PEER_SERVICE_DEFAULT_PORT
        self.assertEqual(PEER_SERVICE_DEFAULT_PORT, 27321)
