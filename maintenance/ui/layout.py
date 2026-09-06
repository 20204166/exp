"""Reusable presentation primitives for dialogs, cards and dashboards.

Every helper here is presentation-only and widget-agnostic about *which*
tkinter it constructs from: callers pass their own widget classes
(``frame_cls``, ``label_cls``, ``canvas_cls``, ...) so existing test seams
that patch e.g. ``maintenance.dialogs.tk.Frame`` keep intercepting widget
creation. Importing this module creates no widgets and no Tk root.
"""

import tkinter as tk
from collections.abc import Callable, Sequence
from typing import Any

from maintenance.ui.styles import Font

SCROLLBAR_GUTTER = 6
FOOTER_GUTTER = 16


def resize_aware(widget: Any, handler: Callable[[Any], None]) -> Callable[[Any], None]:
    """Coalesce one widget's ``<Configure>`` events into per-frame layout calls.

    Rapid window resizes (a drag) fire many ``<Configure>`` events; this
    helper runs ``handler(widget)`` at most once per idle cycle so dependent
    layout (e.g. re-wrapping labels to the new width) never thrashes. Layout
    errors raised after the widget is destroyed are swallowed. Returns the
    bound ``<Configure>`` handler for tests or unbinding.
    """

    scheduled: dict[str, Any] = {"id": None}

    def invoke() -> None:
        scheduled["id"] = None
        try:
            handler(widget)
        except tk.TclError:
            pass

    def on_configure(_event: Any = None) -> None:
        if scheduled["id"] is None:
            try:
                scheduled["id"] = widget.after_idle(invoke)
            except tk.TclError:
                pass

    widget.bind("<Configure>", on_configure)
    return on_configure


def fit_wrap_to_width(
    label: Any,
    max_wrap: int,
    *,
    margin: int = 8,
    floor: int = 240,
) -> Callable[[Any], None]:
    """Return a resize handler that re-fits one label's wrap to its parent width.

    The wrap never exceeds ``max_wrap`` (so default appearance is unchanged
    at normal sizes) but narrows to the container width when the window is
    resized smaller, keeping long descriptions readable and unclipped.
    """

    def handler(widget: Any) -> None:
        width = widget.winfo_width()
        label.configure(wraplength=min(max_wrap, max(floor, width - margin)))

    return handler


def next_wrap_width(
    width: int,
    last: int,
    *,
    margin: int = 36,
    hysteresis: int = 12,
    min_width: int = 40,
) -> int | None:
    """Return the next content wrap width, or None when nothing should change.

    Centralises the no-clip + no-churn resize rule shared by adaptive
    widgets (cards whose headline/subtitle wrap to the widget width):

    - Content always fits: the wrap is exactly ``width - margin``, so
      shrinking never clips horizontally.
    - Small growths are deferred until the width moves by ``hysteresis``, so
      a slow resize does not reflow the surrounding layout on every pixel.
    - Unmeasured or too-narrow widgets (``width <= min_width``) are skipped.
    """

    if width <= min_width:
        return None
    wrap = width - margin
    if wrap == last:
        return None
    if wrap > last and wrap - last < hysteresis:
        return None
    return wrap


def metric_value_wrap(
    wrap: int,
    *,
    label_space: int = 130,
    floor: int = 60,
) -> int:
    """Return the wrap width for a card's metric values, or 0 when unsized.

    Metric values sit beside a left-hand label, so they reserve
    ``label_space`` pixels for it and never wrap narrower than ``floor``.
    A wrap of 0 (card not measured yet) keeps values unwrapped.
    """

    if not wrap:
        return 0
    return max(wrap - label_space, floor)


