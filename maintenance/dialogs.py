import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from maintenance.actions import FileManager, ProcessManager
from maintenance.components import (
    DOWNLOADS_SCAN_CANCELLED,
    BackgroundTaskRunner,
    ProgressTask,
)
from maintenance.components.coordinator import AppCoordinator
from maintenance.components.scan_support import (
    SCAN_CANCELLED_NOTICE,
    call_legacy_compatible,
)
from maintenance.models import (
    FileActionResult,
    FileCandidate,
    ProcessActionResult,
    ProcessCandidate,
    ResourceSummary,
)
from maintenance.scanner import ProgressCallback, SystemScanner
from maintenance.ui import layout as ui_layout
from maintenance.ui import styles as ui_styles


def _invoke_delivered(callback: Callable[[], None]) -> None:
    try:
        callback()
    except (RuntimeError, tk.TclError):
        pass


def _standalone_coordinator(widget: tk.Misc) -> AppCoordinator:
    """Build a dialog-local coordinator that delivers via ``widget.after``.

    Dialogs opened through ``AppWindow`` share the window's coordinator (one
    delivery path for the whole app); standalone constructions fall back to
    the same per-widget delivery seam the legacy runner used, so the Tkinter
    thread-safety contract holds either way.
    """

    def deliver(callback: Callable[[], None]) -> None:
        try:
            widget.after(0, lambda: _invoke_delivered(callback))
        except (RuntimeError, tk.TclError):
            pass

    return AppCoordinator(deliver=deliver)


def run_in_thread(
    widget: tk.Misc,
    task: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[str], None] | None = None,
    *,
    progress_task: ProgressTask | None = None,
    cancel_event: threading.Event | None = None,
    on_progress: ProgressCallback | None = None,
) -> None:
    """Run work off the Tkinter thread and safely deliver the result."""

    BackgroundTaskRunner.run(
        widget,
        task,
        on_success,
        on_error,
        progress_task=progress_task,
        cancel_event=cancel_event,
        on_progress=on_progress,
    )


def process_sort_key(column: str, process: ProcessCandidate) -> Any:
    """Return the comparable sort key for one process-table column."""

    if column == "name":
        return process.name.casefold()
    if column == "pid":
        return process.pid
    if column == "memory":
        return process.memory_bytes
    if column == "cpu":
        return process.cpu_percent
    if column == "activity":
        return 0 if process.activity == "Active" else 1
    if column == "permission":
        return 0 if process.action_allowed else 1
    return 0


def process_row_tags(process: ProcessCandidate) -> tuple[str, ...]:
    """Return the row tags for one process (protected / low activity)."""

    if not process.action_allowed:
        return ("protected",)
    if process.activity == "Low activity":
        return ("low",)
    return ()


def process_matches_query(process: ProcessCandidate, query: str) -> bool:
    """Return whether a process matches the case-insensitive name filter."""

    normalized = query.casefold().strip()
    return not normalized or normalized in process.name.casefold()


def rebuild_tree_rows(
    tree: Any,
    rows: list[tuple[str, tuple[object, ...], tuple[str, ...]]],
) -> None:
    """Replace every row of a Treeview with the given (iid, values, tags)."""

    tree.delete(*tree.get_children())
    for iid, values, tags in rows:
        tree.insert("", tk.END, iid=iid, values=values, tags=tags)


def action_label_text(actionable: bool) -> str:
    """Return the card action label for one summary's actionable flag."""

    return "Review and clean  →" if actionable else "View details  →"


def metric_label_pairs(
    details: tuple[str, ...],
    value: str,
) -> tuple[tuple[str, str], ...]:
    """Return ``(label, value)`` pairs for one summary's detail lines.

    The headline value is not repeated as a row; lines without a ``": "``
    separator keep an empty label.
    """

    pairs: list[tuple[str, str]] = []
    for line in details:
        if line == value:
            continue
        label, separator, line_value = line.partition(": ")
        if separator:
            pairs.append((label, line_value))
        else:
            pairs.append(("", line))
    return tuple(pairs)


_INFO_SECTION_RULES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "gpu": (
        ("Hardware", ()),
        ("Status", ("Temperature", "GPU usage", "Memory", "Driver", "Metal")),
    ),
    "network": (
        (
            "Traffic",
            ("Download rate", "Upload rate", "Received this boot", "Sent this boot"),
        ),
        ("Interface", ("Active interface", "VPN")),
    ),
    "battery": (("Battery", ("Charge", "Power", "Time remaining")),),
}


