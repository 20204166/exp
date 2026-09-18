"""Window node integration tests: selector, switching, isolation, discovery."""

import sys
import unittest
from typing import Any
from unittest.mock import Mock

from maintenance.cluster import ClusterState
from maintenance.components.coordinator import AppCoordinator, ComponentRefreshScheduler
from maintenance.models import CapabilityState
from maintenance.nodes import (
    NodeCapability,
    NodeContext,
    NodePermission,
    NodeRegistry,
    NodeStatus,
    NodeTrustState,
)
from tests.support.models import make_snapshot, make_summary
from tests.support.nodes import make_candidate, make_local_context, make_remote_context
from tests.support.window import make_window as make_bare_window


def _summary(key: str, value: str = "10%") -> Any:
    return make_summary(key, key, value=value, capability=CapabilityState.SUPPORTED)


def _local_context(analyzer: Any = None) -> NodeContext:
    return make_local_context(
        provider=analyzer,
        process_manager=Mock(),
        file_manager=Mock(),
        scheduler=ComponentRefreshScheduler(),
        coordinator=AppCoordinator(),
        snapshot=make_snapshot(_summary("cpu", "local-cpu"), system_label="local-host"),
        capabilities={"cpu": CapabilityState.SUPPORTED},
    )


def _trusted_context(
    node_id: str,
    display_name: str,
    *,
    cpu_value: str,
    host_label: str,
    capabilities: frozenset[NodeCapability] = frozenset(),
) -> NodeContext:
    context = make_remote_context(
        node_id,
        trust=NodeTrustState.TRUSTED,
        status=NodeStatus.ONLINE,
        display_name=display_name,
        hostname=node_id,
        capabilities=capabilities,
        platform="Linux",
        permissions=frozenset(NodePermission),
        provider=Mock(),
        process_manager=Mock(),
        file_manager=Mock(),
        scheduler=ComponentRefreshScheduler(),
        coordinator=AppCoordinator(),
        snapshot=make_snapshot(_summary("cpu", cpu_value), system_label=host_label),
    )
    context.capabilities = {"cpu": CapabilityState.SUPPORTED}
    return context


def _make_window(
    *contexts: NodeContext,
    start_discovery: bool = True,
) -> Any:
    window = make_bare_window(
        _feature_catalog=Mock(),
        _coordinator=AppCoordinator(deliver=lambda callback: callback()),
        _cluster_state=ClusterState(),
        _manual_host_ids=set(),
        _capabilities={},
        _preferences=Mock(),
        _discovery_tick_id=None,
    )
    window._feature_catalog.all = list
    window._preferences.refresh_intervals.as_dict = dict
    window._preferences.visible_cards = frozenset()
    window._preferences.hide_unavailable_cards = False

    registry = NodeRegistry()
    local_ctx = _local_context()
    registry.register_context(local_ctx)
    for context in contexts:
        registry.register_context(context)
    registry.select(local_ctx.node_id)
    window._node_registry = registry
    window._selected_node_id = registry.selected_id()
    window.analyzer = local_ctx.provider
    window.process_manager = local_ctx.process_manager
    window.file_manager = local_ctx.file_manager
    window.snapshot = local_ctx.snapshot
    window._reconcile_intervals = Mock()
    window._reconcile_cards_and_polling = Mock()

    window.status_label = Mock()
    window.progress_bar = Mock()
    window.refreshed_label = Mock()
    window.scan_time_label = Mock()
    window.health_label = Mock()
    window.cards = {}
    window._refresh_health = Mock()
    window._schedule_timer = Mock(return_value="timer-1")
    window._cancel_timer = Mock(return_value=True)
    window._schedule_component_poll = Mock()
    window.handle_analyze = Mock()
    window._start_background_poll = Mock()
    window._show_progress = Mock()
    window._set_busy = Mock()
    window._reset_progress_bar = Mock()
    window._completion_transition = Mock()
    window._cancel_pending_timers = Mock()
    window._layout_dashboard_cards = Mock()
    window._refresh_cards_scrollbar = Mock()

    if start_discovery:
        window._start_discovery()
    return window


def _candidate(stable_id: str, fingerprint: str | None = None) -> Any:
    return make_candidate(
        stable_id,
        hostname=f"{stable_id}-host",
        last_seen=1.0,
        identity_fingerprint=fingerprint,
    )


sys.modules.setdefault("tests.test_window_nodes", sys.modules[__name__])


from tests.window_node_cases.selector import WindowNodeSelectorTests  # noqa: F401, I001
from tests.window_node_cases.connections import WindowNodeConnectionTests, PeerOfflineDebounceTests  # noqa: F401
from tests.window_node_cases.switching import WindowNodeSwitchingTests  # noqa: F401
from tests.window_node_cases.discovery_pairing import WindowDiscoveryIntegrationTests, Phase10ThreadingTests  # noqa: F401
from tests.window_node_cases.resources import WindowOpenResourceNodeTests  # noqa: F401
from tests.window_node_cases.roles import RemoteRoleOperationTests  # noqa: F401


if __name__ == "__main__":
    unittest.main()
