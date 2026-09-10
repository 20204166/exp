"""Page data and selected-theme adapters for ``AppWindow``."""

from typing import Any

from maintenance.preferences import INTERVAL_POLICIES
from maintenance.ui import cluster_page as ui_cluster
from maintenance.ui import nodes_connections as ui_nodes
from maintenance.ui import preferences_page as ui_preferences
from maintenance.ui import settings_home as ui_settings_home
from maintenance.ui import styles as ui_styles
from maintenance.ui.window_supports import node_specs


def colors(controller: Any) -> dict[str, str]:
    preferences = controller.__dict__.get("_preferences")
    appearance = (
        preferences.appearance
        if preferences is not None
        and isinstance(getattr(preferences, "appearance", None), str)
        else ui_styles.DEFAULT_APPEARANCE
    )
    return ui_styles.accent_theme_colors(appearance)


def settings_categories(
    _controller: Any,
) -> list[ui_settings_home.SettingsCategorySpec]:
    return [
        ui_settings_home.SettingsCategorySpec(
            "preferences",
            "Preferences",
            "Refresh intervals, visible dashboard cards, scan behaviour, and interface options.",
        ),
        ui_settings_home.SettingsCategorySpec(
            "nodes",
            "Nodes & Connections",
            "Discover peers, pair trusted nodes, manage manual hosts, and control local-network discovery.",
        ),
        ui_settings_home.SettingsCategorySpec(
            "cluster",
            "All Systems",
            "Overview of every known machine and its connection, trust, and capability state.",
        ),
        ui_settings_home.SettingsCategorySpec(
            "diagnostics",
            "Diagnostics",
            "See current work, recent failures, node reasons, and component health.",
        ),
    ]


def interval_specs(controller: Any) -> list[ui_preferences.IntervalControlSpec]:
    intervals = controller._preferences.refresh_intervals.as_dict()
    return [
        ui_preferences.IntervalControlSpec(
            key=feature.key,
            title=feature.title,
            seconds=intervals[feature.key] // 1000,
            minimum_seconds=INTERVAL_POLICIES[feature.key].minimum_ms // 1000,
            maximum_seconds=INTERVAL_POLICIES[feature.key].maximum_ms // 1000,
            step_seconds=INTERVAL_POLICIES[feature.key].step_ms // 1000,
        )
        for feature in controller._feature_catalog.all()
    ]


def card_specs(controller: Any) -> list[ui_preferences.CardControlSpec]:
    return [
        ui_preferences.CardControlSpec(
            feature.key,
            feature.title,
            feature.key in controller._preferences.visible_cards,
        )
        for feature in controller._feature_catalog.all()
    ]


def nodes_peer_specs(controller: Any) -> list[ui_nodes.DiscoveredPeerSpec]:
    registry = controller.__dict__.get("_node_registry")
    return [] if registry is None else node_specs.discovered_peer_specs(registry)


def nodes_trusted_specs(controller: Any) -> list[ui_nodes.TrustedNodeSpec]:
    registry = controller.__dict__.get("_node_registry")
    return (
        []
        if registry is None
        else node_specs.trusted_node_specs(
            registry,
            controller._cluster_state,
            getattr(controller, "_manual_host_ids", set()),
        )
    )


def nodes_manual_specs(controller: Any) -> list[ui_nodes.TrustedNodeSpec]:
    registry = controller.__dict__.get("_node_registry")
    return (
        []
        if registry is None
        else node_specs.manual_node_specs(
            registry,
            controller._cluster_state,
            getattr(controller, "_manual_host_ids", set()),
        )
    )


def cluster_specs(controller: Any) -> list[ui_cluster.ClusterNodeSpec]:
    registry = controller.__dict__.get("_node_registry")
    return [] if registry is None else node_specs.cluster_node_specs(registry)
