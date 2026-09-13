"""Accuracy checks for Help & Guide content against canonical product concepts.

These are deliberately lightweight substring checks, not brittle full-
paragraph assertions -- they exist to catch a future edit that reintroduces
a security misstatement (discovered == trusted, coordinator == trust
authority, Remove Connection == Revoke, ...), not to lock the exact wording.
"""

import unittest

from maintenance.ui.help_content import HELP_TOPICS, find_topic


def _topic_text(key: str) -> str:
    topic = find_topic(key)
    assert topic is not None, f"missing help topic: {key}"
    chunks = [topic.title, topic.summary]
    for section in topic.sections:
        chunks.append(section.heading)
        chunks.extend(section.paragraphs)
        chunks.extend(section.bullets)
    return " ".join(chunks).casefold()


class HelpTopicKeysAreUniqueTests(unittest.TestCase):
    def test_every_topic_key_is_unique(self) -> None:
        keys = [topic.key for topic in HELP_TOPICS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_find_topic_returns_none_for_an_unknown_key(self) -> None:
        self.assertIsNone(find_topic("does-not-exist"))


class DiscoveryContentTests(unittest.TestCase):
    def test_discovery_does_not_claim_it_grants_trust(self) -> None:
        text = _topic_text("discovery")
        self.assertIn("does not trust", text)
        self.assertIn("does not grant any permission", text)

    def test_discovery_does_not_claim_it_joins_a_cluster(self) -> None:
        text = _topic_text("discovery")
        self.assertIn("does not join anything to a cluster", text)


class PairingTrustContentTests(unittest.TestCase):
    def test_pairing_requires_explicit_accept(self) -> None:
        text = _topic_text("pairing-trust")
        self.assertIn("accept", text)
        self.assertIn("reject", text)

    def test_trust_is_distinguished_from_authorization(self) -> None:
        text = _topic_text("pairing-trust")
        self.assertIn("discovered", text)
        self.assertIn("trusted", text)
        self.assertIn("authorized", text)
        self.assertIn("does not hand over every permission", text)


class ConnectionsContentTests(unittest.TestCase):
    def test_remove_connection_preserves_pairing(self) -> None:
        text = _topic_text("connections")
        self.assertIn("preserved", text)

    def test_revoke_requires_a_new_pairing_invite(self) -> None:
        text = _topic_text("connections")
        self.assertIn("new pairing invite is required", text)

    def test_revoke_does_not_claim_a_permanent_discovery_block(self) -> None:
        text = _topic_text("connections")
        self.assertIn("does not hide the machine from discovery forever", text)


class ClusterContentTests(unittest.TestCase):
    def test_cluster_does_not_claim_pooled_hardware(self) -> None:
        text = _topic_text("clusters")
        for claim in ("pooled ram", "pooled cpu", "shared operating system"):
            self.assertIn(claim, text)

    def test_cluster_requires_pairing_first(self) -> None:
        text = _topic_text("clusters")
        self.assertIn("already be a trusted, paired peer", text)


class CoordinatorWorkerContentTests(unittest.TestCase):
    def test_coordinator_is_not_an_automatic_trust_authority(self) -> None:
        text = _topic_text("coordinator-worker")
        self.assertIn("not a trust authority", text)
        self.assertIn("does not grant automatic trust", text)

    def test_coordinator_cannot_silently_pair_machines(self) -> None:
        text = _topic_text("coordinator-worker")
        self.assertIn("cannot pair a machine on its own", text)

    def test_worker_is_not_described_as_a_pooled_pc(self) -> None:
        text = _topic_text("coordinator-worker")
        self.assertNotIn("pooled pc is an accurate", text)
        self.assertIn("not an accurate way to think about this", text)


class PermissionsContentTests(unittest.TestCase):
    def test_default_trust_is_read_only(self) -> None:
        text = _topic_text("permissions")
        self.assertIn("read-only", text)
        self.assertIn("nothing more", text)

    def test_extra_permissions_are_not_automatic(self) -> None:
        text = _topic_text("permissions")
        self.assertIn("none of these are granted automatically", text)


class CleanupContentTests(unittest.TestCase):
    def test_cleanup_says_trash_not_permanent_delete(self) -> None:
        text = _topic_text("storage")
        self.assertIn("trash", text)
        self.assertIn("never a permanent delete", text)

    def test_cleanup_says_nothing_is_removed_automatically(self) -> None:
        text = _topic_text("storage")
        self.assertIn("nothing is removed", text)


class ThermalContentTests(unittest.TestCase):
    def test_thermals_do_not_promise_universal_sensor_availability(self) -> None:
        text = _topic_text("thermals")
        self.assertIn("not every machine exposes every temperature", text)

    def test_thermals_distinguish_unsupported_from_temporarily_unavailable(
        self,
    ) -> None:
        text = _topic_text("thermals")
        self.assertIn("not supported", text)
        self.assertIn("temporarily unavailable", text)


class PlatformSupportContentTests(unittest.TestCase):
    def test_battery_absence_on_desktops_is_framed_as_expected(self) -> None:
        text = _topic_text("dashboard")
        self.assertIn("expected, not an error", text)


if __name__ == "__main__":
    unittest.main()
