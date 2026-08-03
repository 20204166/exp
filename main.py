from window import Appwindow

def main() -> None:
    root = tk.Tk()
    app = Appwindow(root)
    app.run()


if __name__ == "__main__":
    main()
    