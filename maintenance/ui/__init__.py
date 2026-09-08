"""Shared presentation layer for the System Analyzer UI.

This package owns design tokens and reusable presentation primitives only.
It never imports the app controller, scanners, managers, or network code,
and importing it has no side effects (no Tk root is created).

- ``styles``: design tokens (colours, fonts, style names) and style registration.
- ``layout``: reusable widget construction (scrollable areas, metric rows,
  dialog shells, footers).
- ``telemetry_graph``: the lightweight thermal graph widget used in detail
  views and the Thermals page.
- ``scan_status``: the shared global scan-presentation state (wording and styles).
- ``transition``: the latest-wins cancellable delayed state-change rule used
  for smooth status transitions.
"""

from .action_coordinator import ButtonCoordinator
from .layout import (
    FOOTER_GUTTER,
    SCROLLBAR_GUTTER,
    boolean_setting_row,
    dashboard_header,
    dialog_footer,
    dialog_heading,
    dialog_shell,
    fit_wrap_to_width,
    metric_row,
    metric_value_wrap,
    next_wrap_width,
    pack_action_buttons,
    resize_aware,
    scrollable_area,
    section_card,
    setting_row,
)
from .navigation import PageBuilder, PageRouter, PageSpec
from .scan_status import (
    ANALYSIS_BAR_STYLE,
    BUSY_STYLE,
    CANCELLING_TEXT,
    COMPLETE_BAR_STYLE,
    COMPLETE_TEXT,
    READY_STYLE,
    READY_TEXT,
    SCANNING_TEXT,
    apply_cancelling,
    apply_complete,
    apply_ready,
    apply_reset,
    apply_scanning,
    apply_step,
    progress_text,
)
from .styles import (
    COLORS,
    FONTS,
    STYLE_APP_FRAME,
    STYLE_BAR_ANALYSIS,
    STYLE_BAR_CARD,
    STYLE_BAR_COMPLETE,
    STYLE_CHECKBUTTON,
    STYLE_DANGER_BUTTON,
    STYLE_DESCRIPTION,
    STYLE_HEALTH_WARNING,
    STYLE_HEALTHY,
    STYLE_NEUTRAL_BUTTON,
    STYLE_PRIMARY_BUTTON,
    STYLE_SECTION,
    STYLE_SPINBOX,
    STYLE_STATUS_BUSY,
    STYLE_STATUS_READY,
    STYLE_TITLE,
    configure_app_styles,
)
from .telemetry_graph import TelemetryMiniGraph
from .thermals_page import ThermalsPage, ThermalsPageCallbacks
from .transition import PendingTransition

__all__ = [
    "ANALYSIS_BAR_STYLE",
    "BUSY_STYLE",
    "CANCELLING_TEXT",
    "COLORS",
    "COMPLETE_BAR_STYLE",
    "COMPLETE_TEXT",
    "FONTS",
    "FOOTER_GUTTER",
    "READY_STYLE",
    "READY_TEXT",
    "SCANNING_TEXT",
    "SCROLLBAR_GUTTER",
    "STYLE_APP_FRAME",
    "STYLE_BAR_ANALYSIS",
    "STYLE_BAR_CARD",
    "STYLE_BAR_COMPLETE",
    "STYLE_CHECKBUTTON",
    "STYLE_DANGER_BUTTON",
    "STYLE_DESCRIPTION",
    "STYLE_HEALTHY",
    "STYLE_HEALTH_WARNING",
    "STYLE_NEUTRAL_BUTTON",
    "STYLE_PRIMARY_BUTTON",
    "STYLE_SECTION",
    "STYLE_SPINBOX",
    "STYLE_STATUS_BUSY",
    "STYLE_STATUS_READY",
    "STYLE_TITLE",
    "ButtonCoordinator",
    "PageBuilder",
    "PageRouter",
    "PageSpec",
    "PendingTransition",
    "TelemetryMiniGraph",
    "ThermalsPage",
    "ThermalsPageCallbacks",
    "apply_cancelling",
    "apply_complete",
    "apply_ready",
    "apply_reset",
    "apply_scanning",
    "apply_step",
    "boolean_setting_row",
    "configure_app_styles",
    "dashboard_header",
    "dialog_footer",
    "dialog_heading",
    "dialog_shell",
    "fit_wrap_to_width",
    "metric_row",
    "metric_value_wrap",
    "next_wrap_width",
    "pack_action_buttons",
    "progress_text",
    "resize_aware",
    "scrollable_area",
    "section_card",
    "setting_row",
]
