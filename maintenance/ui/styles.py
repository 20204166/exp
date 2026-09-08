"""Shared presentation tokens and ttk style registration for the UI layer.

This module owns the single source of truth for the design tokens (colours,
fonts, style names) used by the dashboard and its dialogs. Importing it has
no side effects: no Tk root is created and no styles are registered until
``configure_app_styles`` is called with a real ``ttk.Style``. Widget
construction stays in the caller, which supplies its own tkinter widget
classes so existing test seams keep resolving.
"""

from typing import Any

Font = tuple[Any, ...]

COLORS: dict[str, str] = {
    "background": "#F4F7FB",
    "card": "#FFFFFF",
    "text": "#172033",
    "secondary": "#667085",
    "accent": "#4F46E5",
    "accent_active": "#4338CA",
    "border": "#E4E7EC",
    "success": "#16803C",
    "warning": "#B45309",
    "danger": "#B42318",
    "danger_active": "#912018",
    "disabled": "#D0D5DD",
    "primary_disabled": "#A5B4FC",
    "primary_disabled_text": "#EEF2FF",
    "bar_trough": "#E8ECF5",
    "card_bar_trough": "#EEF2F6",
    "button_bg": "#E3E4E8",
    "button_bg_active": "#D4D8E0",
    "muted_text": "#98A2B3",
    "graph_grid": "#D9E0EC",
    "graph_empty_border": "#CBD5E1",
}

SPACING: dict[str, int] = {
    "page_x": 30,
    "page_y": 26,
    "section_gap": 14,
    "row_gap": 10,
    "control_gap": 12,
}

GRAPH: dict[str, int] = {
    "height": 108,
    "width": 520,
    "max_points": 240,
}

FONTS: dict[str, Font] = {
    "ui": ("Helvetica",),
    "title": ("Helvetica", 24, "bold"),
    "section": ("Helvetica", 14, "bold"),
    "body": ("Helvetica", 10),
    "button": ("Helvetica", 11, "bold"),
    "danger_button": ("Helvetica", 10, "bold"),
    "status": ("Helvetica", 10, "bold"),
    "card_overline": ("Helvetica", 10, "bold"),
    "card_headline": ("Helvetica", 22, "bold"),
    "card_subtitle": ("Helvetica", 10),
    "card_metric": ("Helvetica", 9),
    "dialog_heading": ("Helvetica", 20, "bold"),
    "info_heading": ("Helvetica", 22, "bold"),
    "info_subtitle": ("Helvetica", 11),
    "info_headline": ("Helvetica", 20, "bold"),
    "dialog_description": ("Helvetica", 10),
    "detail_section": ("Helvetica", 11, "bold"),
    "detail_row": ("Helvetica", 10),
    "empty_detail": ("Helvetica", 11),
    "status_text": ("Helvetica", 10),
}

STYLE_APP_FRAME = "App.TFrame"
STYLE_TITLE = "Title.TLabel"
STYLE_SECTION = "Section.TLabel"
STYLE_DESCRIPTION = "Description.TLabel"
STYLE_NODE = "Node.TLabel"
STYLE_HEALTHY = "Healthy.TLabel"
STYLE_HEALTH_WARNING = "HealthWarning.TLabel"
STYLE_PRIMARY_BUTTON = "Primary.TButton"
STYLE_NEUTRAL_BUTTON = "Neutral.TButton"
STYLE_DANGER_BUTTON = "Danger.TButton"
STYLE_STATUS_READY = "Ready.Status.TLabel"
STYLE_STATUS_BUSY = "Busy.Status.TLabel"
STYLE_SPINBOX = "App.TSpinbox"
STYLE_CHECKBUTTON = "App.TCheckbutton"
STYLE_BAR_ANALYSIS = "Analysis.Horizontal.TProgressbar"
STYLE_BAR_COMPLETE = "Complete.Horizontal.TProgressbar"
STYLE_BAR_CARD = "Card.Horizontal.TProgressbar"

DEFAULT_APPEARANCE = "indigo"

NODE_COLORS: dict[str, str] = {
    "indigo": "#4F46E5",
    "emerald": "#047857",
    "rose": "#E11D48",
    "amber": "#B45309",
    "sky": "#0369A1",
    "violet": "#7C3AED",
    "teal": "#0F766E",
    "slate": "#475569",
}

ACCENT_THEMES: dict[str, dict[str, str]] = {
    "indigo": {
        "accent": "#4F46E5",
        "accent_active": "#4338CA",
        "primary_disabled": "#A5B4FC",
        "primary_disabled_text": "#EEF2FF",
    },
    "emerald": {
        "accent": "#047857",
        "accent_active": "#065F46",
        "primary_disabled": "#A7F3D0",
        "primary_disabled_text": "#ECFDF5",
    },
    "rose": {
        "accent": "#E11D48",
        "accent_active": "#BE123C",
        "primary_disabled": "#FDA4AF",
        "primary_disabled_text": "#FFF1F2",
    },
    "amber": {
        "accent": "#B45309",
        "accent_active": "#92400E",
        "primary_disabled": "#FCD34D",
        "primary_disabled_text": "#FFFBEB",
    },
    "sky": {
        "accent": "#0369A1",
        "accent_active": "#075985",
        "primary_disabled": "#7DD3FC",
        "primary_disabled_text": "#F0F9FF",
    },
}


