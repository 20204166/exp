"""NetworkDiscovery component tests (no real LAN required)."""

import unittest
from typing import Any

from maintenance.components.network_discovery import (
    DiscoveryAdvertisement,
    NetworkDiscovery,
)
from maintenance.nodes import NodeId

SERVICE_TYPE = "_system-analyzer._tcp.local."


def _advertisement(stable_id: str = "local") -> DiscoveryAdvertisement:
    return DiscoveryAdvertisement(
        stable_id=stable_id,
        display_name="This System",
        hostname="host1",
        app_version="1.2.2.0",
        protocol_version="1",
        platform="Linux",
        connectable=False,
        port=None,
    )


def _info(
    stable_id: str,
    *,
    name: str | None = None,
    protocol: str = "1",
    app_version: str = "1.2.2.0",
    platform: str = "Linux",
    connectable: str = "false",
    port: int = 5000,
    addresses: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "properties": {
            "id": stable_id,
            "name": name or f"host-{stable_id}",
            "app_version": app_version,
            "protocol_version": protocol,
            "platform": platform,
            "connectable": connectable,
        },
        "port": port,
        "addresses": addresses or ["192.168.1.10"],
    }


class FakeBackend:
    """In-memory discovery backend driven by the test."""

    def __init__(self, listener: Any, *, available: bool = True) -> None:
        self.listener = listener
        self.available_flag = available
        self.started = False
        self.stopped = False
        self.last_advertisement: Any = None

    @property
    def available(self) -> bool:
        return self.available_flag

    def start(self, advertisement: DiscoveryAdvertisement) -> None:
        self.started = True
        self.last_advertisement = advertisement

    def stop(self) -> None:
        self.stopped = True

    def add(self, service_name: str, info: Any) -> None:
        self.listener("add", service_name, info)

    def update(self, service_name: str, info: Any) -> None:
        self.listener("update", service_name, info)

    def remove(self, service_name: str) -> None:
        self.listener("remove", service_name, None)


class FailingStartBackend(FakeBackend):
    def start(self, advertisement: DiscoveryAdvertisement) -> None:
        super().start(advertisement)
        raise RuntimeError("bind failed")


def _discovery(
    *,
    local_id: str = "local",
    available: bool = True,
    ttl: float = 30.0,
) -> tuple[NetworkDiscovery, FakeBackend, list[tuple[str, Any]], Any]:
    """Return (discovery, backend, events, clock) where ``clock`` is a mutable
    holder object whose ``now`` the discovery reads, so tests can advance time
    deterministically for expiry scenarios."""

    class Clock:
        now = 100.0

    events: list[tuple[str, Any]] = []
    backend: FakeBackend | None = None

    def factory(listener: Any) -> FakeBackend:
        nonlocal backend
        backend = FakeBackend(listener, available=available)
        return backend

    clock = Clock()
    discovery = NetworkDiscovery(
        NodeId(local_id),
        advertisement=_advertisement(local_id),
        backend_factory=factory,
        ttl_seconds=ttl,
        clock=lambda: clock.now,
        on_event=lambda kind, payload: events.append((kind, payload)),
    )
    assert backend is not None
    return discovery, backend, events, clock


