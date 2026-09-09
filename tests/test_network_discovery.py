"""NetworkDiscovery component tests (no real LAN required)."""

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from maintenance.components.network_discovery import (
    DiscoveryAdvertisement,
    NetworkDiscovery,
    ZeroconfDiscoveryBackend,
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
    fingerprint: str | None = None,
) -> dict[str, Any]:
    properties: dict[str, str] = {
        "id": stable_id,
        "name": name or f"host-{stable_id}",
        "app_version": app_version,
        "protocol_version": protocol,
        "platform": platform,
        "connectable": connectable,
    }
    if fingerprint is not None:
        properties["fingerprint"] = fingerprint
    return {
        "properties": properties,
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
    def test_zeroconf_backend_starts_without_a_zeroconf_addresses_attribute(
        self,
    ) -> None:
        registered: list[Any] = []

        class FakeZeroconf:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            def register_service(self, service_info: Any) -> None:
                registered.append(service_info)

            def close(self) -> None:
                pass

        class FakeServiceInfo:
            def __init__(self, *_args: Any, **kwargs: Any) -> None:
                self.kwargs = kwargs

        class FakeServiceBrowser:
            def __init__(self, *_args: Any) -> None:
                pass

            def cancel(self) -> None:
                pass

        fake_module = SimpleNamespace(
            Zeroconf=FakeZeroconf,
            ServiceInfo=FakeServiceInfo,
            ServiceBrowser=FakeServiceBrowser,
            IPVersion=SimpleNamespace(All="all"),
            get_all_addresses=lambda: ["192.168.1.20", "127.0.0.1"],
            get_all_addresses_v6=lambda: [(("fe80::1", 0, 2), 2), (("::1", 0, 0), 1)],
        )
        with patch(
            "maintenance.components.network_discovery._zeroconf_module", fake_module
        ):
            backend = ZeroconfDiscoveryBackend(lambda *_args: None)
            backend.start(_advertisement())
            backend.stop()

        self.assertEqual(len(registered), 1)
        self.assertEqual(
            registered[0].kwargs["addresses"],
            [
                b"\xc0\xa8\x01\x14",
                b"\xfe\x80" + (b"\x00" * 13) + b"\x01",
            ],
        )

    def test_zeroconf_backend_requests_all_ip_versions(self) -> None:
        created: list[Any] = []

        class FakeZeroconf:
            def __init__(self, **kwargs: Any) -> None:
                created.append(kwargs)

            def register_service(self, _service_info: Any) -> None:
                pass

            def close(self) -> None:
                pass

        class FakeServiceInfo:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

        class FakeServiceBrowser:
            def __init__(self, *_args: Any) -> None:
                pass

            def cancel(self) -> None:
                pass

        fake_module = SimpleNamespace(
            Zeroconf=FakeZeroconf,
            ServiceInfo=FakeServiceInfo,
            ServiceBrowser=FakeServiceBrowser,
            IPVersion=SimpleNamespace(All="all"),
            get_all_addresses=list,
            get_all_addresses_v6=list,
        )
        with patch(
            "maintenance.components.network_discovery._zeroconf_module", fake_module
        ):
            backend = ZeroconfDiscoveryBackend(lambda *_args: None)
            backend.start(_advertisement())
            backend.stop()

        self.assertEqual(created, [{"ip_version": "all"}])

    def test_zeroconf_backend_falls_back_to_ipv4_when_all_versions_fail(self) -> None:
        created: list[Any] = []

        class FakeZeroconf:
            def __init__(self, **kwargs: Any) -> None:
                created.append(kwargs)
                if kwargs["ip_version"] == "all":
                    raise OSError("IPv6 network unavailable")

            def register_service(self, _service_info: Any) -> None:
                pass

            def close(self) -> None:
                pass

        class FakeServiceInfo:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

        class FakeServiceBrowser:
            def __init__(self, *_args: Any) -> None:
                pass

            def cancel(self) -> None:
                pass

        fake_module = SimpleNamespace(
            Zeroconf=FakeZeroconf,
            ServiceInfo=FakeServiceInfo,
            ServiceBrowser=FakeServiceBrowser,
            IPVersion=SimpleNamespace(All="all", V4Only="v4"),
            get_all_addresses=list,
            get_all_addresses_v6=list,
        )
        with patch(
            "maintenance.components.network_discovery._zeroconf_module", fake_module
        ):
            backend = ZeroconfDiscoveryBackend(lambda *_args: None)
            backend.start(_advertisement())
            backend.stop()

        self.assertEqual(created, [{"ip_version": "all"}, {"ip_version": "v4"}])

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

    def test_self_filter_accepts_string_local_node_id(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery._local_node_id = "local"
        discovery.start()

        backend.add(f"local.{SERVICE_TYPE}", _info("local"))

        self.assertEqual(events, [])

    def test_self_advertisement_without_txt_id_is_ignored(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()

        backend.add(f"local.{SERVICE_TYPE}", {"properties": {}, "port": 5000})

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

    def test_zeroconf_bytes_properties_are_normalized(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        info = _info("peer")
        info["properties"] = {
            key.encode(): value.encode() for key, value in info["properties"].items()
        }

        backend.add(f"peer.{SERVICE_TYPE}", info)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][1].stable_id, "peer")

    def test_ipv6_only_service_uses_parsed_addresses(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        info = _info("peer")
        info["addresses"] = []
        info["parsed_addresses"] = lambda: ["2001:db8::9"]

        backend.add(f"peer.{SERVICE_TYPE}", info)

        self.assertEqual(events[0][1].addresses, ("2001:db8::9",))

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

    def test_remove_uses_normalized_stable_id_when_service_name_differs(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        backend.add(f"alias.{SERVICE_TYPE}", _info("peer"))
        backend.remove(f"alias.{SERVICE_TYPE}")

        self.assertEqual(discovery.peers(), ())
        self.assertEqual(events[-1], ("lost", "peer"))

    def test_late_transport_event_after_stop_is_ignored(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        discovery.stop()
        backend.add(f"peer.{SERVICE_TYPE}", _info("peer"))

        self.assertEqual(discovery.peers(), ())
        self.assertEqual(events, [])

    def test_malformed_remove_event_is_ignored(self) -> None:
        discovery, backend, events, _clock = _discovery()
        discovery.start()
        backend.remove(object())  # type: ignore[arg-type]

        self.assertEqual(discovery.peers(), ())
        self.assertEqual(events, [])

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

    def test_peer_identity_fingerprint_is_carried_without_becoming_trust(self) -> None:
        discovery, backend, _events, _clock = _discovery()
        discovery.start()
        backend.add(
            f"a.{SERVICE_TYPE}",
            _info("a", fingerprint="aaaa:bbbb"),
        )

        candidate = discovery.peers()[0]

        self.assertEqual(candidate.identity_fingerprint, "aaaa:bbbb")

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
