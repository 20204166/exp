"""Dashboard page construction delegated from the application controller."""

from typing import Any

from maintenance.dialogs import ResourceCard
from maintenance.ui import discovery_refresh as ui_discovery_refresh
from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles
from maintenance.ui.target_state import render_target_state


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
        wrap=ui_styles.LAYOUT["dashboard_description_wrap"],
        node_title=node_title,
    )
    controller.node_title_label = getattr(
        controller.header_actions, "_dashboard_node_label", None
    )
    controller.target_status_text = (
        f"{rendered.label} · {rendered.identity} · "
        f"capabilities: {', '.join(rendered.capabilities) or 'none'}"
        if (context := controller._selected_context()) is not None
        and (rendered := render_target_state(context.descriptor, context.snapshot))
        else ""
    )
    controller.discovery_status_label = getattr(
        controller.header_actions, "_dashboard_discovery_label", None
    )
    ui_discovery_refresh.render_discovery_status(
        controller.discovery_status_label,
        controller._node_registry.discovered_candidates(),
    )

    navigation_frame = controller.ttk.Frame(
        controller.header_actions,
        style="App.TFrame",
    )
    navigation_frame.pack(anchor="e")

    navigation_specs = (
        ("settings_button", "Settings", controller._show_settings_page),
        ("cluster_button", "All Systems", controller._show_cluster_page),
        ("thermals_button", "Thermals", controller._show_thermals_page),
    )
    navigation_buttons: list[Any] = []
    for attribute, text, callback in navigation_specs:
        button = controller.ttk.Button(
            navigation_frame,
            text=text,
            command=callback,
            style="Neutral.TButton",
            cursor="hand2",
        )
        setattr(controller, attribute, button)
        navigation_buttons.append(button)

    def layout_navigation(_event: Any = None) -> None:
        columns = 3 if controller.main_frame.winfo_width() >= 980 else 2
        for button in navigation_buttons:
            button.grid_forget()
        for index, button in enumerate(navigation_buttons):
            button.grid(
                row=index // columns,
                column=index % columns,
                padx=(
                    0 if index % columns == 0 else ui_styles.LAYOUT["card_grid_gap"],
                    0,
                ),
                pady=(0, 4),
                sticky="e",
            )
        for column in range(3):
            navigation_frame.grid_columnconfigure(
                column,
                weight=1 if column < columns else 0,
            )

    ui_layout.resize_aware(controller.main_frame, layout_navigation)
    layout_navigation()

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
        auto_hide=True,
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

    controller.dashboard_meta_frame = controller.ttk.Frame(
        controller.main_frame, style="App.TFrame"
    )
    controller.dashboard_meta_frame.pack(fill="x", pady=(4, 0))
    controller.refreshed_label = controller.ttk.Label(
        controller.dashboard_meta_frame,
        text="Not refreshed yet",
        style="Description.TLabel",
    )
    controller.refreshed_label.pack(side="left", anchor="w")
    controller.target_status_label = controller.ttk.Label(
        controller.dashboard_meta_frame,
        text=controller.target_status_text,
        justify="right",
        anchor="e",
        wraplength=ui_styles.LAYOUT["dashboard_status_wrap"],
        style="Description.TLabel",
    )
    controller.target_status_label.pack(side="right", anchor="e", padx=(16, 0))
    controller.health_label = controller.ttk.Label(
        controller.main_frame,
        text="Health: No issues detected",
        style="Healthy.TLabel",
    )
    controller.health_label.pack(anchor="w", pady=(2, 0))
    controller._layout_dashboard_cards()
    return controller.main_frame
