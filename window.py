import tkinter as tk 

from algo import generate_random_number, analyze_number, NumberAnalyzer

class Appwindow:
    def __init__(self, master):

        Pd = str(pady=int(5))
        self.master = master
        self.master.title("Number Analyzer")
        self.master.geometry("400x200")

        self.number_entry = tk.Entry(self.master)
        self.number_entry.pack(Pd)

        self.analyze_button = tk.Button(
            self.master, 
            text="Analyze", 
            command=self.analyze_number
        )
        self.analyze_button.pack(Pd)

        self.random_button = tk.Button(
            self.master, 
            text="Generate Random Number", 
            command=self.generate_random_number
        )

        self.random_button.pack(Pd)

        def handle_analyze(self) -> None:
            text = self.number_entry.get()

            try:
                number = int(text)
            except ValueError:
                tk.messagebox.showerror("Invalid input", "Please enter a valid integer.")
                return

            result = analyze_number(number)
            tk.messagebox.showinfo("Result", result)

        def handle_random(self) -> None:
            result = generate_random_number()

            self.number_entry.delete(0, tk.END)
            self.number_entry.insert(0, str(result))
            result = generate_random_number(NumberAnalyzer(self.number_entry.get()))

            self.result_label.config(text=f"Random number generated: {result}")

        def run(self) -> None:
            self.master.mainloop()
