import tkinter as tk
import sys

from src.controllers import ApplicationController
from src.gui.app import ApplicationWindow
from src.gui.desktop import launch
from src.services import UnconfiguredService


def main():
    controller = ApplicationController(*(UnconfiguredService() for _ in range(5)))
    root = tk.Tk()
    if "--native" in sys.argv:
        ApplicationWindow(root, controller)
        root.mainloop()
    else:
        launch(root, controller, open_window="--no-open" not in sys.argv)


if __name__ == "__main__":
    main()
