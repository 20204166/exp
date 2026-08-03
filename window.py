import tkinter as tk
from tkinter import messagebox

import algo


class AppWindow:
    def __init__(self) -> None:
        self.master = tk.Tk()
        self.master.title("Number Analyzer")
        self.master.geometry("420x300")
        self.master.resizable(False, False)

        self.title_label = tk.Label(
            self.master,
            text="Number Analyzer",
            font=("Arial", 18, "bold"),
        )
        self.title_label.pack(pady=(20, 10))

        self.instruction_label = tk.Label(
            self.master,
            text="Enter a whole number:",
        )
        self.instruction_label.pack()

        self.number_entry = tk.Entry(
            self.master,
            width=25,
            justify="center",
        )
        self.number_entry.pack(pady=8)

        self.analyze_button = tk.Button(
            self.master,
            text="Analyze number",
            command=self.handle_analyze,
        )
        self.analyze_button.pack()

        self.random_button = tk.Button(
            self.master,
            text="Generate random number",
            command=self.handle_random,
        )
        self.random_button.pack(pady=10)

        self.result_label = tk.Label(
            self.master,
            text="",
            font=("Arial", 12),
            wraplength=380,
        )
        self.result_label.pack(pady=10)

    def handle_analyze(self) -> None:
        text = self.number_entry.get().strip()

        try:
            number = int(text)
        except ValueError:
            messagebox.showerror(
                "Invalid input",
                "Please enter a valid whole number.",
            )
            return

        random_number = algo.generate_random_number()
        result = algo.analyze_number(number, random_number)

        self.result_label.config(text=result)

    def handle_random(self) -> None:
        random_number = algo.generate_random_number()

        self.number_entry.delete(0, tk.END)
        self.number_entry.insert(0, str(random_number))

        self.result_label.config(
            text=f"Generated number: {random_number}"
        )

    def run(self) -> None:
        self.master.mainloop()