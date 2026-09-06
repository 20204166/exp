"""Unit tests for discovery refresh presentation helpers."""

import unittest
from unittest.mock import Mock

from maintenance.ui.discovery_refresh import refresh_discovery_views


class DiscoveryRefreshTests(unittest.TestCase):
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
