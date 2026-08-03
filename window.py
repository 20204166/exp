import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

import algo


class AppWindow:
    BACKGROUND = "#F4F7FB"
    CARD_BACKGROUND = "#FFFFFF"
    TEXT_PRIMARY = "#172033"
    TEXT_SECONDARY = "#667085"
    ACCENT = "#4F46E5"
    ACCENT_ACTIVE = "#4338CA"
    BORDER = "#E4E7EC"

    def __init__(self) -> None:
        self.analyzer = algo.Analyzer(memory_test_percent=1.0)

        self.master = tk.Tk()
        self.master.title("System Analyzer")
        self.master.geometry("780x560")
        self.master.minsize(680, 480)
        self.master.configure(bg=self.BACKGROUND)

        self._configure_styles()

        self.main_frame = ttk.Frame(
            self.master,
            padding=(32, 28),
            style="App.TFrame",
        )
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.title_label = ttk.Label(
            self.main_frame,
            text="System Analyzer",
            style="Title.TLabel",
        )
        self.title_label.pack(anchor=tk.W)

        self.description_label = ttk.Label(
            self.main_frame,
            text=(
                "Inspect your CPU, memory, storage, GPU, network, and battery, "
                "then run a controlled 1% RAM test."
            ),
            wraplength=700,
            style="Description.TLabel",
        )
        self.description_label.pack(anchor=tk.W, pady=(6, 22))

        self.action_frame = ttk.Frame(
            self.main_frame,
            style="App.TFrame",
        )
        self.action_frame.pack(fill=tk.X, pady=(0, 12))

        self.analyze_button = ttk.Button(
            self.action_frame,
            text="Run Complete Analysis",
            command=self.handle_analyze,
            style="Primary.TButton",
            cursor="hand2",
        )
        self.analyze_button.pack(side=tk.LEFT)

        self.status_label = ttk.Label(
            self.action_frame,
            text="●  Ready",
            style="Ready.Status.TLabel",
        )
        self.status_label.pack(side=tk.RIGHT, padx=(16, 0))

        self.progress_bar = ttk.Progressbar(
            self.main_frame,
            mode="indeterminate",
            style="Analysis.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 18))

        self.output_card = tk.Frame(
            self.main_frame,
            bg=self.CARD_BACKGROUND,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        self.output_card.pack(fill=tk.BOTH, expand=True)

        self.output_header = tk.Label(
            self.output_card,
            text="ANALYSIS OUTPUT",
            bg=self.CARD_BACKGROUND,
            fg=self.TEXT_SECONDARY,
            font=("Helvetica", 10, "bold"),
        )
        self.output_header.pack(anchor=tk.W, padx=18, pady=(16, 8))

        self.output_separator = ttk.Separator(
            self.output_card,
            orient=tk.HORIZONTAL,
        )
        self.output_separator.pack(fill=tk.X, padx=18)

        self.output_frame = tk.Frame(
            self.output_card,
            bg=self.CARD_BACKGROUND,
        )
        self.output_frame.pack(
            fill=tk.BOTH,
            expand=True,
            padx=4,
            pady=(4, 8),
        )

        self.scrollbar = ttk.Scrollbar(self.output_frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.output_text = tk.Text(
            self.output_frame,
            wrap=tk.WORD,
            yscrollcommand=self.scrollbar.set,
            bg=self.CARD_BACKGROUND,
            fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY,
            selectbackground="#DDE3FF",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            padx=14,
            pady=12,
            font=("Menlo", 10),
            spacing1=2,
            spacing3=3,
        )
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.output_text.yview)

        self._write_output(
            "Your system analysis will appear here.\n\n"
            "Select “Run Complete Analysis” to begin."
        )

    def _configure_styles(self) -> None:
        style = ttk.Style(self.master)
        style.theme_use("clam")

        style.configure(
            "App.TFrame",
            background=self.BACKGROUND,
        )
        style.configure(
            "Title.TLabel",
            background=self.BACKGROUND,
            foreground=self.TEXT_PRIMARY,
            font=("Helvetica", 24, "bold"),
        )
        style.configure(
            "Description.TLabel",
            background=self.BACKGROUND,
            foreground=self.TEXT_SECONDARY,
            font=("Helvetica", 11),
        )
        style.configure(
            "Primary.TButton",
            background=self.ACCENT,
            foreground="#FFFFFF",
            font=("Helvetica", 11, "bold"),
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
            "Ready.Status.TLabel",
            background=self.BACKGROUND,
            foreground="#16803C",
            font=("Helvetica", 10, "bold"),
        )
        style.configure(
            "Busy.Status.TLabel",
            background=self.BACKGROUND,
            foreground="#B45309",
            font=("Helvetica", 10, "bold"),
        )
        style.configure(
            "Analysis.Horizontal.TProgressbar",
            background=self.ACCENT,
            troughcolor="#E8ECF5",
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
        button_state = tk.DISABLED if is_busy else tk.NORMAL
        self.analyze_button.config(state=button_state)

        if is_busy:
            self.status_label.config(
                text="●  Analyzing...",
                style="Busy.Status.TLabel",
            )
            self.progress_bar.start(12)
        else:
            self.status_label.config(
                text="●  Ready",
                style="Ready.Status.TLabel",
            )
            self.progress_bar.stop()

    def _show_result(self, result: str) -> None:
        self._write_output(result)
        self._set_busy(False)

    def _show_error(self, message: str) -> None:
        messagebox.showerror("Analysis Error", message)
        self._set_busy(False)

    def _run_in_background(self, task: Callable[[], str]) -> None:
        self._set_busy(True)

        def worker() -> None:
            try:
                result = task()
            except Exception as error:
                self.master.after(0, self._show_error, str(error))
            else:
                self.master.after(0, self._show_result, result)

        threading.Thread(target=worker, daemon=True).start()

    def handle_analyze(self) -> None:
        self._run_in_background(self.analyzer.analyze_all)

    def run(self) -> None:
        self.master.mainloop()