"""Page composition helpers delegated from the application controller."""

from typing import Any, cast

from maintenance import __version__
from maintenance.ui import cluster_page as ui_cluster
from maintenance.ui import diagnostics_page as ui_diagnostics
from maintenance.ui import nodes_connections as ui_nodes
from maintenance.ui import preferences_page as ui_preferences
from maintenance.ui import render_coordinator as ui_render
from maintenance.ui import settings_home as ui_settings_home
from maintenance.ui import styles as ui_styles
from maintenance.ui import thermals_page as ui_thermals


def build_settings_home(controller: Any, parent: Any) -> Any:
    controller.settings_frame = controller.ttk.Frame(
        parent,
        padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
        style="App.TFrame",
    )
    controller.settings_home = ui_settings_home.SettingsHome(
        controller.settings_frame,
        callbacks=ui_settings_home.SettingsHomeCallbacks(
            on_back=controller._show_dashboard_page,
            on_select_category=controller._on_select_settings_category,
        ),
        categories=controller._settings_categories(),
        version=__version__,
        button_coordinator=controller._button_coordinator,
    )
    return controller.settings_frame


def build_preferences(controller: Any, parent: Any) -> Any:
    controller.preferences_frame = controller.ttk.Frame(
        parent,
        padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
        style="App.TFrame",
    )
    controller.preferences_page = ui_preferences.PreferencesPage(
        controller.preferences_frame,
        callbacks=ui_preferences.PreferencesPageCallbacks(
            on_back=controller._show_settings_page,
            on_interval_commit=controller._on_interval_commit,
            on_card_visibility_change=controller._on_card_visibility_change,
            on_auto_hide_change=controller._on_auto_hide_change,
            on_scan=controller.handle_analyze,
            on_cancel_scan=controller._cancel_analysis,
            on_reset=controller._on_reset,
            on_appearance_change=controller._on_appearance_change,
        ),
        intervals=controller._interval_specs(),
        cards=controller._card_specs(),
        hide_unavailable_cards=controller._preferences.hide_unavailable_cards,
        appearance=controller._preferences.appearance,
        button_coordinator=controller._button_coordinator,
    )
    controller.analyze_button = controller.preferences_page.analyze_button
    controller.cancel_button = controller.preferences_page.cancel_button
    controller.preferences_status_label = (
        controller.preferences_page.manual_status_label
    )
    controller.preferences_progress_bar = (
        controller.preferences_page.manual_progress_bar
    )
    return controller.preferences_frame


def build_diagnostics(controller: Any, parent: Any) -> Any:
    controller.diagnostics_frame = controller.ttk.Frame(
        parent,
        padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
        style="App.TFrame",
    )
    controller.diagnostics_page = ui_diagnostics.DiagnosticsPage(
        controller.diagnostics_frame,
        callbacks=ui_diagnostics.DiagnosticsPageCallbacks(
            on_back=controller._show_settings_page,
            on_copy=controller._copy_diagnostics,
        ),
        snapshot=controller._diagnostics_snapshot(),
        button_coordinator=controller._button_coordinator,
        colors=controller.colors,
    )
    return controller.diagnostics_frame


def build_thermals(controller: Any, parent: Any) -> Any:
    controller.thermals_frame = controller.ttk.Frame(
        parent,
        padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
        style="App.TFrame",
    )
    controller.thermals_page = ui_thermals.ThermalsPage(
        controller.thermals_frame,
        callbacks=ui_thermals.ThermalsPageCallbacks(
            on_back=controller._show_dashboard_page,
        ),
        colors=controller.colors,
    )
    return controller.thermals_frame


