"""Unit tests for discovery refresh presentation helpers."""

import unittest
from collections.abc import Callable
from unittest.mock import Mock

from maintenance.components.coordinator import AppCoordinator
from maintenance.ui.discovery_refresh import (
    post_discovery_refresh,
    refresh_discovery_views,
)


class DiscoveryRefreshTests(unittest.TestCase):
    def test_post_discovery_refresh_renders_one_latest_registry_state(self) -> None:
        queued: list[Callable[[], None]] = []
        coordinator = AppCoordinator(deliver=queued.append)
        page = Mock()
        cluster_refresh = Mock()
        status_label = Mock()
        candidates: list[Mock] = []
        trusted_refresh_pending = [False]

        def post() -> None:
            post_discovery_refresh(
                coordinator=coordinator,
                key="discovery-pages",
                page=page,
                get_peer_specs=lambda: list(candidates),
                get_trusted_specs=lambda: ["trusted-now"],
                should_refresh_trusted=lambda: trusted_refresh_pending.pop(),
                refresh_cluster_page=cluster_refresh,
                status_label=status_label,
                get_discovered_candidates=lambda: list(candidates),
            )

        post()
        candidates.append(Mock(hostname="latest"))
        trusted_refresh_pending.append(True)
        post()
        queued[-1]()

        page.refresh_discovered.assert_called_once_with(candidates)
        page.refresh_trusted.assert_called_once_with(["trusted-now"])
        cluster_refresh.assert_called_once_with()

    def test_refresh_discovery_views_updates_lists_and_status(self) -> None:
        page = Mock()
        cluster_refresh = Mock()
        status_label = Mock()
        candidates = [Mock(hostname="beta"), Mock(hostname="alpha")]

        refresh_discovery_views(
            page=page,
            peer_specs=[1, 2],
            trusted_specs=[3],
            refresh_trusted=True,
            refresh_cluster_page=cluster_refresh,
            status_label=status_label,
            discovered_candidates=candidates,
        )

        page.refresh_discovered.assert_called_once_with([1, 2])
        page.refresh_trusted.assert_called_once_with([3])
        cluster_refresh.assert_called_once_with()
        status_label.config.assert_called_once_with(
            text="Discovered 2 untrusted peers: alpha, beta"
        )
        status_label.pack.assert_called_once_with(anchor="w", pady=(2, 0))

    def test_refresh_discovery_views_skips_trusted_refresh_when_unneeded(self) -> None:
        page = Mock()
        cluster_refresh = Mock()
        status_label = Mock()

        refresh_discovery_views(
            page=page,
            peer_specs=[],
            trusted_specs=[3],
            refresh_trusted=False,
            refresh_cluster_page=cluster_refresh,
            status_label=status_label,
            discovered_candidates=[],
        )

        page.refresh_discovered.assert_called_once_with([])
        page.refresh_trusted.assert_not_called()
        cluster_refresh.assert_called_once_with()
        status_label.pack_forget.assert_called_once_with()

    def test_post_discovery_refresh_defers_when_hidden_until_flushed(self) -> None:
        coordinator = AppCoordinator(deliver=lambda callback: callback())
        page = Mock()
        cluster_refresh = Mock()
        status_label = Mock()
        candidates = [Mock(hostname="hidden")]

        post_discovery_refresh(
            coordinator=coordinator,
            key="discovery-pages",
            page=page,
            get_peer_specs=lambda: ["latest"],
            get_trusted_specs=list,
            should_refresh_trusted=lambda: False,
            refresh_cluster_page=cluster_refresh,
            status_label=status_label,
            get_discovered_candidates=lambda: candidates,
            visible=False,
        )

        page.refresh_discovered.assert_not_called()
        coordinator.flush_deferred("discovery-pages")
        page.refresh_discovered.assert_called_once_with(["latest"])
        cluster_refresh.assert_called_once_with()

    def test_deferred_refresh_preserves_trusted_pending_until_render(self) -> None:
        coordinator = AppCoordinator(deliver=lambda callback: callback())
        page = Mock()
        pending = [True]

        post_discovery_refresh(
            coordinator=coordinator,
            key="discovery-pages",
            page=page,
            get_peer_specs=list,
            get_trusted_specs=lambda: ["trusted"],
            should_refresh_trusted=lambda: pending.pop(),
            refresh_cluster_page=Mock(),
            status_label=None,
            get_discovered_candidates=list,
            visible=False,
        )

        self.assertEqual(pending, [True])
        coordinator.flush_deferred("discovery-pages")
        page.refresh_trusted.assert_called_once_with(["trusted"])