def scrollable_area(
    parent: Any,
    *,
    bg: str,
    frame_cls: Callable[..., Any],
    canvas_cls: Callable[..., Any],
    scrollbar_cls: Callable[..., Any],
    frame_kwargs: dict[str, Any],
    auto_hide: bool = False,
) -> tuple[Any, Any, Callable[[], None]]:
    """Build one vertically scrollable content area.

    Returns ``(canvas, inner, refresh_scrollbar)``. The inner frame is
    embedded in a canvas and follows its width; the vertical scrollbar is
    packed alongside (with a ``SCROLLBAR_GUTTER`` gap so it never touches the
    content text) by default. With ``auto_hide`` the scrollbar is shown only
    while the content height exceeds the visible body height, which keeps
    small detail dialogs (e.g. a no-battery view) free of a useless internal
    scrollbar. ``refresh_scrollbar`` recomputes that visibility.
    """

    canvas = canvas_cls(parent, bg=bg, highlightthickness=0)
    scrollbar = scrollbar_cls(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    inner = frame_cls(canvas, **frame_kwargs)
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def update_scrollregion(_event: Any = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def resize_inner_width(_event: Any = None) -> None:
        width = canvas.winfo_width()
        if width > 1:
            canvas.itemconfigure(window_id, width=width)

    def refresh_scrollbar(_event: Any = None) -> None:
        if not auto_hide:
            return
        try:
            content_height = inner.winfo_reqheight()
            view_height = canvas.winfo_height()
        except (AttributeError, tk.TclError):
            return
        if view_height <= 1:
            return
        if content_height > view_height:
            if not scrollbar.winfo_ismapped():
                scrollbar.pack(
                    side="right",
                    fill="y",
                    padx=(SCROLLBAR_GUTTER, 0),
                )
        elif scrollbar.winfo_ismapped():
            scrollbar.pack_forget()

    def on_inner_configure(_event: Any = None) -> None:
        update_scrollregion()
        if auto_hide:
            refresh_scrollbar()

    def on_canvas_configure(_event: Any = None) -> None:
        resize_inner_width()
        if auto_hide:
            refresh_scrollbar()

    inner.bind("<Configure>", on_inner_configure)
    canvas.bind("<Configure>", on_canvas_configure)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(
        side="right",
        fill="y",
        padx=(SCROLLBAR_GUTTER, 0),
    )
    return canvas, inner, refresh_scrollbar


def metric_row(
    parent: Any,
    label_text: str,
    value_text: str,
    *,
    frame_cls: Callable[..., Any],
    label_cls: Callable[..., Any],
    bg: str,
    label_fg: str,
    value_fg: str,
    font: Font,
    value_font: Font | None = None,
    wraplength: int | None = None,
    pady: tuple[int, int] | int = 1,
    cursor: str | None = None,
    justify: str | None = None,
) -> tuple[Any, Any, Any]:
    """Build one labelled metric row: label on the left, value on the right.

    Used by overview cards and detail-dialog section rows so the same
    visual pattern has one implementation. Returns ``(row, label, value)``
    so callers can add click bindings or keep references for later updates.
    ``justify`` defaults to Tk's native behaviour and is only set when a
    caller explicitly needs it (e.g. wrapping detail values).
    """

    row = frame_cls(parent, bg=bg)
    row.pack(fill="x", pady=pady)
    label = label_cls(
        row,
        text=label_text,
        bg=bg,
        fg=label_fg,
        font=font,
        anchor="w",
    )
    label.pack(side="left")
    value_kwargs: dict[str, Any] = {
        "text": value_text,
        "bg": bg,
        "fg": value_fg,
        "font": value_font or font,
        "anchor": "e",
    }
    if wraplength is not None:
        value_kwargs["wraplength"] = wraplength
    if justify is not None:
        value_kwargs["justify"] = justify
    if cursor is not None:
        label.config(cursor=cursor)
        value_kwargs["cursor"] = cursor
    value = label_cls(row, **value_kwargs)
    value.pack(side="right")
    return row, label, value


def dialog_shell(
    toplevel: Any,
    *,
    master: Any,
    title: str,
    geometry: str,
    minsize: tuple[int, int],
    colors: dict[str, str],
    padx: int,
    pady: int,
    frame_cls: Callable[..., Any],
    on_close: Callable[[], None] | None = None,
) -> Any:
    """Configure one secondary dialog window and return its content container.

    Handles the shared title/geometry/min-size/background/transient dance
    and the (optional) window-manager close hook. The container frame uses
    the caller's ``frame_cls`` so patched widget factories keep working.
    """

    toplevel.title(title)
    toplevel.geometry(geometry)
    toplevel.minsize(*minsize)
    toplevel.configure(bg=colors["background"])
    toplevel.transient(master)
    if on_close is not None:
        toplevel.protocol("WM_DELETE_WINDOW", on_close)
    container = frame_cls(
        toplevel,
        bg=colors["background"],
        padx=padx,
        pady=pady,
    )
    container.pack(fill="both", expand=True)
    return container


def dialog_heading(
    container: Any,
    text: str,
    description: str,
    *,
    label_cls: Callable[..., Any],
    colors: dict[str, str],
    heading_font: Font,
    description_font: Font = ("Helvetica", 10),
    wrap: int,
    description_pady: tuple[int, int] = (4, 14),
) -> Any:
    """Render one dialog heading block (title + explanatory description).

    Returns the description label so callers can re-fit its wrap to the
    container width on resize with ``resize_aware``.
    """

    label_cls(
        container,
        text=text,
        bg=colors["background"],
        fg=colors["text"],
        font=heading_font,
    ).pack(anchor="w")
    description_label = label_cls(
        container,
        text=description,
        bg=colors["background"],
        fg=colors["secondary"],
        font=description_font,
        wraplength=wrap,
        justify="left",
    )
    description_label.pack(anchor="w", pady=description_pady)
    return description_label


def dialog_footer(
    container: Any,
    *,
    frame_cls: Callable[..., Any],
    label_cls: Callable[..., Any],
    colors: dict[str, str],
    status_text: str,
    pady: tuple[int, int] = (14, 0),
) -> tuple[Any, Any]:
    """Build one left-status / right-actions footer bar.

    Returns ``(footer, status_label)``; callers add their action buttons on
    the right with ``pack_action_buttons``. The status label keeps a
    ``FOOTER_GUTTER`` gap on its right so action buttons never touch the
    status text.
    """

    footer = frame_cls(container, bg=colors["background"])
    footer.pack(fill="x", pady=pady)
    status = label_cls(
        footer,
        text=status_text,
        bg=colors["background"],
        fg=colors["secondary"],
        font=("Helvetica", 10),
    )
    status.pack(side="left", padx=(0, FOOTER_GUTTER))
    return footer, status


def dashboard_header(
    parent: Any,
    *,
    title: str,
    description: str,
    frame_cls: Callable[..., Any],
    label_cls: Callable[..., Any],
    wrap: int = 680,
    node_title: str | None = None,
) -> Any:
    """Render the dashboard header block and return the actions frame.

    Composes the application title (plus an optional uppercase node label for
    future multi-node screens), the description line, and a right-aligned
    actions area that callers fill with buttons and status. With no
    ``node_title`` the header is exactly the single-node header used today.
    """

    header_frame = frame_cls(parent, style="App.TFrame")
    header_frame.pack(fill="x")

    heading_frame = frame_cls(header_frame, style="App.TFrame")
    heading_frame.pack(side="left", fill="x", expand=True)

    label_cls(
        heading_frame,
        text=title,
        style="Title.TLabel",
    ).pack(anchor="w")
    node_label = None
    if node_title:
        node_label = label_cls(
            heading_frame,
            text=node_title.upper(),
            style="Node.TLabel",
        )
        node_label.pack(anchor="w", pady=(2, 0))
    label_cls(
        heading_frame,
        text=description,
        wraplength=wrap,
        style="Description.TLabel",
    ).pack(anchor="w", pady=(6, 0))
    discovery_label = label_cls(
        heading_frame,
        text="",
        style="Description.TLabel",
    )

    actions = frame_cls(header_frame, style="App.TFrame")
    actions.pack(side="right", padx=(20, 0))
    # Preserve the existing return contract while exposing the optional node
    # and discovery labels for the dashboard controller to update.
    actions._dashboard_node_label = node_label
    actions._dashboard_discovery_label = discovery_label
    return actions


def page_shell(
    parent: Any,
    *,
    title: str,
    description: str,
    back_text: str,
    on_back: Callable[[], None],
    style_frame_cls: Callable[..., Any],
    style_label_cls: Callable[..., Any],
    button_cls: Callable[..., Any],
    canvas_cls: Callable[..., Any],
    scrollbar_cls: Callable[..., Any],
    colors: dict[str, str],
) -> tuple[Any, Any, Any, Callable[[], None]]:
    """Build the standard sub-page shell: header, back button, scroll body.

    Returns ``(back_button, canvas, content, refresh_scrollbar)`` so pages
    attach their sections to ``content`` and store the rest as attributes.
    Shared by the Settings hub and the Preferences page so the page scaffold
    (header at a 620px wrap, right-aligned back button, ``App.TFrame`` body
    with a left-aligned scrollable content column) exists in exactly one
    place.
    """

    header_actions = dashboard_header(
        parent,
        title=title,
        description=description,
        frame_cls=style_frame_cls,
        label_cls=style_label_cls,
        wrap=620,
    )
    back_button = button_cls(
        header_actions,
        text=back_text,
        command=on_back,
        style="Neutral.TButton",
    )
    back_button.pack(anchor="e")

    body = style_frame_cls(parent, style="App.TFrame")
    body.pack(fill="both", expand=True, pady=(14, 0))

    content_side = style_frame_cls(body, style="App.TFrame")
    content_side.pack(side="left", fill="both", expand=True)

    canvas, content, refresh_scrollbar = scrollable_area(
        content_side,
        bg=colors["background"],
        frame_cls=style_frame_cls,
        canvas_cls=canvas_cls,
        scrollbar_cls=scrollbar_cls,
        frame_kwargs={"style": "App.TFrame"},
        auto_hide=True,
    )
    return back_button, canvas, content, refresh_scrollbar


def section_card(
    parent: Any,
    title: str,
    *,
    frame_cls: Callable[..., Any],
    label_cls: Callable[..., Any],
    colors: dict[str, str],
    fonts: dict[str, Any],
    description: str | None = None,
) -> tuple[Any, Any]:
    """Build one passive white settings section card.

    Returns ``(card, body)``; ``body`` is the container callers fill with
    ``setting_row`` controls. The card is deliberately passive (no hover, no
    click binding, no cursor), reusing only the shared white-card and border
    treatment so settings feel like part of the same application.
    """

    card = frame_cls(
        parent,
        bg=colors["card"],
        highlightthickness=1,
        highlightbackground=colors["border"],
        highlightcolor=colors["border"],
    )
    card.pack(fill="x", pady=(0, 14))
    label_cls(
        card,
        text=title,
        bg=colors["card"],
        fg=colors["text"],
        font=fonts["section"],
    ).pack(anchor="w")
    if description is not None:
        label_cls(
            card,
            text=description,
            bg=colors["card"],
            fg=colors["secondary"],
            font=fonts["body"],
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))
    body = frame_cls(card, bg=colors["card"])
    body.pack(fill="x", pady=(10, 0))
    return card, body


def setting_row(
    parent: Any,
    label_text: str,
    control_factory: Callable[[Any], Any],
    *,
    frame_cls: Callable[..., Any],
    label_cls: Callable[..., Any],
    colors: dict[str, str],
    fonts: dict[str, Any],
    help_text: str | None = None,
    label_wrap: int = 260,
) -> tuple[Any, Any, Any]:
    """Build one labelled settings row with a right-hand control slot.

    Returns ``(row, label, control)``. The label sits on the left and can
    wrap independently of the control; ``help_text`` renders beneath it in
    muted secondary styling. The field and its unit remain attached to the
    control on the right.
    """

    row = frame_cls(parent, bg=colors["card"])
    row.pack(fill="x", pady=(0, 10))
    label = label_cls(
        row,
        text=label_text,
        bg=colors["card"],
        fg=colors["text"],
        font=fonts["body"],
        anchor="w",
        wraplength=label_wrap,
        justify="left",
    )
    label.pack(side="left", fill="x", expand=True)
    control = control_factory(row)
    control.pack(side="right", padx=(12, 0))
    if help_text is not None:
        help_label = label_cls(
            row,
            text=help_text,
            bg=colors["card"],
            fg=colors["secondary"],
            font=fonts["body"],
            anchor="w",
            wraplength=label_wrap,
            justify="left",
        )
        help_label.pack(anchor="w", pady=(2, 0))
    return row, label, control


def pack_action_buttons(
    footer: Any,
    buttons: Sequence[
        tuple[str, Callable[[], None], str | None, tuple[int, int] | None]
    ],
    *,
    button_cls: Callable[..., Any],
) -> list[Any]:
    """Pack right-aligned footer action buttons and return them in order.

    Buttons are packed with ``side="right"`` in the order given, so the
    first entry sits at the far right (Tk pack semantics). Each entry is
    ``(text, command, style, padx)`` where ``style``/``padx`` may be None.
    """

    created: list[Any] = []
    for text, command, style, padx in buttons:
        options: dict[str, Any] = {"text": text, "command": command}
        if style is not None:
            options["style"] = style
        button = button_cls(footer, **options)
        pack_options: dict[str, Any] = {"side": "right"}
        if padx is not None:
            pack_options["padx"] = padx
        button.pack(**pack_options)
        created.append(button)
    return created
