import logging
import threading
import tkinter as tk
from collections.abc import Callable
from queue import Empty, Queue
from tkinter import messagebox, ttk

import algo
from maintenance.actions import FileManager, ProcessManager
from maintenance.dialogs import (
    InfoDialog,
    ProcessDialog,
    ResourceCard,
    StorageDialog,
)
from maintenance.models import DashboardSnapshot


LOGGER = logging.getLogger(__name__)


class AppWindow:
    BACKGROUND = "#F4F7FB"
    CARD_BACKGROUND = "#FFFFFF"
    TEXT_PRIMARY = "#172033"
    TEXT_SECONDARY = "#667085"
    ACCENT = "#4F46E5"
    ACCENT_ACTIVE = "#4338CA"
    BORDER = "#E4E7EC"
    AUTO_SCAN_MILLISECONDS = 5000
    UI_FONT = "Helvetica"
    FIXED_FONT = "TkFixedFont"
    TITLE_FONT = (UI_FONT, 24, "bold")
    SECTION_FONT = (UI_FONT, 14, "bold")
    BODY_FONT = (UI_FONT, 10)
    BUTTON_FONT = (UI_FONT, 11, "bold")
    DANGER_BUTTON_FONT = (UI_FONT, 10, "bold")
    STATUS_FONT = (UI_FONT, 10, "bold")
    OUTPUT_HEADER_FONT = (UI_FONT, 10, "bold")
    OUTPUT_FONT = FIXED_FONT
    BACKGROUND_POLL_MILLISECONDS = 10

    RESOURCE_CARDS = (
        ("cpu", "CPU"),
        ("memory", "Memory"),
        ("storage", "Storage"),
        ("gpu", "GPU"),
        ("network", "Network"),
        ("battery", "Battery"),
    )

    def __init__(self) -> None:
        self.analyzer = algo.Analyzer(memory_test_percent=1.0)
        self.process_manager = ProcessManager()
        self.file_manager = FileManager(self.analyzer.scanner.downloads_path)
        self.snapshot: DashboardSnapshot | None = None
        self.auto_scan_id: str | None = None
        self._is_closing = False
        self._pending_after_ids: set[str] = set()
        self._background_poll_id: str | None = None
        self._background_tasks = 0
        self._analysis_active = False
        self._analysis_generation = 0
        self._analysis_requested = False
        self._analysis_cancel_event: threading.Event | None = None
        self._background_queue: Queue[
            tuple[Callable[..., None], tuple[object, ...]] | None
        ] = Queue()

        self.master = tk.Tk()
        self.master.title("System Analyzer")
        self.master.geometry("1040x760")
        self.master.minsize(900, 680)
        self.master.configure(bg=self.BACKGROUND)
        self.master.protocol("WM_DELETE_WINDOW", self._close)

        self._configure_styles()
        self._build_window()
        self._schedule_timer(350, self.handle_analyze)

    @property
    def colors(self) -> dict[str, str]:
        return {
            "background": self.BACKGROUND,
            "card": self.CARD_BACKGROUND,
            "text": self.TEXT_PRIMARY,
            "secondary": self.TEXT_SECONDARY,
            "accent": self.ACCENT,
            "border": self.BORDER,
        }

    def _build_window(self) -> None:
        self.main_frame = ttk.Frame(
            self.master,
            padding=(30, 26),
            style="App.TFrame",
        )
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.header_frame = ttk.Frame(self.main_frame, style="App.TFrame")
        self.header_frame.pack(fill=tk.X)

        self.heading_frame = ttk.Frame(self.header_frame, style="App.TFrame")
        self.heading_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.title_label = ttk.Label(
            self.heading_frame,
            text="System Analyzer",
            style="Title.TLabel",
        )
        self.title_label.pack(anchor=tk.W)

        self.description_label = ttk.Label(
            self.heading_frame,
            text=(
                "Scan your system, open any category, and review safe cleanup "
                "actions before anything changes."
            ),
            wraplength=680,
            style="Description.TLabel",
        )
        self.description_label.pack(anchor=tk.W, pady=(6, 0))

        self.header_actions = ttk.Frame(self.header_frame, style="App.TFrame")
        self.header_actions.pack(side=tk.RIGHT, padx=(20, 0))

        self.analyze_button = ttk.Button(
            self.header_actions,
            text="Scan System",
            command=self.handle_analyze,
            style="Primary.TButton",
            cursor="hand2",
        )
        self.analyze_button.pack(anchor=tk.E)

        self.status_label = ttk.Label(
            self.header_actions,
            text="●  Ready",
            style="Ready.Status.TLabel",
        )
        self.status_label.pack(anchor=tk.E, pady=(9, 0))

        self.progress_bar = ttk.Progressbar(
            self.main_frame,
            mode="indeterminate",
            style="Analysis.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill=tk.X, pady=(22, 20))

        self.overview_frame = ttk.Frame(self.main_frame, style="App.TFrame")
        self.overview_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            self.overview_frame,
            text="System overview",
            style="Section.TLabel",
        ).pack(side=tk.LEFT)
        self.scan_time_label = ttk.Label(
            self.overview_frame,
            text="Not scanned yet",
            style="Description.TLabel",
        )
        self.scan_time_label.pack(side=tk.RIGHT)

        self.cards_frame = ttk.Frame(self.main_frame, style="App.TFrame")
        self.cards_frame.pack(fill=tk.X)
        for column in range(3):
            self.cards_frame.grid_columnconfigure(column, weight=1, uniform="cards")

        self.cards: dict[str, ResourceCard] = {}
        for index, (key, title) in enumerate(self.RESOURCE_CARDS):
            card = ResourceCard(
                self.cards_frame,
                key=key,
                title=title,
                on_open=self.open_resource,
                colors=self.colors,
            )
            card.grid(
                row=index // 3,
                column=index % 3,
                sticky="nsew",
                padx=(0 if index % 3 == 0 else 7, 0 if index % 3 == 2 else 7),
                pady=(0, 14),
            )
            self.cards[key] = card

        self.output_card = tk.Frame(
            self.main_frame,
            bg=self.CARD_BACKGROUND,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        self.output_card.pack(fill=tk.BOTH, expand=True, pady=(2, 0))

        self.output_header = tk.Label(
            self.output_card,
            text="LATEST SCAN",
            bg=self.CARD_BACKGROUND,
            fg=self.TEXT_SECONDARY,
            font=self.OUTPUT_HEADER_FONT,
        )
        self.output_header.pack(anchor=tk.W, padx=18, pady=(14, 8))

        ttk.Separator(self.output_card, orient=tk.HORIZONTAL).pack(
            fill=tk.X,
            padx=18,
        )

        self.output_frame = tk.Frame(self.output_card, bg=self.CARD_BACKGROUND)
        self.output_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 8))

        self.scrollbar = ttk.Scrollbar(self.output_frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.output_text = tk.Text(
            self.output_frame,
            wrap=tk.WORD,
            yscrollcommand=self.scrollbar.set,
            bg=self.CARD_BACKGROUND,
            fg=self.TEXT_PRIMARY,
            selectbackground="#DDE3FF",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            padx=14,
            pady=10,
            height=8,
            font=self.OUTPUT_FONT,
            spacing1=2,
            spacing3=3,
        )
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.output_text.yview)

        self._write_output(
            "The first read-only system scan will begin automatically.\n\n"
            "Nothing is quit, removed, or moved without your confirmation."
        )

    def _configure_styles(self) -> None:
        style = ttk.Style(self.master)
        style.theme_use("clam")

        style.configure("App.TFrame", background=self.BACKGROUND)
        style.configure(
            "Title.TLabel",
            background=self.BACKGROUND,
            foreground=self.TEXT_PRIMARY,
            font=self.TITLE_FONT,
        )
        style.configure(
            "Section.TLabel",
            background=self.BACKGROUND,
            foreground=self.TEXT_PRIMARY,
            font=self.SECTION_FONT,
        )
        style.configure(
            "Description.TLabel",
            background=self.BACKGROUND,
            foreground=self.TEXT_SECONDARY,
            font=self.BODY_FONT,
        )
        style.configure(
            "Primary.TButton",
            background=self.ACCENT,
            foreground="#FFFFFF",
            font=self.BUTTON_FONT,
            padding=(18, 11),
            borderwidth=0,
            focusthickness=0,
            focuscolor=self.ACCENT,
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", self.ACCENT_ACTIVE),
                ("disabled", "#A5B4FC"),
            ],
            foreground=[("disabled", "#EEF2FF")],
        )
        style.configure(
            "Danger.TButton",
            background="#B42318",
            foreground="#FFFFFF",
            font=self.DANGER_BUTTON_FONT,
            padding=(12, 8),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#912018"), ("disabled", "#D0D5DD")],
        )
        style.configure(
            "Ready.Status.TLabel",
            background=self.BACKGROUND,
            foreground="#16803C",
            font=self.STATUS_FONT,
        )
        style.configure(
            "Busy.Status.TLabel",
            background=self.BACKGROUND,
            foreground="#B45309",
            font=self.STATUS_FONT,
        )
        style.configure(
            "Analysis.Horizontal.TProgressbar",
            background=self.ACCENT,
            troughcolor="#E8ECF5",
            borderwidth=0,
            lightcolor=self.ACCENT,
            darkcolor=self.ACCENT,
        )
        style.configure(
            "Card.Horizontal.TProgressbar",
            background=self.ACCENT,
            troughcolor="#EEF2F6",
            borderwidth=0,
            lightcolor=self.ACCENT,
            darkcolor=self.ACCENT,
        )

    def _write_output(self, text: str) -> None:
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, text)
        self.output_text.config(state=tk.DISABLED)

    def _set_busy(self, is_busy: bool) -> None:
        self.analyze_button.config(state=tk.DISABLED if is_busy else tk.NORMAL)

        if is_busy:
            self.status_label.config(
                text="●  Scanning...",
                style="Busy.Status.TLabel",
            )
            self.progress_bar.start(12)
        else:
            self.status_label.config(
                text="●  Ready",
                style="Ready.Status.TLabel",
            )
            self.progress_bar.stop()

    def _run_in_background(
        self,
        task: Callable[[], DashboardSnapshot],
        on_success: Callable[[DashboardSnapshot], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._set_busy(True)
        self._background_tasks += 1
        self._start_background_poll()
        success_callback = on_success or self._show_snapshot
        error_callback = on_error or self._show_error

        def worker() -> None:
            try:
                result = task()
            except Exception as error:
                self._background_queue.put((error_callback, (str(error),)))
            else:
                self._background_queue.put((success_callback, (result,)))
            finally:
                self._background_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def _start_background_poll(self) -> None:
        if self._background_poll_id is None and not self._is_closing:
            self._background_poll_id = self._schedule_timer(
                self.BACKGROUND_POLL_MILLISECONDS,
                self._drain_background_queue,
            )

    def _drain_background_queue(self) -> None:
        self._background_poll_id = None

        while True:
            try:
                item = self._background_queue.get_nowait()
            except Empty:
                break

            if item is None:
                self._background_tasks -= 1
                continue

            callback, args = item
            if not self._is_closing:
                callback(*args)

        if self._background_tasks > 0 and not self._is_closing:
            self._start_background_poll()

    def handle_analyze(self) -> None:
        if self._is_closing:
            return
        if self._analysis_active:
            self._analysis_requested = True
            return

        self._analysis_active = True
        self._analysis_generation += 1
        generation = self._analysis_generation
        cancel_event = threading.Event()
        self._analysis_cancel_event = cancel_event

        def dashboard_task() -> DashboardSnapshot:
            try:
                return self.analyzer.dashboard_snapshot(cancel_event=cancel_event)
            except TypeError as error:
                if "unexpected keyword argument" not in str(error):
                    raise
                return self.analyzer.dashboard_snapshot()

        self._run_in_background(
            dashboard_task,
            on_success=lambda snapshot: self._show_snapshot_for_generation(
                generation,
                snapshot,
            ),
            on_error=lambda message: self._show_error_for_generation(
                generation,
                message,
            ),
        )

    def _show_snapshot_for_generation(
        self,
        generation: int,
        snapshot: DashboardSnapshot,
    ) -> None:
        if generation != self._analysis_generation:
            return
        self._analysis_active = False
        self._analysis_cancel_event = None
        rerun_requested = self._analysis_requested
        self._analysis_requested = False
        self._show_snapshot(snapshot)
        if rerun_requested and not self._is_closing:
            self._schedule_timer(0, self.handle_analyze)

    def _show_error_for_generation(self, generation: int, message: str) -> None:
        if generation != self._analysis_generation:
            return
        self._analysis_active = False
        self._analysis_cancel_event = None
        rerun_requested = self._analysis_requested
        self._analysis_requested = False
        self._show_error(message)
        if rerun_requested and not self._is_closing:
            self._schedule_timer(0, self.handle_analyze)

    def _show_snapshot(self, snapshot: DashboardSnapshot) -> None:
        if self._is_closing:
            return

        self.snapshot = snapshot
        for resource in snapshot.resources:
            self.cards[resource.key].update_summary(resource)

        scanned_time = snapshot.scanned_at.strftime("%H:%M:%S")
        self.scan_time_label.config(
            text=f"{snapshot.system_label} • scanned {scanned_time}"
        )
        self._write_output(self._format_snapshot(snapshot))
        self._set_busy(False)
        self._schedule_auto_scan()

    @staticmethod
    def _format_snapshot(snapshot: DashboardSnapshot) -> str:
        lines = [
            "SYSTEM",
            snapshot.system_label,
            f"Scanned: {snapshot.scanned_at:%Y-%m-%d %H:%M:%S}",
        ]
        for resource in snapshot.resources:
            lines.extend(("", resource.title.upper(), *resource.details))
        return "\n".join(lines)

    def open_resource(self, resource_key: str) -> None:
        if self.snapshot is None:
            messagebox.showinfo(
                "Scan Required",
                "Run the system scan before opening resource details.",
                parent=self.master,
            )
            return

        summary = self.snapshot.get(resource_key)
        if resource_key in {"cpu", "memory"}:
            ProcessDialog(
                self.master,
                analyzer=self.analyzer,
                manager=self.process_manager,
                resource_key=resource_key,
                colors=self.colors,
                on_changed=self._rescan_after_change,
            )
        elif resource_key == "storage":
            StorageDialog(
                self.master,
                analyzer=self.analyzer,
                manager=self.file_manager,
                colors=self.colors,
                on_changed=self._rescan_after_change,
            )
        else:
            InfoDialog(self.master, summary=summary, colors=self.colors)

    def _rescan_after_change(self) -> None:
        self._schedule_timer(500, self.handle_analyze)

    def _schedule_auto_scan(self) -> None:
        if self._is_closing:
            return

        if not self._cancel_timer(self.auto_scan_id):
            return
        self.auto_scan_id = self._schedule_timer(
            self.AUTO_SCAN_MILLISECONDS,
            self._run_auto_scan,
        )

    def _schedule_timer(
        self,
        delay: int,
        callback: Callable[..., None],
        *args: object,
    ) -> str | None:
        if self._is_closing:
            return None

        identifier: str | None = None

        def run_callback() -> None:
            if identifier is not None:
                self._pending_after_ids.discard(identifier)
            if not self._is_closing:
                callback(*args)

        try:
            identifier = self.master.after(delay, run_callback)
        except (RuntimeError, tk.TclError):
            if not self._is_closing:
                LOGGER.exception("Failed to schedule Tkinter work")
            return None

        self._pending_after_ids.add(identifier)
        return identifier

    def _cancel_timer(self, identifier: str | None) -> bool:
        if identifier is None:
            return True

        try:
            self.master.after_cancel(identifier)
        except (RuntimeError, tk.TclError):
            if not self._is_closing:
                LOGGER.exception("Failed to cancel Tkinter work")
            else:
                self._pending_after_ids.discard(identifier)
            return False

        self._pending_after_ids.discard(identifier)
        return True

    def _run_auto_scan(self) -> None:
        self.auto_scan_id = None
        if not self._is_closing:
            self.handle_analyze()

    def _cancel_pending_timers(self) -> None:
        for identifier in tuple(self._pending_after_ids):
            self._cancel_timer(identifier)

    def _close(self) -> None:
        self._is_closing = True
        self._analysis_active = False
        self._analysis_requested = False
        if self._analysis_cancel_event is not None:
            self._analysis_cancel_event.set()
        self._analysis_cancel_event = None
        self._cancel_pending_timers()
        self.auto_scan_id = None
        self._background_poll_id = None
        self.master.destroy()

    def _show_error(self, message: str) -> None:
        if self._is_closing:
            return

        self._analysis_active = False
        self._set_busy(False)
        messagebox.showerror("Analysis Error", message, parent=self.master)

    def run(self) -> None:
        try:
            self.master.mainloop()
        finally:
            self._is_closing = True
            self._cancel_pending_timers()
            self.auto_scan_id = None
            self._background_poll_id = None
