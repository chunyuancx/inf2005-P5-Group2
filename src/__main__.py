import tkinter as tk
import sys

from src.controllers import ApplicationController
from src.gui.app import ApplicationWindow
from src.gui.desktop import launch
from src.services import UnconfiguredService
from src.services.audio_steganography import WavSteganographyService
from src.services.image_steganography import ImageSteganography
from src.services.start_location import KeyedStartLocation


def main():
    controller = ApplicationController(
        image=ImageSteganography(),      # Member 1
        audio=WavSteganographyService(),  # Member 2
        crypto=UnconfiguredService(),     # Member 3
        payload=UnconfiguredService(),    # Member 3
        location=KeyedStartLocation(),    # Member 4 - passphrase set from the GUI
    )
    root = tk.Tk()
    if "--native" in sys.argv:
        ApplicationWindow(root, controller)
        root.mainloop()
    else:
        launch(root, controller, open_window="--no-open" not in sys.argv)


if __name__ == "__main__":
    main()
