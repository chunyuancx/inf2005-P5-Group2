"""Isolated backend for browser regression tests; never used by the app launcher.

Uses the real controller, worker, HTTP bridge and reporting runner. Media service
implementations and native file-dialog selections are controlled test doubles.
"""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import random
from threading import Thread
import time
import tkinter as tk
from unittest.mock import patch

from src.controllers import ApplicationController
from src.gui.desktop import GlassDesktop, make_server
from tests.fakes import FakeCrypto, FakePayloadService, FakeSteganography, SelfCheckingStartLocation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    cover, stego, tampered, tiny = [folder / name for name in
                                  ("cover.png", "stego.png", "tampered.png", "tiny.png")]
    rng = random.Random(1234)
    cover.write_bytes(bytes(rng.randrange(256) for _ in range(5000)))
    tiny.write_bytes(b"tiny")
    calls, dialog_errors = [], []

    class Controller(ApplicationController):
        def protect(self, path, lsb):
            calls.append(["protect", Path(path).name, lsb])
            time.sleep(1.2)
            return super().protect(path, lsb)

        def verify(self, path, lsb):
            calls.append(["verify", Path(path).name, lsb])
            time.sleep(.4)
            return super().verify(path, lsb)

        def save(self, media, path):
            super().save(media, path)
            data = bytearray(media.data)
            for i in range(4000, 4100):
                data[i] ^= 0x80
            tampered.write_bytes(data)

    service = FakeSteganography()
    controller = Controller(service, service, FakeCrypto(), FakePayloadService(), SelfCheckingStartLocation())
    root = tk.Tk()
    desktop = GlassDesktop(root, controller)
    server, url = make_server(desktop)
    Thread(target=server.serve_forever, daemon=True).start()
    (folder / "ready.json").write_text(json.dumps({"url": url}), encoding="utf-8")
    with ExitStack() as stack:
        stack.enter_context(patch("src.gui.app.filedialog.askopenfilename",
                                  side_effect=["", str(cover), str(stego), str(tampered), str(tiny), str(cover), ""]))
        stack.enter_context(patch("src.gui.app.filedialog.asksaveasfilename",
                                  side_effect=["", str(stego), str(stego)]))
        stack.enter_context(patch("src.gui.app.filedialog.askdirectory",
                                  side_effect=["", str(folder / "reports"), str(folder / "reports")]))
        stack.enter_context(patch("src.gui.app.messagebox.showerror",
                                  side_effect=lambda *args: dialog_errors.append(args)))
        root.after(180000, lambda: desktop.action({"action": "close"}))
        try:
            root.mainloop()
        finally:
            server.shutdown()
            server.server_close()
            desktop.executor.shutdown(wait=True)
            (folder / "backend.json").write_text(json.dumps({"calls": calls, "dialog_errors": dialog_errors}), encoding="utf-8")


if __name__ == "__main__":
    main()
