import tkinter as tk
import sys

from src.controllers import ApplicationController
from src.gui.app import ApplicationWindow
from src.gui.desktop import launch
from src.services import UnconfiguredService
from src.services.image_steganography import ImageSteganography


def main():
    controller = ApplicationController(
        image=ImageSteganography(),      # Member 1
        audio=UnconfiguredService(),     # Member 2
        crypto=UnconfiguredService(),    # Member 3
        payload=UnconfiguredService(),   # Member 3
        location=UnconfiguredService(),  # Member 4
    )
    root = tk.Tk()
    if "--native" in sys.argv:
        ApplicationWindow(root, controller)
        root.mainloop()
    else:
        launch(root, controller, open_window="--no-open" not in sys.argv)


if __name__ == "__main__":
    main()
