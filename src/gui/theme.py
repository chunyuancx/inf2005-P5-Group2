"""Cosmic glass-inspired surfaces drawn with Tk's built-in canvas."""

import tkinter as tk
from tkinter import ttk

BACKDROP = "#cec1d9"
PANEL = "#23212c"
INSET = "#2d293b"
TEXT = "#f8f4ff"
MUTED = "#b4aabd"
ACCENT = "#dab0ef"


def rounded_rectangle(canvas, x1, y1, x2, y2, radius=24, **kwargs):
    return canvas.create_polygon(
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        smooth=True, splinesteps=24, **kwargs)


class GlassCard(tk.Frame):
    """Rounded surface with an inset content area and a fine glass rim."""

    def __init__(self, parent, title=None, **kwargs):
        super().__init__(parent, background=BACKDROP, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=BACKDROP)
        self.canvas.place(relwidth=1, relheight=1)
        self.content = ttk.Frame(self)
        self.content.pack(fill="both", expand=True, padx=20, pady=14)
        if title:
            ttk.Label(self.content, text=title, style="CardTitle.TLabel").pack(
                anchor="w", pady=(0, 8))
        self.canvas.bind("<Configure>", self._draw)

    def _draw(self, event):
        self.canvas.delete("all")
        rounded_rectangle(self.canvas, 2, 4, event.width - 1, event.height - 1,
                          fill="#b3a1c0", outline="")
        rounded_rectangle(self.canvas, 1, 1, event.width - 3, event.height - 4,
                          fill=PANEL, outline="#61536f", width=1)
        self.canvas.create_line(27, 2, event.width - 30, 2, fill="#82708e")


class CosmicHeader(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, height=130, highlightthickness=0, background=BACKDROP,
                         cursor="fleur")
        self.bind("<Configure>", self._draw)

    def _draw(self, event):
        self.delete("all")
        width = event.width
        rounded_rectangle(self, 1, 1, width - 2, 128, fill=PANEL, outline="#655570")
        center = width - 110
        for radius, color in ((82, "#373044"), (62, "#51405f"), (42, "#84649b")):
            self.create_oval(center - radius, 64 - radius * .55,
                             center + radius, 64 + radius * .55,
                             outline=color, width=1)
        self.create_oval(center - 8, 56, center + 8, 72, fill=ACCENT, outline="")
        for x, y, size in ((-72, 22, 2), (50, 81, 3), (83, 42, 2), (-24, 99, 1)):
            self.create_oval(center + x, y, center + x + size, y + size,
                             fill="#cab1e4", outline="")
        self.create_text(28, 25, anchor="nw", text="Media Integrity", fill=TEXT,
                         font=("Segoe UI", 29, "bold"))
        self.create_text(30, 77, anchor="nw",
                         text="Protect a file. Verify its integrity. Review the evidence.",
                         fill=MUTED, font=("Segoe UI", 11))
        self.create_text(30, 103, anchor="nw", text="Drag the header or a panel to move",
                         fill="#a392b2", font=("Segoe UI", 9))
