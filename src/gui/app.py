import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.controllers import ApplicationController
from src.exceptions import IntegrationError


class ApplicationWindow:
    def __init__(self, root: tk.Tk, controller: ApplicationController):
        self.root, self.controller = root, controller
        self.protected = None
        self.path = tk.StringVar()
        self.lsb = tk.StringVar(value="1")
        self.output = tk.StringVar(value="Ready — teammate service adapters are required.")
        root.title("INF2005 — Protect and Verify (Skeleton)")
        frame = ttk.Frame(root, padding=20)
        frame.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="Image (PNG/BMP) or audio (PCM WAV)").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.path, width=65, state="readonly").grid(row=1, column=0, sticky="ew")
        ttk.Button(frame, text="Choose file", command=self.choose).grid(row=1, column=1)
        ttk.Label(frame, text="LSB bits (1–8)").grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Combobox(frame, textvariable=self.lsb, values=list(range(1, 9)),
                     state="readonly", width=8).grid(row=3, column=0, sticky="w")
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="w", pady=15)
        ttk.Button(buttons, text="Protect / encode", command=self.protect).pack(side="left")
        ttk.Button(buttons, text="Verify selected file", command=self.verify).pack(side="left")
        self.save_button = ttk.Button(buttons, text="Save stego file", command=self.save, state="disabled")
        self.save_button.pack(side="left")
        ttk.Label(frame, textvariable=self.output, wraplength=600, justify="left").grid(
            row=5, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Image comparison — awaiting image adapter and preview integration").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(20, 5))
        ttk.Button(frame, text="Audio playback — integration pending", state="disabled").grid(
            row=7, column=0, sticky="w")
        self.lsb.trace_add("write", self.invalidate)

    def invalidate(self, *_):
        self.protected = None
        self.save_button.configure(state="disabled")
        self.output.set("Selection changed. Run protect or verify.")

    def choose(self):
        path = filedialog.askopenfilename(filetypes=[("Supported media", "*.png *.bmp *.wav")])
        if path:
            self.path.set(path)
            self.invalidate()

    def protect(self):
        self.invalidate()
        try:
            self.protected = self.controller.protect(self.path.get(), int(self.lsb.get()))
            self.save_button.configure(state="normal")
            self.output.set("Protection complete. Save the stego file for Party B.")
        except IntegrationError as exc:
            self.output.set(str(exc))

    def verify(self):
        result = self.controller.verify(self.path.get(), int(self.lsb.get()))
        lines = [result.verdict.value, result.message]
        lines.extend(f"{stage.capitalize()}: {status}" for stage, status in result.statuses.items())
        self.output.set("\n".join(lines))

    def save(self):
        if self.protected is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=self.protected.suffix)
        if path:
            try:
                self.controller.save(self.protected, path)
                self.output.set("Saved. Select the saved stego file to verify it as Party B.")
            except IntegrationError as exc:
                messagebox.showerror("Save failed", str(exc))