def build_nodes(controller: Any, parent: Any) -> Any:
    controller.nodes_frame = controller.ttk.Frame(
        parent,
        padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
        style="App.TFrame",
    )
    controller.nodes_page = ui_nodes.NodesConnectionsPage(
        controller.nodes_frame,
        callbacks=ui_nodes.NodesConnectionsCallbacks(
            on_back=controller._show_settings_page,
            on_discovery_toggle=controller._apply_discovery_enabled,
            on_start_discovery=controller._start_discovery_from_nodes,
            on_pair=controller._pair_discovered_node,
            on_reject=controller._reject_discovered_node,
            on_rename=controller._rename_node,
            on_color=controller._set_node_color,
            on_revoke=controller._revoke_node,
            on_test_connection=controller._test_connection,
            on_open_node=controller._open_cluster_node,
            on_add_manual_host=controller._add_manual_host,
            on_remove_manual=controller._remove_manual_host,
            on_permissions=controller._set_node_permissions,
            on_role_change=controller._set_node_roles,
            on_pause=controller._pause_node,
            on_resume=controller._resume_node,
            on_remove_connection=controller._remove_connection_node,
            on_remove_job=controller._remove_job_node,
        ),
        discovery_enabled=controller._cluster_state.discovery_enabled,
        discovered=controller._nodes_peer_specs(),
        trusted=controller._nodes_trusted_specs(),
        manual=controller._nodes_manual_specs(),
        button_coordinator=controller._button_coordinator,
    )
    return controller.nodes_frame


def build_cluster(controller: Any, parent: Any) -> Any:
    controller.cluster_frame = controller.ttk.Frame(
        parent,
        padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
        style="App.TFrame",
    )
    controller.cluster_page = ui_cluster.ClusterPage(
        controller.cluster_frame,
        callbacks=ui_cluster.ClusterPageCallbacks(
            on_back=controller._show_dashboard_page,
            on_open_node=controller._open_cluster_node,
            on_pause=controller._pause_node,
            on_resume=controller._resume_node,
            on_revoke=controller._revoke_node,
            on_remove_connection=controller._remove_connection_node,
            on_remove_job=controller._remove_job_node,
            on_share_dashboard=controller._share_dashboard,
        ),
        nodes=controller._cluster_specs(),
        button_coordinator=controller._button_coordinator,
    )
    return controller.cluster_frame


def select_settings_category(controller: Any, key: str) -> None:
    handler = {
        "preferences": controller._show_preferences_page,
        "nodes": controller._show_nodes_page,
        "cluster": controller._show_cluster_page,
        "diagnostics": controller._show_diagnostics_page,
    }.get(key)
    if handler is not None:
        handler()


def show_page(controller: Any, page_name: str, focus_attribute: str) -> None:
    controller._page_router.show(page_name)
    controller._sync_render_visibility(page_name)
    controller._set_diagnostics_visibility(page_name == "diagnostics")
    page = getattr(controller, focus_attribute, None)
    if page is not None:
        page.focus_back()


def show_dashboard(controller: Any) -> None:
    controller._page_router.show("dashboard")
    controller._sync_render_visibility("dashboard")
    controller._set_diagnostics_visibility(False)
    button = getattr(controller, "settings_button", None)
    if button is not None:
        button.focus_set()


def show_thermals(controller: Any) -> None:
    page = getattr(controller, "thermals_page", None)
    context = controller._selected_context()
    if page is not None:
        page.render(
            controller._thermal_render_state(context) if context is not None else None,
            getattr(context, "capabilities", None) if context is not None else None,
        )
    show_page(controller, "thermals", "thermals_page")


def refresh_nodes(controller: Any) -> None:
    page = getattr(controller, "nodes_page", None)
    if page is None:
        return
    page.set_discovery_enabled(controller._cluster_state.discovery_enabled)
    page.refresh_discovered(controller._nodes_peer_specs())
    page.refresh_trusted(controller._nodes_trusted_specs())
    page.refresh_manual(controller._nodes_manual_specs())


def set_nodes_status(controller: Any, message: str, *, error: bool) -> None:
    page = getattr(controller, "nodes_page", None)
    if page is None:
        return
    renderer = page.show_error if error else page.show_status
    controller._request_render(
        ui_render.RenderIntent(
            target="nodes-status", payload=message, payload_set=True, priority=1
        ),
        lambda intent: renderer(cast(str, intent.payload)),
    )


def refresh_cluster(controller: Any) -> None:
    page = getattr(controller, "cluster_page", None)
    if page is not None:
        page.refresh_nodes(controller._cluster_specs())
