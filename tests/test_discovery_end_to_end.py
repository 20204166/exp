"""End-to-end discovery integration tests without requiring a LAN or Tk root."""

import unittest
from dataclasses import dataclass, field
from typing import Any, cast

from maintenance.cluster import ClusterState
from maintenance.components.coordinator import AppCoordinator
from maintenance.components.network_discovery import (
    DiscoveryAdvertisement,
    NetworkDiscovery,
)
from maintenance.nodes import (
    NodeId,
    NodeRegistry,
    NodeTrustState,
)
from maintenance.ui.discovery_refresh import refresh_discovery_views
from maintenance.ui.render_coordinator import RenderIntent, UICoordinator
from tests.support.discovery import FakeBackend
from tests.support.nodes import make_local_context

SERVICE_TYPE = "_system-analyzer._tcp.local."


@dataclass
class FakeNodesPage:
    discovered: list[Any] = field(default_factory=list)
    trusted: list[Any] = field(default_factory=list)

    def refresh_discovered(self, specs: Any) -> None:
        self.discovered = list(specs)

    def refresh_trusted(self, specs: Any) -> None:
        self.trusted = list(specs)


class DiscoveryEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        local = make_local_context()
        self.registry = NodeRegistry(local)
        self.page = FakeNodesPage()
        self.ui = UICoordinator()
        self.now = 100.0
        self.backend: FakeBackend | None = None
        self.coordinator = AppCoordinator(deliver=lambda callback: callback())
        self.discovery = NetworkDiscovery(
            "local",
            advertisement=DiscoveryAdvertisement(
                stable_id="local",
                display_name="This System",
                hostname="local-host",
                app_version="1.3.7.1",
            ),
            backend_factory=cast(Any, self._backend_factory),
            ttl_seconds=30.0,
            clock=lambda: self.now,
        )
        self.cluster = ClusterState()

    def _backend_factory(self, listener: Any) -> FakeBackend:
        self.backend = FakeBackend(listener)
        return self.backend

    @staticmethod
    def _info(
        stable_id: str,
        *,
        name: str | None = None,
        address: str = "192.168.1.10",
        protocol: str = "1",
        platform: str = "Linux",
    ) -> dict[str, Any]:
        return {
            "properties": {
                "id": stable_id,
                "name": name or f"host-{stable_id}",
                "app_version": "1.3.7.1",
                "protocol_version": protocol,
                "platform": platform,
                "connectable": "false",
            },
            "port": 5000,
            "addresses": [address],
        }

    def _start(self) -> FakeBackend:
        self.assertTrue(
            self.coordinator.start_discovery(
                self.discovery,
                on_candidate=self._on_candidate,
                on_lost=self._on_lost,
            )
        )
        assert self.backend is not None
        return self.backend

    def _render(self) -> None:
        self.ui.request(
            RenderIntent(target="discovery", node_id="local", layout_changed=True),
            lambda _intent: refresh_discovery_views(
                page=self.page,
                peer_specs=self.registry.discovered_candidates(),
                trusted_specs=(),
                refresh_trusted=False,
                refresh_cluster_page=lambda: None,
                status_label=None,
                discovered_candidates=self.registry.discovered_candidates(),
            ),
        )

    def _on_candidate(self, candidate: Any) -> None:
        self.registry.update_discovered(candidate)
        self._render()

    def _on_lost(self, stable_id: str) -> None:
        self.registry.remove_discovered(NodeId(stable_id))
        self._render()

    def test_advertisement_reaches_nodes_page_and_stays_untrusted(self) -> None:
        backend = self._start()

        backend.add(f"peer-a.{SERVICE_TYPE}", self._info("peer-a"))
        backend.add(f"local.{SERVICE_TYPE}", self._info("local"))
        backend.add(f"peer-a-ethernet.{SERVICE_TYPE}", self._info("peer-a"))
        backend.add(
            f"peer-a-wifi.{SERVICE_TYPE}", self._info("peer-a", address="10.0.0.8")
        )
        backend.add(f"peer-b.{SERVICE_TYPE}", self._info("peer-b", name="same-host"))
        backend.add(f"peer-c.{SERVICE_TYPE}", self._info("peer-c", name="same-host"))
        backend.add(f"old.{SERVICE_TYPE}", self._info("old", protocol="0"))
        backend.add(f"bad.{SERVICE_TYPE}", {"properties": {}, "addresses": []})

        candidates = self.registry.discovered_candidates()
        self.assertEqual(
            {candidate.stable_id for candidate in candidates},
            {"peer-a", "peer-b", "peer-c", "old"},
        )
        self.assertEqual(
            len(
                [
                    candidate
                    for candidate in candidates
                    if candidate.stable_id == "peer-a"
                ]
            ),
            1,
        )
        self.assertEqual(
            self.registry.contexts()[0].descriptor.trust, NodeTrustState.LOCAL
        )
        self.assertEqual(self.page.discovered, list(candidates))
        self.assertFalse(
            next(
                candidate for candidate in candidates if candidate.stable_id == "old"
            ).compatible
        )
        self.assertEqual(len(self.registry.contexts()), 1)

    def test_ip_change_disappearance_and_restart_are_observable(self) -> None:
        backend = self._start()
        service = f"peer-a.{SERVICE_TYPE}"

        backend.add(service, self._info("peer-a", address="192.168.1.10"))
        backend.update(service, self._info("peer-a", address="10.0.0.8"))
        self.assertEqual(self.page.discovered[0].addresses, ("10.0.0.8",))

        backend.remove(service)
        self.assertEqual(self.registry.discovered_candidates(), ())
        self.assertEqual(self.page.discovered, [])

        backend.add(service, self._info("peer-a", address="192.168.1.11"))
        self.assertEqual(self.page.discovered[0].stable_id, "peer-a")
        self.assertEqual(self.page.discovered[0].addresses, ("192.168.1.11",))

    def test_ttl_expiry_and_shutdown_stop_the_complete_bridge(self) -> None:
        backend = self._start()
        backend.add(f"peer-a.{SERVICE_TYPE}", self._info("peer-a"))

        self.discovery.expire_stale(now=1000.0)
        self.assertEqual(self.registry.discovered_candidates(), ())

        self.coordinator.stop_discovery()
        self.assertTrue(backend.stopped)
        backend.add(f"late.{SERVICE_TYPE}", self._info("late"))
        self.assertEqual(self.registry.discovered_candidates(), ())
        self.ui.shutdown()
        self.assertFalse(
            self.ui.request(RenderIntent(target="discovery"), lambda _intent: None)
        )

    def test_restart_can_be_started_again_after_coordinator_stop(self) -> None:
        backend = self._start()
        self.coordinator.stop_discovery()
        self.assertTrue(
            self.coordinator.start_discovery(
                self.discovery,
                on_candidate=self._on_candidate,
                on_lost=self._on_lost,
            )
        )
        assert self.backend is backend
        backend.add(f"peer-a.{SERVICE_TYPE}", self._info("peer-a"))
        self.assertEqual(len(self.registry.discovered_candidates()), 1)


if __name__ == "__main__":
    unittest.main()
