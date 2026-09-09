"""Dashboard page construction delegated from the application controller."""

from typing import Any

from maintenance.dialogs import ResourceCard
from maintenance.ui import discovery_refresh as ui_discovery_refresh
from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles


def build(controller: Any, parent: Any) -> Any:
    """Build the dashboard while keeping controller callbacks and test seams."""

    controller.main_frame = controller.ttk.Frame(
        parent,
        padding=(ui_styles.SPACING["page_x"], ui_styles.SPACING["page_y"]),
        style="App.TFrame",
    )

    node_title = None
    if controller._multi_node_selectable():
        context = controller._selected_context()
        if context is not None:
            node_title = context.descriptor.display_name

    controller.header_actions = ui_layout.dashboard_header(
        controller.main_frame,
        title="System Analyzer",
        description=(
            "Scan your system, open any category, and review safe cleanup "
            "actions before anything changes."
        ),
        frame_cls=controller.ttk.Frame,
        label_cls=controller.ttk.Label,
        wrap=680,
        node_title=node_title,
    )
    controller.node_title_label = getattr(
        controller.header_actions, "_dashboard_node_label", None
    )
    controller.discovery_status_label = getattr(
        controller.header_actions, "_dashboard_discovery_label", None
    )
    ui_discovery_refresh.render_discovery_status(
        controller.discovery_status_label,
        controller._node_registry.discovered_candidates(),
    )

    navigation_buttons = controller.ttk.Frame(
        controller.header_actions,
        style="App.TFrame",
    )
    navigation_buttons.pack(anchor="e")

    for attribute, text, callback in (
        ("cluster_button", "All Systems", controller._show_cluster_page),
        ("thermals_button", "Thermals", controller._show_thermals_page),
        ("settings_button", "Settings", controller._show_settings_page),
    ):
        button = controller.ttk.Button(
            navigation_buttons,
            text=text,
            command=callback,
            style="Neutral.TButton",
            cursor="hand2",
        )
        setattr(controller, attribute, button)

    for action_id, button, callback in (
        (
            "dashboard:settings",
            controller.settings_button,
            controller._show_settings_page,
        ),
        ("dashboard:cluster", controller.cluster_button, controller._show_cluster_page),
        (
            "dashboard:thermals",
            controller.thermals_button,
            controller._show_thermals_page,
        ),
    ):
        controller._button_coordinator.register(action_id, callback, replace=True)
        controller._button_coordinator.bind(button, action_id)
    controller._build_node_selector(controller.header_actions)
    controller.settings_button.pack(side="left")
    controller.cluster_button.pack(side="left", padx=(8, 0))
    controller.thermals_button.pack(side="left", padx=(8, 0))

    controller.status_label = controller.ttk.Label(
        controller.header_actions,
        text="●  Ready",
        style="Ready.Status.TLabel",
    )
    controller.status_label.pack(anchor="e", pady=(9, 0))
    controller.overview_frame = controller.ttk.Frame(
        controller.main_frame, style="App.TFrame"
    )
    controller.overview_frame.pack(fill="x", pady=(0, 10))
    controller.ttk.Label(
        controller.overview_frame, text="System overview", style="Section.TLabel"
    ).pack(side="left")
    controller.scan_time_label = controller.ttk.Label(
        controller.overview_frame,
        text="Not scanned yet",
        style="Description.TLabel",
    )
    controller.scan_time_label.pack(side="right")

    controller.cards_container = controller.ttk.Frame(
        controller.main_frame, style="App.TFrame"
    )
    controller.cards_container.pack(fill="both", expand=True)
    (
        controller.cards_canvas,
        controller.cards_frame,
        controller._refresh_cards_scrollbar,
    ) = ui_layout.scrollable_area(
        controller.cards_container,
        bg=controller.BACKGROUND,
        frame_cls=controller.ttk.Frame,
        canvas_cls=controller.tk.Canvas,
        scrollbar_cls=controller.ttk.Scrollbar,
        frame_kwargs={"style": "App.TFrame"},
    )
    for column in range(3):
        controller.cards_frame.grid_columnconfigure(column, weight=1, uniform="cards")

    controller.cards = {}
    for index, feature in enumerate(controller._feature_catalog.all()):
        action_id = f"dashboard:resource:{feature.key}"
        controller._button_coordinator.register(
            action_id,
            lambda key=feature.key: controller.open_resource(key),
            replace=True,
        )
        card = ResourceCard(
            controller.cards_frame,
            key=feature.key,
            title=feature.title,
            on_open=controller.open_resource,
            colors=controller.colors,
            action_id=action_id,
            button_coordinator=controller._button_coordinator,
        )
        controller._grid_card(card, index, 3)
        controller.cards[feature.key] = card
    controller.cards_empty_label = None

    controller.refreshed_label = controller.ttk.Label(
        controller.main_frame,
        text="Not refreshed yet",
        style="Description.TLabel",
    )
    controller.refreshed_label.pack(anchor="w", pady=(4, 0))
    controller.health_label = controller.ttk.Label(
        controller.main_frame,
        text="Health: No issues detected",
        style="Healthy.TLabel",
    )
    controller.health_label.pack(anchor="w", pady=(2, 0))
    controller._layout_dashboard_cards()
    return controller.main_frame
