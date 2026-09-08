import tkinter as tk

from src.controllers import ApplicationController
from src.gui.app import ApplicationWindow
from src.services import UnconfiguredService


def main():
    controller = ApplicationController(*(UnconfiguredService() for _ in range(5)))
    root = tk.Tk()
    ApplicationWindow(root, controller)
    root.mainloop()


if __name__ == "__main__":
    main()
