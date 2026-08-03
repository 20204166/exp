import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from maintenance.actions import FileManager, ProcessManager
from maintenance.models import (
    FileActionResult,
    FileCandidate,
    ProcessActionResult,
    ProcessCandidate,
    ResourceSummary,
)
from maintenance.scanner import SystemScanner


def run_in_thread(
    widget: tk.Misc,
    task: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[str], None] | None = None,
) -> None:
    """Run work off the Tkinter thread and safely deliver the result."""

    def deliver(callback: Callable, value: Any) -> None:
        try:
            if widget.winfo_exists():
                callback(value)
        except tk.TclError:
            pass

    def worker() -> None:
        try:
            result = task()
        except Exception as error:
            callback = on_error or (
                lambda message: messagebox.showerror(
                    "Operation Error",
                    message,
                    parent=widget,
                )
            )
            try:
                widget.after(0, deliver, callback, str(error))
            except tk.TclError:
                pass
        else:
            try:
                widget.after(0, deliver, on_success, result)
            except tk.TclError:
                pass

    threading.Thread(target=worker, daemon=True).start()


class ResourceCard(tk.Frame):
    """Clickable summary card for one system resource."""

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
        )
        self.value_label.pack(anchor=tk.W, pady=(10, 2))

        self.subtitle_label = tk.Label(
            self,
            text="Run a scan to load details",
            bg=colors["card"],
            fg=colors["secondary"],
            font=("Helvetica", 10),
            anchor=tk.W,
            cursor="hand2",
        )
        self.subtitle_label.pack(anchor=tk.W)

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

        for child in (self, *self.winfo_children()):
            child.bind("<Button-1>", self._open)

    def _open(self, _event: tk.Event | None = None) -> None:
        self.on_open(self.key)

    def update_summary(self, summary: ResourceSummary) -> None:
        self.value_label.config(text=summary.value)
        self.subtitle_label.config(text=summary.subtitle)
        self.progress.config(value=summary.percent or 0)
        action_text = "Review and clean  →" if summary.actionable else "View details  →"
        self.details_label.config(text=action_text)


class InfoDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        summary: ResourceSummary,
        colors: dict[str, str],
    ) -> None:
        super().__init__(master)
        self.title(f"{summary.title} Details")
        self.geometry("560x360")
        self.minsize(500, 320)
        self.configure(bg=colors["background"])
        self.transient(master)

        container = tk.Frame(self, bg=colors["background"], padx=28, pady=24)
        container.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            container,
            text=summary.title,
            bg=colors["background"],
            fg=colors["text"],
            font=("Helvetica", 22, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            container,
            text=summary.subtitle,
            bg=colors["background"],
            fg=colors["secondary"],
            font=("Helvetica", 11),
        ).pack(anchor=tk.W, pady=(4, 18))

        card = tk.Frame(
            container,
            bg=colors["card"],
            highlightbackground=colors["border"],
            highlightthickness=1,
            padx=20,
            pady=18,
        )
        card.pack(fill=tk.BOTH, expand=True)

        for line in summary.details:
            tk.Label(
                card,
                text=line,
                bg=colors["card"],
                fg=colors["text"],
                font=("Helvetica", 11),
                anchor=tk.W,
                justify=tk.LEFT,
                wraplength=460,
            ).pack(anchor=tk.W, pady=4)

        ttk.Button(container, text="Close", command=self.destroy).pack(
            anchor=tk.E,
            pady=(16, 0),
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
    ) -> None:
        super().__init__(master)
        self.analyzer = analyzer
        self.manager = manager
        self.resource_key = resource_key
        self.colors = colors
        self.on_changed = on_changed
        self.processes: dict[int, ProcessCandidate] = {}
        self.normal_quit_result: ProcessActionResult | None = None

        title = "Memory Processes" if resource_key == "memory" else "CPU Processes"
        self.title(title)
        self.geometry("900x560")
        self.minsize(760, 480)
        self.configure(bg=colors["background"])
        self.transient(master)

        container = tk.Frame(self, bg=colors["background"], padx=24, pady=22)
        container.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            container,
            text=title,
            bg=colors["background"],
            fg=colors["text"],
            font=("Helvetica", 20, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            container,
            text=(
                "Select user processes to request a normal quit. "
                "Protected processes cannot be selected for cleanup."
            ),
            bg=colors["background"],
            fg=colors["secondary"],
            font=("Helvetica", 10),
            wraplength=800,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 14))

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
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)

        scrollbar = ttk.Scrollbar(tree_frame, command=self.tree.yview)
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure("protected", foreground="#98A2B3")
        self.tree.tag_configure("low", foreground="#B45309")

        footer = tk.Frame(container, bg=colors["background"])
        footer.pack(fill=tk.X, pady=(14, 0))
        self.status_label = tk.Label(
            footer,
            text="Loading processes...",
            bg=colors["background"],
            fg=colors["secondary"],
            font=("Helvetica", 10),
        )
        self.status_label.pack(side=tk.LEFT)
        ttk.Button(footer, text="Refresh", command=self.refresh).pack(
            side=tk.RIGHT,
            padx=(8, 0),
        )
        self.quit_button = ttk.Button(
            footer,
            text="Quit Selected",
            command=self.quit_selected,
            style="Danger.TButton",
        )
        self.quit_button.pack(side=tk.RIGHT)

        self.refresh()

    def refresh(self) -> None:
        self.quit_button.config(state=tk.DISABLED)
        self.status_label.config(text="Scanning active processes...")
        run_in_thread(
            self,
            self.analyzer.process_candidates,
            self._show_processes,
            self._show_error,
        )

    def _show_processes(self, processes: list[ProcessCandidate]) -> None:
        self.tree.delete(*self.tree.get_children())
        sort_key = (
            (lambda item: item.memory_bytes)
            if self.resource_key == "memory"
            else (lambda item: item.cpu_percent)
        )
        ordered = sorted(processes, key=sort_key, reverse=True)
        self.processes = {process.pid: process for process in ordered}

        for process in ordered:
            tags = ()
            if not process.action_allowed:
                tags = ("protected",)
            elif process.activity == "Low activity":
                tags = ("low",)

            self.tree.insert(
                "",
                tk.END,
                iid=str(process.pid),
                values=(
                    process.name,
                    process.pid,
                    SystemScanner.format_bytes(process.memory_bytes),
                    f"{process.cpu_percent:.1f}%",
                    process.activity,
                    "Can quit" if process.action_allowed else "Protected",
                ),
                tags=tags,
            )

        allowed_count = sum(item.action_allowed for item in ordered)
        self.status_label.config(
            text=f"{len(ordered)} shown • {allowed_count} available for review"
        )
        self.quit_button.config(state=tk.NORMAL)

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
        run_in_thread(
            self,
            lambda: self.manager.request_quit(allowed),
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
                run_in_thread(
                    self,
                    lambda: self.manager.force_quit(list(result.force_required)),
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
        message = f"Stopped {len(result.stopped)} process(es)."
        if result.errors:
            message += "\n\n" + "\n".join(result.errors[:6])
        messagebox.showinfo("Process Cleanup", message, parent=self)
        self.on_changed()
        self.refresh()

    def _show_error(self, message: str) -> None:
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
    ) -> None:
        super().__init__(master)
        self.analyzer = analyzer
        self.manager = manager
        self.colors = colors
        self.on_changed = on_changed
        self.candidates: dict[str, FileCandidate] = {}

        self.title("Storage Cleanup")
        self.geometry("980x580")
        self.minsize(820, 500)
        self.configure(bg=colors["background"])
        self.transient(master)

        container = tk.Frame(self, bg=colors["background"], padx=24, pady=22)
        container.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            container,
            text="Storage Cleanup",
            bg=colors["background"],
            fg=colors["text"],
            font=("Helvetica", 20, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            container,
            text=(
                "Find large files and verified duplicates in Downloads. "
                "Only selected files are moved to Trash."
            ),
            bg=colors["background"],
            fg=colors["secondary"],
            font=("Helvetica", 10),
            wraplength=860,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 14))

        tree_frame = tk.Frame(container, bg=colors["card"])
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("path", "reason", "size", "modified")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("path", text="File")
        self.tree.heading("reason", text="Reason")
        self.tree.heading("size", text="Size")
        self.tree.heading("modified", text="Modified")
        self.tree.column("path", width=480, anchor=tk.W)
        self.tree.column("reason", width=180, anchor=tk.W)
        self.tree.column("size", width=100, anchor=tk.W)
        self.tree.column("modified", width=130, anchor=tk.W)

        y_scroll = ttk.Scrollbar(tree_frame, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(
            tree_frame,
            command=self.tree.xview,
            orient=tk.HORIZONTAL,
        )
        self.tree.config(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        footer = tk.Frame(container, bg=colors["background"])
        footer.pack(fill=tk.X, pady=(14, 0))
        self.status_label = tk.Label(
            footer,
            text="Ready to scan Downloads",
            bg=colors["background"],
            fg=colors["secondary"],
            font=("Helvetica", 10),
        )
        self.status_label.pack(side=tk.LEFT)
        self.scan_button = ttk.Button(
            footer,
            text="Scan Downloads",
            command=self.scan,
        )
        self.scan_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.trash_button = ttk.Button(
            footer,
            text="Move Selected to Trash",
            command=self.move_selected,
            style="Danger.TButton",
        )
        self.trash_button.pack(side=tk.RIGHT)

        self.scan()

    def scan(self) -> None:
        self.scan_button.config(state=tk.DISABLED)
        self.trash_button.config(state=tk.DISABLED)
        self.status_label.config(text="Scanning Downloads and checking duplicates...")
        run_in_thread(
            self,
            self.analyzer.storage_candidates,
            self._show_candidates,
            self._show_error,
        )

    def _show_candidates(self, candidates: list[FileCandidate]) -> None:
        self.tree.delete(*self.tree.get_children())
        self.candidates = {}

        for index, candidate in enumerate(candidates):
            item_id = str(index)
            self.candidates[item_id] = candidate
            self.tree.insert(
                "",
                tk.END,
                iid=item_id,
                values=(
                    str(candidate.path),
                    candidate.reason,
                    SystemScanner.format_bytes(candidate.size_bytes),
                    candidate.modified_at.strftime("%Y-%m-%d %H:%M"),
                ),
            )

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
        message = f"Moved {len(result.moved)} file(s) to Trash."
        if result.errors:
            message += "\n\n" + "\n".join(result.errors[:6])
        messagebox.showinfo("Storage Cleanup", message, parent=self)
        self.on_changed()
        self.scan()

    def _show_error(self, message: str) -> None:
        self.scan_button.config(state=tk.NORMAL)
        self.trash_button.config(state=tk.NORMAL)
        self.status_label.config(text="Operation failed")
        messagebox.showerror("Storage Error", message, parent=self)