def detail_sections(
    key: str,
    details: tuple[str, ...],
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    """Group one summary's detail lines into titled dialog sections.

    Lines whose label matches a section's pinned prefixes land in that
    section; unprefixed lines (full hardware identifiers, guidance text)
    land in the first declared section; anything else lands in a trailing
    "Details" section. Unknown keys get one "Details" section only.
    """

    rules = _INFO_SECTION_RULES.get(key, ())
    buckets: list[list[tuple[str, str]]] = [[] for _ in range(len(rules) + 1)]
    for line in details:
        prefix, separator, value = line.partition(": ")
        if not separator:
            buckets[0 if rules else -1].append(("", line))
            continue
        for index, (_title, prefixes) in enumerate(rules):
            if prefix in prefixes:
                buckets[index].append((prefix, value))
                break
        else:
            buckets[-1].append((prefix, value))

    sections: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for (title, _prefixes), rows in zip(rules, buckets):
        if rows:
            sections.append((title, tuple(rows)))
    if buckets[-1]:
        sections.append(("Details", tuple(buckets[-1])))
    return tuple(sections)


def show_action_result(
    widget: tk.Misc,
    title: str,
    summary: str,
    errors: tuple[str, ...] | list[str],
) -> None:
    """Show one cleanup-action result dialog, appending the first errors."""

    message = summary
    if errors:
        message += "\n\n" + "\n".join(errors[:6])
    messagebox.showinfo(title, message, parent=widget)


def close_coordinated_dialog(
    dialog: Any,
    *,
    key: str,
    unsubscribe_callback: Callable[[str, Any | None], None],
    active: bool,
) -> None:
    """Close one dialog that shares a coordinator scanning key.

    Shared by the process and storage dialogs: unsubscribes a waiting
    callback, cancels the shared run when the dialog owns an active one, and
    destroys the window. ``active`` is the dialog's own in-flight flag.
    """

    if dialog._waiting_for_shared:
        dialog.coordinator.unsubscribe(key, unsubscribe_callback)
    if active:
        dialog.coordinator.cancel(key)
    dialog.destroy()


class ResourceCard(tk.Frame):
    """Clickable summary card for one system resource."""

    WRAP_HYSTERESIS = 12
    METRIC_LABEL_SPACE = 130

    def __init__(
        self,
        master: tk.Misc,
        key: str,
        title: str,
        on_open: Callable[[str], None],
        colors: dict[str, str],
    ) -> None:
        super().__init__(
            master,
            bg=colors["card"],
            highlightbackground=colors["border"],
            highlightthickness=1,
            cursor="hand2",
            padx=18,
            pady=16,
        )
        self.key = key
        self.on_open = on_open
        self.colors = colors

        self.title_label = tk.Label(
            self,
            text=title.upper(),
            bg=colors["card"],
            fg=colors["secondary"],
            font=("Helvetica", 10, "bold"),
            cursor="hand2",
        )
        self.title_label.pack(anchor=tk.W)

        self.value_label = tk.Label(
            self,
            text="—",
            bg=colors["card"],
            fg=colors["text"],
            font=("Helvetica", 22, "bold"),
            cursor="hand2",
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=300,
        )
        self.value_label.pack(anchor=tk.W, pady=(10, 2))

        self.subtitle_label = tk.Label(
            self,
            text="Run a scan to load details",
            bg=colors["card"],
            fg=colors["secondary"],
            font=("Helvetica", 10),
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=300,
            cursor="hand2",
        )
        self.subtitle_label.pack(anchor=tk.W)

        self.metrics_frame = tk.Frame(self, bg=colors["card"])
        self.metrics_frame.pack(fill=tk.X, pady=(8, 0))
        self.metric_rows: list[tuple[tk.Frame, tk.Label, tk.Label]] = []

        self.progress = ttk.Progressbar(
            self,
            maximum=100,
            value=0,
            style="Card.Horizontal.TProgressbar",
        )
        self.progress.pack(fill=tk.X, pady=(14, 12))

        self.details_label = tk.Label(
            self,
            text="View details  →",
            bg=colors["card"],
            fg=colors["accent"],
            font=("Helvetica", 10, "bold"),
            cursor="hand2",
        )
        self.details_label.pack(anchor=tk.W)

        self._last_card_wrap = 0
        ui_layout.resize_aware(self, self._rewrap)
        for child in (self, *self.winfo_children()):
            self._bind_affordance(child)

    def _rewrap(self, _widget: Any = None) -> None:
        """Re-fit headline, subtitle and metric wraps to the current card width.

        Runs (coalesced) on every card resize so long values wrap within the
        card instead of clipping, keeping every card consistent at any window
        size. The no-clip + hysteresis rule lives in the shared UI layout
        primitive ``next_wrap_width``; metric values reserve ``METRIC_LABEL_SPACE``
        for their left-hand label.
        """

        wrap = ui_layout.next_wrap_width(
            self.winfo_width(),
            getattr(self, "_last_card_wrap", 0),
            hysteresis=self.WRAP_HYSTERESIS,
        )
        if wrap is None:
            return
        self._last_card_wrap = wrap
        self.value_label.config(wraplength=wrap)
        self.subtitle_label.config(wraplength=wrap)
        metric_wrap = self._metric_wrap()
        for _row, _name_label, value_label in getattr(self, "metric_rows", []):
            value_label.config(wraplength=metric_wrap)

    def _metric_wrap(self) -> int:
        """Return the current metric-value wrap, or 0 before the card is sized."""

        return ui_layout.metric_value_wrap(
            getattr(self, "_last_card_wrap", 0),
            label_space=self.METRIC_LABEL_SPACE,
        )

    def _bind_affordance(self, widget: Any) -> None:
        """Wire one card widget to open on click and highlight on hover."""

        widget.bind("<Button-1>", self._open)
        widget.bind("<Enter>", self._set_hover)
        widget.bind("<Leave>", self._clear_hover)

    def _set_hover(self, _event: tk.Event | None = None) -> None:
        self.configure(highlightbackground=self.colors["accent"])

    def _clear_hover(self, _event: tk.Event | None = None) -> None:
        self.configure(highlightbackground=self.colors["border"])

    def _open(self, _event: tk.Event | None = None) -> None:
        self.on_open(self.key)

    def update_summary(self, summary: ResourceSummary) -> None:
        self.value_label.config(text=summary.value)
        self.subtitle_label.config(text=summary.subtitle)
        self.progress.config(value=summary.percent or 0)
        self.details_label.config(text=action_label_text(summary.actionable))
        self._render_metrics(summary)

    def _render_metrics(self, summary: ResourceSummary) -> None:
        """Update one labelled secondary value per detail line in place.

        Existing rows are reused (text updated in place) so a refresh never
        destroys and rebuilds widgets; rows are only added or removed when the
        set of metrics actually changes. The headline value is not repeated as
        a row, and every row keeps a label so the user always knows what the
        number represents.
        """

        lines = metric_label_pairs(summary.details, summary.value)

        for index, (label_text, value_text) in enumerate(lines):
            if index < len(self.metric_rows):
                row, name_label, value_label = self.metric_rows[index]
                name_label.config(text=label_text)
                value_label.config(text=value_text)
                continue

            row, name_label, value_label = ui_layout.metric_row(
                self.metrics_frame,
                label_text,
                value_text,
                frame_cls=tk.Frame,
                label_cls=tk.Label,
                bg=self.colors["card"],
                label_fg=self.colors["secondary"],
                value_fg=self.colors["text"],
                font=ui_styles.FONTS["card_metric"],
                pady=(1, 0),
                cursor="hand2",
                justify="right",
            )
            metric_wrap = self._metric_wrap()
            if metric_wrap:
                value_label.config(wraplength=metric_wrap)
            for child in (row, name_label, value_label):
                self._bind_affordance(child)
            self.metric_rows.append((row, name_label, value_label))

        for row, _name_label, _value_label in self.metric_rows[len(lines) :]:
            row.destroy()
        del self.metric_rows[len(lines) :]


class InfoDialog(tk.Toplevel):
    """Structured details view for one resource summary.

    The headline value and sectioned detail lines present the information
    the overview card already collected in a readable layout. The content
    scrolls and the Close button sits outside the scroll region, so it
    stays visible however many lines a summary has.
    """

    DETAIL_WRAPLENGTH = 430
    GEOMETRY = "560x360"
    MIN_SIZE = (500, 320)

    def __init__(
        self,
        master: tk.Misc,
        summary: ResourceSummary,
        colors: dict[str, str],
    ) -> None:
        super().__init__(master)
        container = ui_layout.dialog_shell(
            self,
            master=master,
            title=f"{summary.title} Details",
            geometry=self.GEOMETRY,
            minsize=self.MIN_SIZE,
            colors=colors,
            padx=28,
            pady=24,
            frame_cls=tk.Frame,
        )

        footer = tk.Frame(container, bg=colors["background"])
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        ui_layout.pack_action_buttons(
            footer,
            [
                (
                    "Close",
                    self.destroy,
                    ui_styles.STYLE_NEUTRAL_BUTTON,
                    None,
                ),
            ],
            button_cls=ttk.Button,
        )

        tk.Label(
            container,
            text=summary.title,
            bg=colors["background"],
            fg=colors["text"],
            font=ui_styles.FONTS["info_heading"],
        ).pack(anchor=tk.W)
        tk.Label(
            container,
            text=summary.subtitle,
            bg=colors["background"],
            fg=colors["secondary"],
            font=ui_styles.FONTS["info_subtitle"],
            wraplength=self.DETAIL_WRAPLENGTH,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 14))

        if summary.value:
            tk.Label(
                container,
                text=summary.value,
                bg=colors["background"],
                fg=colors["text"],
                font=ui_styles.FONTS["info_headline"],
                anchor=tk.W,
            ).pack(anchor=tk.W, pady=(0, 12))

        body = tk.Frame(container, bg=colors["background"])
        body.pack(fill=tk.BOTH, expand=True)

        _canvas, inner, _refresh_scrollbar = ui_layout.scrollable_area(
            body,
            bg=colors["background"],
            frame_cls=tk.Frame,
            canvas_cls=tk.Canvas,
            scrollbar_cls=ttk.Scrollbar,
            frame_kwargs={"bg": colors["background"]},
            auto_hide=True,
        )

        sections = detail_sections(summary.key, summary.details)
        if not sections:
            tk.Label(
                inner,
                text="No further details available.",
                bg=colors["card"],
                fg=colors["secondary"],
                font=ui_styles.FONTS["empty_detail"],
                anchor=tk.W,
            ).pack(anchor=tk.W, pady=4)
            return

        for section_title, rows in sections:
            tk.Label(
                inner,
                text=section_title,
                bg=colors["card"],
                fg=colors["secondary"],
                font=ui_styles.FONTS["detail_section"],
                anchor=tk.W,
            ).pack(anchor=tk.W, pady=(10, 2))
            for label, line_value in rows:
                ui_layout.metric_row(
                    inner,
                    label,
                    line_value,
                    frame_cls=tk.Frame,
                    label_cls=tk.Label,
                    bg=colors["card"],
                    label_fg=colors["secondary"],
                    value_fg=colors["text"],
                    font=ui_styles.FONTS["detail_row"],
                    wraplength=self.DETAIL_WRAPLENGTH,
                    justify="left",
                )


class ProcessDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        analyzer: Any,
        manager: ProcessManager,
        resource_key: str,
        colors: dict[str, str],
        on_changed: Callable[[], None],
        coordinator: AppCoordinator | None = None,
    ) -> None:
        super().__init__(master)
        self.analyzer = analyzer
        self.manager = manager
        self.resource_key = resource_key
        self.colors = colors
        self.on_changed = on_changed
        self.coordinator = coordinator or _standalone_coordinator(self)
        self.processes: dict[int, ProcessCandidate] = {}
        self._displayed: list[ProcessCandidate] = []
        self._sort_column = "memory" if resource_key == "memory" else "cpu"
        self._sort_reverse = True
        self.normal_quit_result: ProcessActionResult | None = None
        self._refresh_active = False
        self._waiting_for_shared = False

        title = "Memory Processes" if resource_key == "memory" else "CPU Processes"
        container = ui_layout.dialog_shell(
            self,
            master=master,
            title=title,
            geometry="900x560",
            minsize=(760, 480),
            colors=colors,
            padx=24,
            pady=22,
            frame_cls=tk.Frame,
            on_close=self._close,
        )
        description_label = ui_layout.dialog_heading(
            container,
            title,
            (
                "Select user processes to request a normal quit. "
                "Protected processes cannot be selected for cleanup."
            ),
            label_cls=tk.Label,
            colors=colors,
            heading_font=ui_styles.FONTS["dialog_heading"],
            wrap=800,
        )
        ui_layout.resize_aware(
            container,
            ui_layout.fit_wrap_to_width(description_label, 800),
        )

        search_frame = tk.Frame(container, bg=colors["background"])
        search_frame.pack(fill=tk.X, pady=(0, 10))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_changed)
        self.search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            bg=colors["card"],
            fg=colors["text"],
            insertbackground=colors["text"],
            relief=tk.FLAT,
            highlightbackground=colors["border"],
            highlightthickness=1,
            font=("Helvetica", 10),
        )
        self.search_entry.pack(fill=tk.X, expand=True)

        tree_frame = tk.Frame(container, bg=colors["card"])
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "pid", "memory", "cpu", "activity", "permission")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        headings = {
            "name": "Application / Process",
            "pid": "PID",
            "memory": "Memory",
            "cpu": "CPU",
            "activity": "Activity",
            "permission": "Action",
        }
        widths = {
            "name": 250,
            "pid": 70,
            "memory": 110,
            "cpu": 80,
            "activity": 110,
            "permission": 100,
        }

        def heading_command(column_name: str) -> Callable[[], None]:
            return lambda: self._sort_by(column_name)

        for column in columns:
            self.tree.heading(
                column,
                text=headings[column],
                command=heading_command(column),
            )
            self.tree.column(column, width=widths[column], anchor=tk.W)

        scrollbar = ttk.Scrollbar(tree_frame, command=self.tree.yview)
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(
            side=tk.RIGHT,
            fill=tk.Y,
            padx=(ui_layout.SCROLLBAR_GUTTER, 0),
        )
        self.tree.tag_configure("protected", foreground="#98A2B3")
        self.tree.tag_configure("low", foreground="#B45309")

        footer, self.status_label = ui_layout.dialog_footer(
            container,
            frame_cls=tk.Frame,
            label_cls=tk.Label,
            colors=colors,
            status_text="Loading processes...",
        )
        self.refresh_button, self.quit_button = ui_layout.pack_action_buttons(
            footer,
            [
                ("Refresh", self.refresh, ui_styles.STYLE_NEUTRAL_BUTTON, (8, 0)),
                ("Quit Selected", self.quit_selected, "Danger.TButton", None),
            ],
            button_cls=ttk.Button,
        )

        cached = self.coordinator.last_result("process")
        if cached is not None:
            self._show_processes(cached)
        self.refresh()

    def refresh(self) -> None:
        if self._refresh_active:
            return

        def process_task(
            cancel_event: threading.Event,
            _progress: Callable[[str], None],
        ) -> list[ProcessCandidate]:
            return call_legacy_compatible(
                lambda: self.analyzer.process_candidates(
                    cancel_event=cancel_event,
                ),
                lambda: self.analyzer.process_candidates(),
            )

        generation = self.coordinator.run(
            "process",
            process_task,
            on_result=lambda _key, processes: self._on_refresh_result(processes),
            on_error=lambda _key, message: self._on_refresh_error(message),
        )
        if generation is None:
            self._wait_for_shared_scan()
            return

        self._refresh_active = True
        self.quit_button.config(state=tk.DISABLED)
        self.refresh_button.config(state=tk.DISABLED)
        self.status_label.config(text="Analyzing processes...")

    def _on_refresh_result(self, processes: list[ProcessCandidate]) -> None:
        self._finish_refresh()
        self._show_processes(processes)

    def _on_refresh_error(self, message: str) -> None:
        self._finish_refresh()
        self._show_error(message)

    def _wait_for_shared_scan(self) -> None:
        if self._waiting_for_shared:
            return
        self._waiting_for_shared = True
        self.status_label.config(text="Waiting for the active process scan...")
        self.coordinator.subscribe("process", self._on_shared_process_result)

    def _on_shared_process_result(
        self,
        _key: str,
        result: Any | None,
    ) -> None:
        self._waiting_for_shared = False
        if result is None:
            self.refresh()
            return
        self._show_processes(result)
        self.refresh_button.config(state=tk.NORMAL)

    def _finish_refresh(self) -> None:
        self._refresh_active = False

    def _show_processes(self, processes: list[ProcessCandidate]) -> None:
        self.processes = {process.pid: process for process in processes}
        self._apply_filter(self.search_var.get())

    def _on_search_changed(self, *_args: object) -> None:
        self._apply_filter(self.search_var.get())

    def _apply_filter(self, query: str) -> None:
        self._display_query = query.strip()
        self._displayed = [
            process
            for process in self.processes.values()
            if process_matches_query(process, query)
        ]
        self._sort_displayed()
        self._render_rows()

    def _sort_by(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = column not in ("name", "activity", "permission")
        self._sort_displayed()
        self._render_rows()

    def _sort_displayed(self) -> None:
        self._displayed.sort(
            key=lambda item: process_sort_key(self._sort_column, item),
            reverse=self._sort_reverse,
        )

    def _render_rows(self) -> None:
        rows: list[tuple[str, tuple[object, ...], tuple[str, ...]]] = [
            (
                str(process.pid),
                (
                    process.name,
                    process.pid,
                    SystemScanner.format_bytes(process.memory_bytes),
                    f"{process.cpu_percent:.1f}%",
                    process.activity,
                    "Can quit" if process.action_allowed else "Protected",
                ),
                process_row_tags(process),
            )
            for process in self._displayed
        ]
        rebuild_tree_rows(self.tree, rows)

        if not self.processes:
            self.status_label.config(text="No processes available for cleanup review.")
            self.quit_button.config(state=tk.DISABLED)
            self.refresh_button.config(state=tk.NORMAL)
            return

        allowed_count = sum(item.action_allowed for item in self._displayed)
        if not self._displayed:
            query = getattr(self, "_display_query", "")
            if query:
                self.status_label.config(
                    text=f'No processes match "{query}"',
                )
            else:
                self.status_label.config(
                    text="No processes available for cleanup review.",
                )
            self.quit_button.config(state=tk.DISABLED)
        else:
            self.status_label.config(
                text=f"{len(self._displayed)} shown • {allowed_count} available for review"
            )
            self.quit_button.config(
                state=tk.NORMAL if allowed_count > 0 else tk.DISABLED
            )
        self.refresh_button.config(state=tk.NORMAL)

    def quit_selected(self) -> None:
        selected = [int(item) for item in self.tree.selection()]
        allowed = [
            pid
            for pid in selected
            if self.processes.get(pid) and self.processes[pid].action_allowed
        ]
        if not allowed:
            messagebox.showinfo(
                "Nothing Selected",
                "Select one or more processes marked “Can quit”.",
                parent=self,
            )
            return

        names = ", ".join(self.processes[pid].name for pid in allowed[:5])
        if len(allowed) > 5:
            names += f" and {len(allowed) - 5} more"
        confirmed = messagebox.askyesno(
            "Quit Selected Processes?",
            f"Request a normal quit for: {names}?\n\n"
            "Unsaved work in these applications could be lost.",
            parent=self,
        )
        if not confirmed:
            return

        self.quit_button.config(state=tk.DISABLED)
        self.status_label.config(text="Requesting a normal quit...")
        self._selected_create_times: dict[int, float] = {}
        for pid in allowed:
            create_time = self.processes[pid].create_time
            if create_time is not None:
                self._selected_create_times[pid] = create_time
        run_in_thread(
            self,
            lambda: self.manager.request_quit(allowed, self._selected_create_times),
            self._after_normal_quit,
            self._show_error,
        )

    def _after_normal_quit(self, result: ProcessActionResult) -> None:
        self.normal_quit_result = result
        if result.force_required:
            force = messagebox.askyesno(
                "Force Quit?",
                f"{len(result.force_required)} process(es) did not quit normally. "
                "Force quit them now?\n\nUnsaved work may be lost.",
                parent=self,
            )
            if force:
                self.status_label.config(text="Force quitting selected processes...")
                create_times = getattr(self, "_selected_create_times", {})
                run_in_thread(
                    self,
                    lambda: self.manager.force_quit(
                        list(result.force_required),
                        create_times,
                    ),
                    self._after_force_quit,
                    self._show_error,
                )
                return

        self._finish_process_action(result)

    def _after_force_quit(self, result: ProcessActionResult) -> None:
        normal_result = self.normal_quit_result
        if normal_result is None:
            self._finish_process_action(result)
            return

        combined = ProcessActionResult(
            requested=normal_result.requested,
            stopped=tuple(dict.fromkeys((*normal_result.stopped, *result.stopped))),
            force_required=result.force_required,
            errors=(*normal_result.errors, *result.errors),
        )
        self._finish_process_action(combined)

    def _finish_process_action(self, result: ProcessActionResult) -> None:
        show_action_result(
            self,
            "Process Cleanup",
            f"Stopped {len(result.stopped)} process(es).",
            result.errors,
        )
        self.on_changed()
        self.refresh()

    def _close(self) -> None:
        close_coordinated_dialog(
            self,
            key="process",
            unsubscribe_callback=self._on_shared_process_result,
            active=self._refresh_active,
        )

    def _show_error(self, message: str) -> None:
        self._finish_refresh()
        self.refresh_button.config(state=tk.NORMAL)
        self.quit_button.config(state=tk.NORMAL)
        self.status_label.config(text="Operation failed")
        messagebox.showerror("Process Error", message, parent=self)


class StorageDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        analyzer: Any,
        manager: FileManager,
        colors: dict[str, str],
        on_changed: Callable[[], None],
        coordinator: AppCoordinator | None = None,
    ) -> None:
        super().__init__(master)
        self.analyzer = analyzer
        self.manager = manager
        self.colors = colors
        self.on_changed = on_changed
        self.coordinator = coordinator or _standalone_coordinator(self)
        self.candidates: dict[str, FileCandidate] = {}
        self._scan_active = False
        self._waiting_for_shared = False

        self.title("Storage Cleanup")
        container = ui_layout.dialog_shell(
            self,
            master=master,
            title="Storage Cleanup",
            geometry="980x580",
            minsize=(820, 500),
            colors=colors,
            padx=24,
            pady=22,
            frame_cls=tk.Frame,
            on_close=self._close,
        )
        description_label = ui_layout.dialog_heading(
            container,
            "Storage Cleanup",
            (
                "Find large files and verified duplicates in Downloads. "
                "Only selected files are moved to Trash. "
                "Ctrl-click (Cmd-click on macOS) to select multiple files."
            ),
            label_cls=tk.Label,
            colors=colors,
            heading_font=ui_styles.FONTS["dialog_heading"],
            wrap=860,
        )
        ui_layout.resize_aware(
            container,
            ui_layout.fit_wrap_to_width(description_label, 860),
        )

        self.tree_frame = tk.Frame(container, bg=colors["card"])
        self.tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("path", "reason", "size", "modified")
        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=columns,
            show="headings",
            selectmode=tk.EXTENDED,
        )
        self.tree.heading("path", text="File")
        self.tree.heading("reason", text="Reason")
        self.tree.heading("size", text="Size")
        self.tree.heading("modified", text="Modified")
        self.tree.column(
            "path",
            width=480,
            minwidth=300,
            anchor=tk.W,
            stretch=False,
        )
        self.tree.column(
            "reason",
            width=180,
            minwidth=140,
            anchor=tk.W,
            stretch=False,
        )
        self.tree.column(
            "size",
            width=100,
            minwidth=85,
            anchor=tk.W,
            stretch=False,
        )
        self.tree.column(
            "modified",
            width=130,
            minwidth=120,
            anchor=tk.W,
            stretch=False,
        )

        y_scroll = ttk.Scrollbar(self.tree_frame, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(
            self.tree_frame,
            command=self.tree.xview,
            orient=tk.HORIZONTAL,
        )
        self.tree.config(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(
            row=0, column=1, sticky="ns", padx=(ui_layout.SCROLLBAR_GUTTER, 0)
        )
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.tree_frame.grid_rowconfigure(0, weight=1)
        self.tree_frame.grid_columnconfigure(0, weight=1)
        self.tree.bind("<Configure>", self._resize_columns)

        footer, self.status_label = ui_layout.dialog_footer(
            container,
            frame_cls=tk.Frame,
            label_cls=tk.Label,
            colors=colors,
            status_text="Ready to scan Downloads",
        )
        self.scan_button, self.trash_button = ui_layout.pack_action_buttons(
            footer,
            [
                (
                    "Scan Downloads",
                    self.scan,
                    ui_styles.STYLE_NEUTRAL_BUTTON,
                    (8, 0),
                ),
                ("Move Selected to Trash", self.move_selected, "Danger.TButton", None),
            ],
            button_cls=ttk.Button,
        )

        cached = self.coordinator.last_result("storage")
        if cached is not None:
            self._show_candidates(cached)
        self.scan()

    def _resize_columns(self, _event: tk.Event | None = None) -> None:
        available_width = self.tree.winfo_width()
        if available_width <= 1:
            return

        reason_width = 140
        size_width = 85
        modified_width = 120
        path_width = max(
            300,
            available_width - reason_width - size_width - modified_width,
        )
        widths = {
            "path": path_width,
            "reason": reason_width,
            "size": size_width,
            "modified": modified_width,
        }
        for column, width in widths.items():
            self.tree.column(column, width=width)

    def scan(self) -> None:
        if self._scan_active:
            return

        def scan_task(
            cancel_event: threading.Event,
            progress: Callable[[str], None],
        ) -> list[FileCandidate]:
            return call_legacy_compatible(
                lambda: self.analyzer.storage_candidates(
                    progress_callback=progress,
                    cancel_event=cancel_event,
                ),
                lambda: self.analyzer.storage_candidates(),
            )

        generation = self.coordinator.run(
            "storage",
            scan_task,
            on_result=lambda _key, candidates: self._on_scan_result(candidates),
            on_error=lambda _key, message: self._on_scan_error(message),
            on_progress=lambda _key, message: self._show_scan_progress(message),
        )
        if generation is None:
            self._wait_for_shared_scan()
            return

        self._scan_active = True
        self.scan_button.config(
            state=tk.NORMAL,
            text="Cancel Scan",
            command=self.cancel_scan,
        )
        self.trash_button.config(state=tk.DISABLED)
        self.status_label.config(text="Scanning Downloads and checking duplicates...")

    def _on_scan_result(self, candidates: list[FileCandidate]) -> None:
        self._set_scan_idle()
        self._show_candidates(candidates)

    def _on_scan_error(self, message: str) -> None:
        self._set_scan_idle()
        if message == DOWNLOADS_SCAN_CANCELLED:
            self.status_label.config(text=SCAN_CANCELLED_NOTICE)
            return
        self._show_error(message)

    def _wait_for_shared_scan(self) -> None:
        if self._waiting_for_shared:
            return
        self._waiting_for_shared = True
        self.status_label.config(text="Waiting for the active Downloads scan...")
        self.coordinator.subscribe("storage", self._on_shared_scan_result)

    def _on_shared_scan_result(self, _key: str, result: Any | None) -> None:
        self._waiting_for_shared = False
        if result is None:
            self.scan()
            return
        self._set_scan_idle()
        self._show_candidates(result)

    def cancel_scan(self) -> None:
        if not self._scan_active:
            return
        self.scan_button.config(state=tk.DISABLED)
        self.status_label.config(text="Cancelling Downloads scan...")
        self.coordinator.cancel(
            "storage",
            cancellation_message=DOWNLOADS_SCAN_CANCELLED,
        )

    def _close(self) -> None:
        close_coordinated_dialog(
            self,
            key="storage",
            unsubscribe_callback=self._on_shared_scan_result,
            active=self._scan_active,
        )

    def _show_scan_progress(self, message: str) -> None:
        if self._scan_active:
            self.status_label.config(text=message)

    def _set_scan_idle(self) -> None:
        self._scan_active = False
        self.scan_button.config(
            state=tk.NORMAL,
            text="Scan Downloads",
            command=self.scan,
        )
        self.trash_button.config(state=tk.NORMAL)

    def _show_candidates(self, candidates: list[FileCandidate]) -> None:
        self.candidates = {}
        rows: list[tuple[str, tuple[object, ...], tuple[str, ...]]] = []
        for index, candidate in enumerate(candidates):
            item_id = str(index)
            self.candidates[item_id] = candidate
            rows.append(
                (
                    item_id,
                    (
                        str(candidate.path),
                        candidate.reason,
                        SystemScanner.format_bytes(candidate.size_bytes),
                        candidate.modified_at.strftime("%Y-%m-%d %H:%M"),
                    ),
                    (),
                )
            )
        rebuild_tree_rows(self.tree, rows)

        if not candidates:
            self.status_label.config(text="No cleanup candidates found.")
            self.scan_button.config(state=tk.NORMAL)
            self.trash_button.config(state=tk.DISABLED)
            return

        total_bytes = sum(candidate.size_bytes for candidate in candidates)
        self.status_label.config(
            text=(
                f"{len(candidates)} candidate(s) • "
                f"up to {SystemScanner.format_bytes(total_bytes)} reviewable"
            )
        )
        self.scan_button.config(state=tk.NORMAL)
        self.trash_button.config(state=tk.NORMAL)

    def move_selected(self) -> None:
        selected = [
            self.candidates[item]
            for item in self.tree.selection()
            if item in self.candidates
        ]
        if not selected:
            messagebox.showinfo(
                "Nothing Selected",
                "Select one or more files to move to Trash.",
                parent=self,
            )
            return

        total = sum(candidate.size_bytes for candidate in selected)
        confirmed = messagebox.askyesno(
            "Move Files to Trash?",
            f"Move {len(selected)} selected file(s) "
            f"({SystemScanner.format_bytes(total)}) to Trash?\n\n"
            "The files will not be permanently deleted.",
            parent=self,
        )
        if not confirmed:
            return

        self.scan_button.config(state=tk.DISABLED)
        self.trash_button.config(state=tk.DISABLED)
        self.status_label.config(text="Moving selected files to Trash...")
        paths: list[Path] = [candidate.path for candidate in selected]
        run_in_thread(
            self,
            lambda: self.manager.move_to_trash(paths),
            self._after_trash,
            self._show_error,
        )

    def _after_trash(self, result: FileActionResult) -> None:
        show_action_result(
            self,
            "Storage Cleanup",
            f"Moved {len(result.moved)} file(s) to Trash.",
            result.errors,
        )
        self.on_changed()
        self.scan()

    def _show_error(self, message: str) -> None:
        self.scan_button.config(state=tk.NORMAL)
        self.trash_button.config(state=tk.NORMAL)
        self.status_label.config(text="Operation failed")
        messagebox.showerror("Storage Error", message, parent=self)