def accent_theme_colors(
    theme: str,
    *,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return a full colour token map with one accent theme applied.

    Unknown themes fall back to the default appearance, so a stale persisted
    choice can never break style registration.
    """

    tokens = ACCENT_THEMES.get(theme, ACCENT_THEMES[DEFAULT_APPEARANCE])
    colors = dict(COLORS if base is None else base)
    colors.update(tokens)
    return colors


def configure_app_styles(
    style: Any,
    colors: dict[str, str] | None = None,
    fonts: dict[str, Font] | None = None,
) -> None:
    """Register every ttk style used by the dashboard and its dialogs.

    ``style`` is a ``ttk.Style`` bound to the live application root. The
    optional token dictionaries default to this module's ``COLORS`` and
    ``FONTS`` so callers can override them for tests without touching the
    shared token source.
    """

    c = COLORS if colors is None else colors
    f = FONTS if fonts is None else fonts

    style.configure(
        STYLE_APP_FRAME,
        background=c["background"],
    )
    style.configure(
        STYLE_TITLE,
        background=c["background"],
        foreground=c["text"],
        font=f["title"],
    )
    style.configure(
        STYLE_SECTION,
        background=c["background"],
        foreground=c["text"],
        font=f["section"],
    )
    style.configure(
        STYLE_DESCRIPTION,
        background=c["background"],
        foreground=c["secondary"],
        font=f["body"],
    )
    style.configure(
        STYLE_NODE,
        background=c["background"],
        foreground=c["secondary"],
        font=("Helvetica", 9, "bold"),
    )
    style.configure(
        STYLE_HEALTHY,
        background=c["background"],
        foreground=c["success"],
        font=f["body"],
    )
    style.configure(
        STYLE_HEALTH_WARNING,
        background=c["background"],
        foreground=c["warning"],
        font=f["body"],
    )
    style.configure(
        STYLE_PRIMARY_BUTTON,
        background=c["accent"],
        foreground="#FFFFFF",
        font=f["button"],
        padding=(18, 11),
        borderwidth=0,
        focusthickness=0,
        focuscolor=c["accent"],
    )
    style.map(
        STYLE_PRIMARY_BUTTON,
        background=[
            ("active", c["accent_active"]),
            ("disabled", c["primary_disabled"]),
        ],
        foreground=[("disabled", c["primary_disabled_text"])],
    )
    style.configure(
        STYLE_DANGER_BUTTON,
        background=c["danger"],
        foreground="#FFFFFF",
        font=f["danger_button"],
        padding=(12, 8),
    )
    style.map(
        STYLE_DANGER_BUTTON,
        background=[("active", c["danger_active"]), ("disabled", c["disabled"])],
    )
    style.configure(
        STYLE_NEUTRAL_BUTTON,
        background=c["button_bg"],
        foreground=c["text"],
        font=f["danger_button"],
        padding=(12, 8),
        bordercolor=c["border"],
    )
    style.map(
        STYLE_NEUTRAL_BUTTON,
        background=[("active", c["button_bg_active"]), ("disabled", c["disabled"])],
        foreground=[("disabled", c["muted_text"])],
    )
    style.configure(
        STYLE_STATUS_READY,
        background=c["background"],
        foreground=c["success"],
        font=f["status"],
    )
    style.configure(
        STYLE_STATUS_BUSY,
        background=c["background"],
        foreground=c["warning"],
        font=f["status"],
    )
    style.configure(
        STYLE_BAR_ANALYSIS,
        background=c["accent"],
        troughcolor=c["bar_trough"],
        borderwidth=0,
        lightcolor=c["accent"],
        darkcolor=c["accent"],
    )
    style.configure(
        STYLE_SPINBOX,
        background=c["card"],
        foreground=c["text"],
        fieldbackground=c["card"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
        arrowcolor=c["secondary"],
        padding=4,
        font=f["body"],
    )
    style.map(
        STYLE_SPINBOX,
        foreground=[("disabled", c["disabled"])],
        fieldbackground=[("disabled", c["background"])],
    )
    style.configure(
        STYLE_CHECKBUTTON,
        background=c["card"],
        foreground=c["text"],
        font=f["body"],
    )
    style.map(
        STYLE_CHECKBUTTON,
        background=[("active", c["card"])],
        foreground=[("disabled", c["disabled"])],
    )
    style.configure(
        STYLE_BAR_COMPLETE,
        background=c["success"],
        troughcolor=c["bar_trough"],
        borderwidth=0,
        lightcolor=c["success"],
        darkcolor=c["success"],
    )
    style.configure(
        STYLE_BAR_CARD,
        background=c["accent"],
        troughcolor=c["card_bar_trough"],
        borderwidth=0,
        lightcolor=c["accent"],
        darkcolor=c["accent"],
    )
