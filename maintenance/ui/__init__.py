"""Shared presentation layer with deliberately lazy compatibility exports.

Importing the package does not select a UI toolkit. Prefer explicit imports
from the owning submodule; legacy package-level names resolve on demand.
"""

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, str] = {
    **dict.fromkeys(("ButtonCoordinator",), "action_coordinator"),
    **dict.fromkeys(("PageBuilder", "PageRouter", "PageSpec"), "navigation"),
    **dict.fromkeys(("PendingTransition",), "transition"),
    **dict.fromkeys(
        (
            "TargetPresentation",
            "TargetState",
            "render_target_state",
            "target_status_text",
        ),
        "target_state",
    ),
    **dict.fromkeys(("TelemetryMiniGraph",), "telemetry_graph"),
    **dict.fromkeys(("ThermalsPage", "ThermalsPageCallbacks"), "thermals_page"),
    **dict.fromkeys(
        (
            "apply_cancelling",
            "apply_complete",
            "apply_ready",
            "apply_reset",
            "apply_scanning",
            "apply_step",
            "progress_text",
            "ANALYSIS_BAR_STYLE",
            "BUSY_STYLE",
            "CANCELLING_TEXT",
            "COMPLETE_BAR_STYLE",
            "COMPLETE_TEXT",
            "READY_STYLE",
            "READY_TEXT",
            "SCANNING_TEXT",
        ),
        "scan_status",
    ),
    **dict.fromkeys(
        (
            "COLORS",
            "FONTS",
            "GRAPH",
            "SPACING",
            "STYLE_APP_FRAME",
            "STYLE_BAR_ANALYSIS",
            "STYLE_BAR_CARD",
            "STYLE_BAR_COMPLETE",
            "STYLE_CHECKBUTTON",
            "STYLE_DANGER_BUTTON",
            "STYLE_DESCRIPTION",
            "STYLE_HEALTH_WARNING",
            "STYLE_HEALTHY",
            "STYLE_NEUTRAL_BUTTON",
            "STYLE_PRIMARY_BUTTON",
            "STYLE_SECTION",
            "STYLE_SPINBOX",
            "STYLE_STATUS_BUSY",
            "STYLE_STATUS_READY",
            "STYLE_TITLE",
            "configure_app_styles",
        ),
        "styles",
    ),
    **dict.fromkeys(
        (
            "FOOTER_GUTTER",
            "SCROLLBAR_GUTTER",
            "boolean_setting_row",
            "dashboard_header",
            "dialog_footer",
            "dialog_heading",
            "dialog_shell",
            "event_row",
            "fit_wrap_to_width",
            "metric_row",
            "metric_value_wrap",
            "navigation_card",
            "next_wrap_width",
            "pack_action_buttons",
            "resize_aware",
            "scrollable_area",
            "section_card",
            "setting_row",
        ),
        "layout",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module_name}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *_EXPORTS))
