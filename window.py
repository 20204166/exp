import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox

import algo


class AppWindow:
    def __init__(self) -> None:
        self.analyzer = Analyzer(memory_test_percentage=1.0)

        self.master = tk.Tk()
        self.master.title("System Analyzer")
        self.master.geometry("720x300")
        self.master.minsize(420, 300)

        self.title_label = tk.Label(
            self.master,
            text="System Analyzer",
            font=("Arial", 18, "bold"),
        )
        self.title_label.pack(pady=(20, 5))

        self.description_label = tk.Label(
            self.master,
            text=(
                "Inspect CPU, RAM, and GPU, network, and battery,"
                " or run a controlled 1% RAM test."
            ),
            wraplength=660,
        )
        self.description_label.pack(pady=(0, 12))
        
        self.button_frame = tk.Frame(self.master)
        self.button_frame.pack(pady=(0, 5))

        self.analyze_button = tk.Button(
            self.button_frame,
            text="Analyze system",
            width=15,
            command=self.handle_analyze,
        )
        self.analyze_button.pack(side=tk.LEFT, padx=5)

        self.memory_button = tk.Button(
            self.button_frame,
            text="Generate random number",
            command=self.handle_memory_test,
        )
        self.memory_button.pack(pady=10)

        self.result_label = tk.Label(
            self.master,
            text="Ready",
            fg="blue",
        
        )
        self.status_label.pack(pady=8)

        self.output_frame = tk.Frame(self.master)
        self.output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.scrollbar = tk.Scrollbar(self.output_frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.output_text = tk.Text(
            self.output_frame,
            wrap=tk.WORD,
            yscrollcommand=self.scrollbar.set,
        )
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.output_text.yview)
    
    def _set_busy(self, is_busy: bool) -> None:
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, "Analyzing..." if is_busy else "Ready")
        self._set_busy(False)
    
    def _show_error(self, message: str) -> None:
        messagebox.showerror("Error", message)
        self._set_busy(False)

    def _run_in_background(self, func, *args, task: Callable[[], str]) -> None:
        self._set_busy(True)
        
        def worker() -> None:
            try:
                func(*args)
                result = task()
                self.output_text.delete(1.0, tk.END)
                self.output_text.insert(tk.END, result)
            except Exception as e:
                self.master.after(0, self._show_error, str(e))
            else:
                self.master.after(0, self._set_busy, False)

        threading.Thread(target=worker, daemon=True).start()

    def handle_analyze(self) -> None:
        text = self._run_in_background(self.analyzer.full_report)

    def handle_memory_test(self) -> None:
        should_run = messagebox.askyesno(
            "Memory Test",
            "This will run a controlled 1% RAM test. Do you want to proceed?",
        )

        if should_run:
            self._run_in_background(self.analyzer.test_memory)
            
    def run(self) -> None:
        self.master.mainloop()