class NetworkDiscoveryTests(unittest.TestCase):
    def test_start_and_stop_lifecycle(self) -> None:
        discovery, backend, _events, _clock = _discovery()
        self.assertTrue(discovery.start())
        self.assertTrue(backend.started)
        self.assertTrue(discovery.active)
        discovery.stop()
        self.assertTrue(backend.stopped)
        self.assertFalse(discovery.active)

    def test_start_is_idempotent(self) -> None:
        discovery, backend, _events, _clock = _discovery()
        discovery.start()
        discovery.start()
        self.assertTrue(backend.started)

    def test_stop_is_idempotent(self) -> None:
        discovery, _backend, _events, _clock = _discovery()
        discovery.stop()
        discovery.stop()

    def test_unavailable_backend_reports_reason_and_stays_inactive(self) -> None:
        discovery, backend, _events, _clock = _discovery(available=False)
        self.assertFalse(discovery.available)
        self.assertFalse(discovery.start())
        self.assertFalse(backend.started)
        self.assertFalse(discovery.active)
        self.assertIsNotNone(discovery.unavailable_reason)

    def test_failed_start_cleans_up_partial_backend_state(self) -> None:
        backend: FailingStartBackend | None = None

        def factory(listener: Any) -> FailingStartBackend:
            nonlocal backend
            backend = FailingStartBackend(listener)
            return backend

        discovery = NetworkDiscovery(
            NodeId("local"),
            advertisement=_advertisement(),
            backend_factory=factory,
        )

        self.assertFalse(discovery.start())
        assert backend is not None
        self.assertTrue(backend.started)
        self.assertTrue(backend.stopped)
        self.assertFalse(discovery.active)

    def test_multihomed_addresses_remain_one_stable_peer(self) -> None:
        discovery, backend, _events, _clock = _discovery()
        discovery.start()
        backend.add(
            f"a.{SERVICE_TYPE}",
            _info("a", addresses=["192.168.1.10", "fe80::1", "192.168.1.10"]),
        )
        backend.add(
            f"a.{SERVICE_TYPE}",
            _info("a", addresses=["10.0.0.2", "fe80::1"]),
        )

        self.assertEqual(len(discovery.peers()), 1)
        self.assertEqual(discovery.peers()[0].stable_id, "a")

    def test_discovers_one_peer(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        backend.add(f"peer-a.{SERVICE_TYPE}", _info("peer-a"))

        self.assertEqual(len(events), 1)
        kind, candidate = events[0]
        self.assertEqual(kind, "candidate")
        self.assertEqual(candidate.stable_id, "peer-a")
        self.assertEqual(candidate.hostname, "host-peer-a")
        self.assertEqual(candidate.port, 5000)
        self.assertTrue(candidate.compatible)

    def test_discovers_multiple_peers(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        backend.add(f"a.{SERVICE_TYPE}", _info("a"))
        backend.add(f"b.{SERVICE_TYPE}", _info("b"))
        backend.add(f"c.{SERVICE_TYPE}", _info("c"))

        self.assertEqual(
            {
                candidate.stable_id
                for _kind, candidate in events
                if _kind == "candidate"
            },
            {"a", "b", "c"},
        )

    def test_self_advertisement_is_ignored(self) -> None:
        discovery, backend, events, _clock = _discovery(local_id="local")
        discovery.start()
        backend.add(f"local.{SERVICE_TYPE}", _info("local"))
        self.assertEqual(events, [])
        self.assertEqual(discovery.peers(), ())

    def test_duplicate_peer_is_deduplicated(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        backend.add(f"a.{SERVICE_TYPE}", _info("a"))
        backend.add(f"a.{SERVICE_TYPE}", _info("a"))
        backend.add(f"a.{SERVICE_TYPE}", _info("a"))
        self.assertEqual(len(discovery.peers()), 1)
        self.assertEqual(sum(1 for kind, _payload in events if kind == "candidate"), 1)

    def test_peer_address_change_emits_update(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        backend.add(f"a.{SERVICE_TYPE}", _info("a", addresses=["192.168.1.10"]))
        backend.add(f"a.{SERVICE_TYPE}", _info("a", addresses=["192.168.1.20"]))
        self.assertEqual(len(discovery.peers()), 1)
        self.assertEqual(discovery.peers()[0].addresses, ("192.168.1.20",))
        self.assertEqual(sum(1 for kind, _payload in events if kind == "candidate"), 2)

    def test_peer_hostname_change_emits_update(self) -> None:
        discovery, backend, _events, _clock = _discovery()
        discovery.start()
        backend.add(f"a.{SERVICE_TYPE}", _info("a", name="old-name"))
        backend.add(f"a.{SERVICE_TYPE}", _info("a", name="new-name"))
        self.assertEqual(discovery.peers()[0].hostname, "new-name")

    def test_invalid_port_is_tolerated_as_none(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        malformed = dict(_info("bad", port=1234))
        malformed["port"] = "not-a-port"
        backend.add(f"bad.{SERVICE_TYPE}", malformed)
        self.assertEqual(len(events), 1)
        kind, candidate = events[0]
        self.assertEqual(kind, "candidate")
        self.assertIsNone(candidate.port)

    def test_missing_stable_id_is_rejected(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        backend.add(f"bad.{SERVICE_TYPE}", {"properties": {}, "port": 0})
        self.assertEqual(events, [])

    def test_incompatible_protocol_version_is_flagged(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        backend.add(f"old.{SERVICE_TYPE}", _info("old", protocol="0"))
        kind, candidate = events[0]
        self.assertEqual(kind, "candidate")
        self.assertFalse(candidate.compatible)

    def test_remove_emits_lost(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        backend.add(f"a.{SERVICE_TYPE}", _info("a"))
        backend.remove(f"a.{SERVICE_TYPE}")
        self.assertEqual(discovery.peers(), ())
        self.assertEqual(events[-1][0], "lost")
        self.assertEqual(events[-1][1], "a")

    def test_expiry_drops_stale_peer(self) -> None:
        discovery, backend, events, clock = _discovery(ttl=30.0)
        discovery.start()
        backend.add(f"a.{SERVICE_TYPE}", _info("a"))
        clock.now = 500.0
        discovery.expire_stale()
        self.assertEqual(discovery.peers(), ())
        self.assertEqual(events[-1][0], "lost")

    def test_peer_return_after_expiry_is_fresh(self) -> None:
        discovery, backend, events, clock = _discovery(ttl=30.0)
        discovery.start()
        backend.add(f"a.{SERVICE_TYPE}", _info("a"))
        clock.now = 500.0
        discovery.expire_stale()
        clock.now = 501.0
        backend.add(f"a.{SERVICE_TYPE}", _info("a"))
        self.assertEqual(len(discovery.peers()), 1)
        self.assertEqual(sum(1 for kind, _p in events if kind == "candidate"), 2)

    def test_same_hostname_different_ids_stay_separate(self) -> None:
        discovery, backend, _events, _clock = _discovery()
        discovery.start()
        backend.add(f"a.{SERVICE_TYPE}", _info("a", name="same-host"))
        backend.add(f"b.{SERVICE_TYPE}", _info("b", name="same-host"))
        self.assertEqual(len(discovery.peers()), 2)

    def test_advertisement_contains_minimal_metadata(self) -> None:
        discovery, backend, _events, _clock = _discovery()
        discovery.start()
        assert backend.last_advertisement is not None
        self.assertEqual(backend.last_advertisement.stable_id, "local")
        self.assertEqual(backend.last_advertisement.app_version, "1.2.2.0")
        self.assertFalse(backend.last_advertisement.connectable)

    def test_repeated_start_stop_leaves_no_duplicate_peers(self) -> None:
        discovery, backend, _events, _clock = _discovery()
        for _ in range(5):
            discovery.start()
            backend.add(f"a.{SERVICE_TYPE}", _info("a"))
            discovery.stop()
        # After stop peers are cleared; on a fresh start a new add is one peer.
        discovery.start()
        backend.add(f"a.{SERVICE_TYPE}", _info("a"))
        self.assertEqual(len(discovery.peers()), 1)


if __name__ == "__main__":
    unittest.main()
