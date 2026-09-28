from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.controllers import ApplicationController
from src.attacks import ATTACKS, AttackContext, apply_attack, attacks_for
from src.exceptions import IntegrationError
from src.models import MediaType, Verdict
from src.testing.runner import AutomatedTestRunner
from src.testing.scenarios import DEFAULT_COVERS, MESSAGE, build_real_scenarios
from src.gui.theme import ACCENT, BACKDROP, INSET, MUTED, PANEL, TEXT, CosmicHeader, GlassCard


class ApplicationWindow:
    # Class-level defaults so partially constructed windows (tests) still work.
    preview_version = 0      # bumped whenever the preview panes must reload
    attack_preview_version = 0  # same, for the attack result's before/after panes
    verified_protected = False  # the protected copy passed its self-check; saving allowed
    scenarios = None         # callable(folder) -> scenarios for the test studio; real suite by default
    _progress = None         # (stages, current index) while verification runs
    _progress_dirty = False  # set from the worker thread, drained by the poll loop

    def _initialize_state(self, root, controller, runner=None, scenarios=None):
        """Shared workflow state for the native and glass desktop views."""
        self.root, self.controller = root, controller
        self.runner = runner or AutomatedTestRunner()
        self.scenarios = scenarios
        self.attack_choice = tk.StringVar()
        self.attack_output = tk.StringVar()
        # The test studio works on its own file with its own settings, so the
        # workspace selection and the attack lab never interfere.
        self.attack_path = tk.StringVar()
        self.attack_lsb = tk.StringVar(value="1")
        self.attack_passphrase = tk.StringVar()
        self.attack_start_mode = tk.StringVar(value="auto")
        self.attack_manual_start = tk.StringVar()
        self.attack_message = tk.StringVar()
        # Result of the last single attack, shown in the Attack result card.
        self.attack_verdict = tk.StringVar(value="Not attacked")
        self.attack_result = tk.StringVar()
        self.attack_decoded = tk.StringVar()
        self.attack_source = tk.StringVar()
        self.attack_copy = tk.StringVar()
        self.protected = None
        self.busy = False
        self._drag_offset = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.path = tk.StringVar()
        self.lsb = tk.StringVar(value="1")
        self.payload = tk.StringVar()
        self.passphrase = tk.StringVar()
        # "auto" derives the start from the passphrase; "manual" uses the typed
        # position. FR7 allows the user to select or derive the location.
        self.start_mode = tk.StringVar(value="auto")
        self.manual_start = tk.StringVar()
        self.output = tk.StringVar(value="Choose an original or stego file to begin.")
        self.decoded_payload = tk.StringVar(value="No decoded payload yet.")
        self.verdict = tk.StringVar(value="Not verified")
        self.test_output = tk.StringVar()
        self.test_summary = tk.StringVar(value="No test run yet")

    def __init__(self, root: tk.Tk, controller: ApplicationController,
                 runner: AutomatedTestRunner | None = None, scenarios=None):
        self._initialize_state(root, controller, runner, scenarios)
        root.title("Media Integrity | Protect & Verify")
        root.geometry("1140x940")
        root.minsize(940, 860)
        root.configure(background=BACKDROP)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._configure_styles()
        header = CosmicHeader(root)
        header.pack(fill="x", padx=24, pady=(20, 8))
        body = ttk.Frame(root, padding=(24, 0, 24, 14), style="Backdrop.TFrame")
        body.pack(fill="both", expand=True)
        self.tabs = ttk.Notebook(body)
        self.tabs.pack(fill="both", expand=True)
        workspace = ttk.Frame(self.tabs, padding=(0, 12, 0, 0), style="Backdrop.TFrame")
        testing_card = GlassCard(self.tabs)
        testing = testing_card.content
        self.tabs.add(workspace, text="  Protect & Verify  ")
        self.tabs.add(testing_card, text="  Automated Tests  ")
        self._build_workspace(workspace)
        self._build_testing(testing)
        ttk.Label(body, text="Media preview and playback are available in the glass desktop view.",
                  style="Footer.TLabel").pack(anchor="w", pady=(10, 0))
        self.lsb.trace_add("write", self.invalidate)
        self.payload.trace_add("write", self.invalidate)
        self.path.trace_add("write", self.invalidate)
        root.bind("<ButtonPress-1>", self._start_drag, add="+")
        root.bind("<B1-Motion>", self._drag_window, add="+")
        root.bind("<ButtonRelease-1>", self._stop_drag, add="+")

    def _start_drag(self, event):
        self._drag_offset = None
        # Interactive controls retain normal selection and click behavior.
        if event.widget.winfo_class() not in {"Canvas", "Frame", "TFrame", "Label", "TLabel"}:
            return
        if self.root.state() != "normal":
            return
        self._drag_offset = (event.x_root - self.root.winfo_x(),
                             event.y_root - self.root.winfo_y())

    def _drag_window(self, event):
        if self._drag_offset is not None:
            x = event.x_root - self._drag_offset[0]
            y = event.y_root - self._drag_offset[1]
            # Position only: preserve loaded media, widgets and pending callbacks.
            self.root.geometry(f"+{x}+{y}")

    def _stop_drag(self, _event):
        self._drag_offset = None

    @staticmethod
    def _workspace_card(parent, title, **layout):
        card = GlassCard(parent, title)
        card.grid(**layout)
        content = ttk.Frame(card.content)
        content.pack(fill="both", expand=True)
        return content

    def _build_workspace(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(2, weight=1)
        source = self._workspace_card(parent, "01 / SOURCE FILE", row=0, column=0,
                                      columnspan=2, sticky="ew", pady=(0, 12))
        source.columnconfigure(0, weight=1)
        ttk.Label(source, text="Original file → Protect    •    Received stego file → Verify",
                  style="Muted.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Entry(source, textvariable=self.path, state="readonly").grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.browse_button = ttk.Button(source, text="Choose file…", command=self.choose)
        self.browse_button.grid(row=1, column=1)
        ttk.Label(source, text="PNG / BMP images  ·  PCM WAV audio", style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 0))
        actions = self._workspace_card(parent, "02 / PROTECT & VERIFY", row=1,
                                      column=0, sticky="nsew", padx=(0, 12), pady=(0, 12))
        settings = ttk.Frame(actions)
        settings.pack(fill="x", pady=(0, 10))
        ttk.Label(settings, text="LSB depth", style="Heading.TLabel").pack(side="left", padx=(0, 12))
        self.lsb_box = ttk.Combobox(settings, textvariable=self.lsb, values=list(range(1, 9)), state="readonly", width=4)
        self.lsb_box.pack(side="left")
        ttk.Label(settings, text="bits (1 to 8)", style="Muted.TLabel").pack(side="left", padx=8)
        secret = ttk.Frame(actions)
        secret.pack(fill="x", pady=(10, 0))
        ttk.Label(secret, text="Passphrase", style="Heading.TLabel").pack(side="left", padx=(0, 12))
        self.passphrase_box = ttk.Entry(secret, textvariable=self.passphrase, show="•")
        self.passphrase_box.pack(side="left", fill="x", expand=True)
        payload = ttk.Frame(actions)
        payload.pack(fill="x", pady=(10, 0))
        ttk.Label(payload, text="Payload", style="Heading.TLabel").pack(side="left", padx=(0, 12))
        self.payload_box = ttk.Entry(payload, textvariable=self.payload)
        self.payload_box.pack(side="left", fill="x", expand=True)
        manual = ttk.Frame(actions)
        manual.pack(fill="x", pady=(10, 0))
        self.mode_box = ttk.Checkbutton(manual, text="Choose start position manually",
                                        variable=self.start_mode,
                                        onvalue="manual", offvalue="auto")
        self.mode_box.pack(side="left", padx=(0, 12))
        self.manual_box = ttk.Entry(manual, textvariable=self.manual_start, width=12)
        self.manual_box.pack(side="left")
        ttk.Label(actions, text="Automatic derives the position from your passphrase, so it differs for every file.\n"
                                "Manual uses the position you type, which is not protected by the passphrase.\n"
                                "Party B needs the same depth, and whichever of the two you used.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(6, 12))
        self.protect_button = ttk.Button(actions, text="Protect / encode", style="Primary.TButton", command=self.protect)
        self.protect_button.pack(fill="x")
        preview = self._workspace_card(parent, "MEDIA PREVIEW", row=1, column=1,
                                      sticky="nsew", pady=(0, 12))
        ttk.Label(preview, text="Original and stego", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(preview, text="Side-by-side image comparison, the changed-bits map and audio "
                                "playback are shown in the glass desktop. Launch it with "
                                "python -m src (without --native).",
                  style="Muted.TLabel", wraplength=290, justify="left").pack(anchor="w", pady=(8, 12))
        result = self._workspace_card(parent, "03 / VERIFICATION RESULT", row=2,
                                     column=0, columnspan=2, sticky="nsew")
        ttk.Label(result, textvariable=self.verdict, style="Verdict.TLabel").pack(anchor="w")
        ttk.Label(result, textvariable=self.output, wraplength=820, justify="left").pack(anchor="w", pady=(6, 10))
        ttk.Label(result, text="Decoded payload", style="Heading.TLabel").pack(anchor="w", pady=(4, 2))
        ttk.Label(result, textvariable=self.decoded_payload, wraplength=820, justify="left").pack(anchor="w", pady=(0, 10))
        row = ttk.Frame(result)
        row.pack(fill="x", pady=(0, 10))
        self.verify_button = ttk.Button(row, text="Verify", command=self.verify)
        self.verify_button.pack(side="left")
        self.save_button = ttk.Button(row, text="Save stego file", command=self.save, state="disabled")
        self.save_button.pack(side="left", padx=(8, 0))
        self.statuses_table = self._table(result, (("stage", "Verification stage", 240), ("status", "Status", 540)), height=4)

    def _build_testing(self, parent):
        ttk.Label(parent, text="Attack lab", style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text="Apply an attack to the selected stego file. The attacked copy is saved next to it and verified.",
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 10))
        pick = ttk.Frame(parent)
        pick.pack(fill="x", pady=(0, 6))
        self.attack_browse_button = ttk.Button(pick, text="Choose file…", command=self.choose_attack)
        self.attack_browse_button.pack(side="left")
        ttk.Label(pick, textvariable=self.attack_path, style="Muted.TLabel").pack(side="left", padx=10)
        settings = ttk.Frame(parent)
        settings.pack(fill="x", pady=(0, 6))
        ttk.Label(settings, text="LSB", style="Heading.TLabel").pack(side="left", padx=(0, 6))
        self.attack_lsb_box = ttk.Combobox(settings, textvariable=self.attack_lsb, values=list(range(1, 9)), state="readonly", width=3)
        self.attack_lsb_box.pack(side="left")
        ttk.Label(settings, text="Passphrase", style="Heading.TLabel").pack(side="left", padx=(12, 6))
        self.attack_passphrase_box = ttk.Entry(settings, textvariable=self.attack_passphrase, show="•", width=22)
        self.attack_passphrase_box.pack(side="left")
        self.attack_mode_box = ttk.Checkbutton(settings, text="Manual start", variable=self.attack_start_mode,
                                               onvalue="manual", offvalue="auto")
        self.attack_mode_box.pack(side="left", padx=(12, 6))
        self.attack_manual_box = ttk.Entry(settings, textvariable=self.attack_manual_start, width=8)
        self.attack_manual_box.pack(side="left")
        message = ttk.Frame(parent)
        message.pack(fill="x", pady=(0, 6))
        ttk.Label(message, text="Hidden message for the suite", style="Heading.TLabel").pack(side="left", padx=(0, 8))
        self.attack_message_box = ttk.Entry(message, textvariable=self.attack_message)
        self.attack_message_box.pack(side="left", fill="x", expand=True)
        lab = ttk.Frame(parent)
        lab.pack(fill="x", pady=(0, 6))
        self.attack_box = ttk.Combobox(lab, textvariable=self.attack_choice, state="readonly", width=34,
                                       values=[attack.label for attack in ATTACKS.values()])
        self.attack_box.pack(side="left")
        self.attack_button = ttk.Button(lab, text="Run attack", command=self.attack)
        self.attack_button.pack(side="left", padx=(8, 0))
        ttk.Label(parent, textvariable=self.attack_output, wraplength=820, justify="left").pack(anchor="w", pady=(0, 8))
        ttk.Label(parent, textvariable=self.attack_verdict, style="Verdict.TLabel").pack(anchor="w")
        ttk.Label(parent, textvariable=self.attack_result, wraplength=820, justify="left").pack(anchor="w", pady=(4, 6))
        self.attack_statuses_table = self._table(parent, (("stage", "Verification stage", 240), ("status", "Status", 540)), height=4)
        self.attack_statuses_table.tag_configure("done", foreground="#8fe0c3")
        self.attack_statuses_table.tag_configure("running", foreground="#e8c5ff")
        self.attack_statuses_table.tag_configure("pending", foreground="#8d7f9c")
        ttk.Label(parent, textvariable=self.attack_copy, style="Muted.TLabel", wraplength=820).pack(anchor="w", pady=(4, 14))
        ttk.Label(parent, text="Automated attack suite", style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text="Protects the bundled samples and your selected file, runs every attack and verifier case\nin both start modes, and writes JSON, log and Markdown evidence.", justify="left").pack(anchor="w", pady=(6, 10))
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(0, 14))
        self.test_button = ttk.Button(toolbar, text="Run attack suite…", style="Primary.TButton", command=self.run_tests)
        self.test_button.pack(side="left")
        ttk.Label(toolbar, textvariable=self.test_summary, style="Heading.TLabel").pack(side="left", padx=18)
        self.results_table = self._table(parent, (("case", "Scenario", 300), ("expected", "Expected", 130), ("actual", "Actual", 130), ("result", "Result", 60), ("note", "Note", 320)), height=9)
        self.results_table.tag_configure("pass", foreground="#8fe0c3")
        self.results_table.tag_configure("fail", foreground="#ff9aaf")
        self.statuses_table.tag_configure("done", foreground="#8fe0c3")
        self.statuses_table.tag_configure("running", foreground="#e8c5ff")
        self.statuses_table.tag_configure("pending", foreground="#8d7f9c")
        evidence = ttk.LabelFrame(parent, text="Test evidence", padding=12)
        evidence.pack(fill="x", pady=(12, 0))
        ttk.Label(evidence, textvariable=self.test_output, wraplength=820, justify="left").pack(anchor="w")

    @staticmethod
    def _table(parent, columns, height):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        table = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height)
        for key, title, width in columns:
            table.heading(key, text=title)
            table.column(key, width=width, minwidth=80)
        vertical = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=table.xview)
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        return table

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=PANEL, foreground=TEXT,
                        bordercolor="#51465f", lightcolor="#51465f", darkcolor=PANEL,
                        troughcolor=PANEL, selectbackground="#65507d", selectforeground=TEXT)
        style.configure("Backdrop.TFrame", background=BACKDROP)
        style.configure("Muted.TLabel", foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Footer.TLabel", foreground="#51415e", background=BACKDROP,
                        font=("Segoe UI", 9))
        style.configure("Heading.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("CardTitle.TLabel", foreground=ACCENT, font=("Segoe UI", 9, "bold"))
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
        style.configure("Verdict.TLabel", foreground=ACCENT, font=("Segoe UI", 23))
        style.configure("TLabelframe", bordercolor="#51465f", relief="solid")
        style.configure("TLabelframe.Label", foreground=ACCENT, font=("Segoe UI", 10, "bold"))
        style.configure("TButton", padding=(14, 7), background=INSET, borderwidth=1,
                        focusthickness=1, focuscolor=ACCENT)
        style.map("TButton", background=[("disabled", "#292633"), ("pressed", "#51425f"),
                                        ("active", "#42364f")],
                  foreground=[("disabled", "#8c8099")])
        style.configure("Primary.TButton", background=ACCENT, foreground=PANEL)
        style.map("Primary.TButton", background=[("disabled", "#3b3249"),
                  ("pressed", "#bc8bd8"), ("active", "#ecc7fc")],
                  foreground=[("disabled", "#9c8bab"), ("!disabled", PANEL)])
        for name in ("TEntry", "TCombobox"):
            style.configure(name, fieldbackground=INSET, foreground=TEXT, padding=7,
                            arrowcolor=ACCENT, insertcolor=TEXT)
            style.map(name, fieldbackground=[("readonly", INSET), ("disabled", PANEL)],
                      foreground=[("disabled", "#8c8099"), ("readonly", TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", INSET)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#65507d")
        style.configure("TNotebook", background=BACKDROP, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", padding=(18, 10), background="#b9a8c8", foreground="#493a56")
        style.map("TNotebook.Tab", background=[("selected", PANEL), ("active", "#e3d3ed")],
                  foreground=[("selected", TEXT)])
        style.configure("Treeview", rowheight=26, fieldbackground=INSET, background=INSET,
                        foreground=TEXT, borderwidth=0)
        style.map("Treeview", background=[("selected", "#65507d")], foreground=[("selected", TEXT)])
        style.configure("Treeview.Heading", background="#363044", foreground=ACCENT,
                        font=("Segoe UI", 9, "bold"), padding=8, relief="flat")
        style.map("Treeview.Heading", background=[("active", "#443751")])
        style.configure("TScrollbar", background="#51425f", arrowcolor=MUTED,
                        borderwidth=0, troughcolor=PANEL)
        style.map("TScrollbar", background=[("active", "#756087")])
        style.configure("TSeparator", background="#51465f")

    @staticmethod
    def _clear_table(table):
        for item in table.get_children():
            table.delete(item)

    def invalidate(self, *_):
        self.protected = None
        self.verified_protected = False
        self.preview_version += 1
        self.save_button.configure(state="disabled")
        self.verdict.set("Not verified")
        if hasattr(self, "decoded_payload"):
            self.decoded_payload.set("No decoded payload yet.")
        self._clear_table(self.statuses_table)
        self.output.set("Selection changed. Run protect or verify.")

    def _dialog(self, opener, **options):
        """Open a native dialog centred on screen and above the app window.

        The glass view keeps the Tk root withdrawn, and a dialog owned by a
        hidden window can open behind the maximised browser window. A 1x1
        topmost anchor gives Windows a visible owner to centre on and raise.
        """
        anchor = None
        if isinstance(self.root, tk.Misc):
            try:
                anchor = tk.Toplevel(self.root)
                anchor.overrideredirect(True)
                anchor.attributes("-topmost", True)
                width, height = anchor.winfo_screenwidth(), anchor.winfo_screenheight()
                anchor.geometry(f"1x1+{width // 2}+{height // 2}")
                anchor.update()
                options["parent"] = anchor
            except tk.TclError:
                anchor = None
        try:
            return opener(**options)
        finally:
            if anchor is not None:
                anchor.destroy()

    def choose(self):
        path = self._dialog(filedialog.askopenfilename, title="Choose a media file",
                            filetypes=[("Supported media", "*.png *.bmp *.wav")])
        if path:
            self.path.set(path)

    def _apply_start_location(self, mode=None, manual=None, passphrase=None):
        """Configure the start-location service from the GUI controls.

        Defaults to the workspace controls; the attack lab passes its own.
        Skipped when the configured locator takes neither, so other locator
        designs and test doubles keep working unchanged.  The controller and
        the verification engine share one locator instance, so setting it here
        covers protect, verify and the attack lab alike.
        """
        locator = getattr(self.controller, "location", None)
        if not hasattr(type(locator), "key"):
            return
        mode = self.start_mode.get() if mode is None else mode
        manual = self.manual_start.get() if manual is None else manual
        passphrase = self.passphrase.get() if passphrase is None else passphrase
        if mode == "manual":
            typed = manual.strip()
            if not typed:
                raise IntegrationError(
                    "Enter a start position, or untick manual to derive one.")
            try:
                position = int(typed)
            except ValueError as exc:
                raise IntegrationError("Start position must be a whole number.") from exc
            locator.manual_start = position
            return
        locator.manual_start = None
        if not passphrase:
            raise IntegrationError("Enter the start-location passphrase.")
        locator.key = passphrase

    def _attack_inputs(self, require_location=True):
        """The attack lab's own file, depth and start-location settings."""
        path = self.attack_path.get()
        if not path:
            raise IntegrationError("Choose a file for the attack lab first.")
        try:
            depth = int(self.attack_lsb.get())
        except ValueError as exc:
            raise IntegrationError("Choose an LSB depth from 1 to 8.") from exc
        if not 1 <= depth <= 8:
            raise IntegrationError("Choose an LSB depth from 1 to 8.")
        try:
            self._apply_start_location(self.attack_start_mode.get(), self.attack_manual_start.get(),
                                       self.attack_passphrase.get())
        except IntegrationError:
            if require_location:
                raise
        return path, depth

    def _inputs(self, require_location=True):
        """Selected path and LSB depth, with the start-location service configured.

        ``require_location=False`` lets a media-level attack proceed without a
        passphrase or position; the verification that follows will ask for it.
        """
        if not self.path.get():
            raise IntegrationError("Choose an image or audio file first.")
        try:
            depth = int(self.lsb.get())
        except ValueError as exc:
            raise IntegrationError("Choose an LSB depth from 1 to 8.") from exc
        if not 1 <= depth <= 8:
            raise IntegrationError("Choose an LSB depth from 1 to 8.")
        try:
            self._apply_start_location()
        except IntegrationError:
            if require_location:
                raise
        return self.path.get(), depth

    def _set_busy(self, busy):
        self.busy = busy
        for button in (self.browse_button, self.protect_button, self.verify_button, self.test_button,
                       self.attack_button, self.attack_browse_button):
            button.configure(state="disabled" if busy else "normal")
        for box in (self.attack_box, self.lsb_box, self.attack_lsb_box):
            box.configure(state="disabled" if busy else "readonly")
        for box in (self.passphrase_box, getattr(self, "payload_box", None), self.manual_box, self.mode_box,
                    self.attack_passphrase_box, self.attack_mode_box, self.attack_manual_box, self.attack_message_box):
            if box is None:
                continue
            box.configure(state="disabled" if busy else "normal")
        ready = self.protected is not None and self.verified_protected
        self.save_button.configure(state="normal" if not busy and ready else "disabled")

    def _submit(self, work, success, failure):
        if self.busy:
            return
        self._set_busy(True)
        future = self.executor.submit(work)

        def poll():
            if self._progress_dirty:
                self._progress_dirty = False
                self._draw_progress()
            if not future.done():
                self.root.after(50, poll)
                return
            self._set_busy(False)
            try:
                result = future.result()
            except Exception as exc:
                failure(exc)
            else:
                success(result)
        self.root.after(50, poll)

    def protect(self):
        if self.busy:
            return
        self.invalidate()
        try:
            path, depth = self._inputs()
        except IntegrationError as exc:
            self.output.set(str(exc))
            return
        self.output.set("Protecting selected file…")

        def complete(media):
            self.protected = media
            self.verified_protected = False
            self.preview_version += 1
            self.save_button.configure(state="disabled")
            self.output.set("Protection complete. Verify the protected copy to check it, then save it.")
        payload = getattr(self, "payload", None)
        payload_text = payload.get() if payload is not None else ""
        if payload_text:
            work = lambda: self.controller.protect(path, depth, payload_text)
        else:
            work = lambda: self.controller.protect(path, depth)
        self._submit(work, complete,
                     lambda exc: self.output.set(str(exc)))

    def verify(self):
        """Self-check a freshly protected copy, or verify the selected file.

        While an unsaved protected copy exists, Verify checks that copy so the
        user can confirm it before saving (Party A). Otherwise it verifies the
        file chosen on disk (Party B).
        """
        if self.busy:
            return
        self.verified_protected = False
        self.save_button.configure(state="disabled")
        self.verdict.set("Not verified")
        if hasattr(self, "decoded_payload"):
            self.decoded_payload.set("No decoded payload yet.")
        self._clear_table(self.statuses_table)
        try:
            path, depth = self._inputs()
        except IntegrationError as exc:
            self._verification_error(exc)
            return
        finish = self._watch_stages()
        media = self.protected
        if media is not None:
            self.output.set("Checking the protected copy…")
            self._submit(lambda: self.controller.verify_media(media, depth),
                         finish(self._show_self_check), finish(self._verification_error))
            return
        self.output.set("Verifying selected file…")
        self._submit(lambda: self.controller.verify(path, depth),
                     finish(self.show_result), finish(self._verification_error))

    def _show_self_check(self, result):
        self.show_result(result)
        self.verified_protected = result.verdict is Verdict.AUTHENTIC
        if self.verified_protected:
            self.save_button.configure(state="normal")
            self.output.set(f"Self-check passed. {result.message} Save the stego file to share with Party B.")
        else:
            self.output.set(f"Self-check failed. {result.message}")

    # ------------------------------------------------------------ live stages

    def _watch_stages(self, table=None):
        """Show each verification stage as it starts.

        The engine calls ``on_stage`` from the worker thread, so the callback
        only records the stage; the poll loop redraws on the Tk thread. The
        engine stops at the first failure, so every stage before the current
        one is known to have passed. Returns a wrapper that detaches the
        observer once the result (or error) arrives.
        """
        engine = getattr(self.controller, "engine", None)
        stages = tuple(getattr(type(engine), "STAGES", ()))
        if not stages or not hasattr(engine, "on_stage"):
            return lambda handler: handler
        table = table if table is not None else self.statuses_table
        self._progress = (stages, 0, table)
        self._draw_progress()

        def started(stage):
            self._progress = (stages, stages.index(stage) if stage in stages else 0, table)
            self._progress_dirty = True
        engine.on_stage = started

        def finish(handler):
            def wrapped(value):
                engine.on_stage = None
                self._progress = None
                handler(value)
            return wrapped
        return finish

    def _draw_progress(self):
        if self._progress is None:
            return
        stages, current, table = self._progress
        self._clear_table(table)
        for index, stage in enumerate(stages):
            if index < current:
                status, tag = "Passed", "done"
            elif index == current:
                status, tag = "Checking…", "running"
            else:
                status, tag = "Waiting", "pending"
            table.insert("", "end", values=(stage.capitalize(), status), tags=(tag,))

    def _verification_error(self, exc):
        self.verdict.set("Cannot Verify")
        self.output.set(str(exc))
        self._clear_table(self.statuses_table)

    def show_result(self, result):
        self.verdict.set(result.verdict.value)
        self.output.set(result.message)
        decoded = getattr(result, "decoded_payload", None)
        if hasattr(self, "decoded_payload"):
            self.decoded_payload.set(decoded if decoded else "No decoded payload found.")
        self._clear_table(self.statuses_table)
        for stage, status in result.statuses.items():
            self.statuses_table.insert("", "end", values=(stage.capitalize(), status))

    # ------------------------------------------------------------- attack lab

    def choose_attack(self):
        path = self._dialog(filedialog.askopenfilename, title="Choose a file to attack",
                            filetypes=[("Supported media", "*.png *.bmp *.wav")])
        if path:
            self.attack_path.set(path)
            self.attack_output.set("")

    def attack(self, attack_id=None):
        """Attack the studio's file, save the copy beside it and verify it."""
        if self.busy:
            return
        if attack_id is None:
            attack_id = next((a.id for a in ATTACKS.values() if a.label == self.attack_choice.get()), None)
        attack = ATTACKS.get(attack_id)
        if attack is None:
            self.attack_output.set("Choose an attack first.")
            return
        try:
            # Only payload-level attacks need the start location up front.
            path, depth = self._attack_inputs(require_location=attack.targets_payload)
        except IntegrationError as exc:
            self.attack_output.set(str(exc))
            return
        self.attack_output.set(f"Applying '{attack.label}'…")
        self.attack_verdict.set("Attacking…")
        self.attack_result.set(f"Applying '{attack.label}' and saving the attacked copy.")
        self.attack_decoded.set("")
        self.attack_source.set(path)
        self.attack_copy.set("")
        self._clear_table(self.attack_statuses_table)
        # Read the Tk variables here; the worker thread must not touch them.
        where = (f"manual position {self.attack_manual_start.get().strip() or '?'}"
                 if self.attack_start_mode.get() == "manual" else "the position derived from your passphrase")

        def work():
            media = self.controller.load(path)
            context = AttackContext(lsb=depth, seed=depth)
            if attack.targets_payload:
                context = AttackContext(lsb=depth, start=self.controller.location.recover(media, depth),
                                        service=self.controller.service_for(media), seed=depth)
            try:
                attacked = apply_attack(attack.id, media, context)
            except IntegrationError as exc:
                if not attack.targets_payload:
                    raise
                found = self._payload_depths(media, depth)
                positions = [] if found else self._envelope_positions(media, depth)
                if found:
                    hint = (f" With these same settings a payload IS found at LSB depth {found[0]}: "
                            f"set the lab depth to {found[0]}.")
                elif positions:
                    hint = (f" At LSB depth {depth} a payload sits at position {positions[0]:,}: "
                            f"set the lab to Manual with position {positions[0]:,}.")
                else:
                    hint = (" Choose the saved stego copy (not the original or an already attacked copy) and "
                            "use exactly the depth, mode and passphrase or position it was protected with.")
                raise IntegrationError(
                    f"{exc} This attack rewrites the hidden payload, so the lab must find it first: "
                    f"it looked at LSB depth {depth}, {where}.{hint}") from exc
            source = Path(path)
            # Each source file gets its own folder under "attacks", and every
            # attacked copy is named by the date and time it was made.
            if source.parent.parent.name == "attacks":
                folder = source.parent  # attacking an attacked copy: stay in its folder
            else:
                folder = source.parent / "attacks" / source.stem
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            target = folder / f"{stamp}_{attack.id}{attacked.suffix}"
            counter = 1
            while target.exists():
                counter += 1
                target = folder / f"{stamp}_{attack.id}-{counter}{attacked.suffix}"
            self.controller.save(attacked, str(target))
            return target

        def done(target):
            # The studio keeps the file you chose, so the next attack starts clean again.
            self.attack_copy.set(str(target))
            self.attack_preview_version += 1
            self.attack_output.set(f"Saved attacked copy: {target}\nVerifying it…")
            self._verify_attacked(attack, target, depth)

        def failed(exc):
            self.attack_verdict.set("Attack failed")
            self.attack_result.set(str(exc))
            self.attack_output.set(f"Attack failed: {exc}")

        self._submit(work, done, failed)

    def _payload_depths(self, media, skip_depth):
        """Other LSB depths at which the studio's settings do find an envelope.

        A wrong depth is the commonest reason a payload attack cannot find the
        envelope, so the lab checks the other depths and names the right one.
        """
        found = []
        for other in range(1, 9):
            if other == skip_depth:
                continue
            try:
                start = self.controller.location.recover(media, other)
                self.controller.service_for(media).extract(media, other, start)
                found.append(other)
            except Exception:
                continue
        return found

    @staticmethod
    def _envelope_positions(media, depth):
        """Where envelopes really sit at this depth, for the lab's hints (worker thread)."""
        try:
            from src.gui.diagnostics import find_envelopes
            return [start for start, _ in find_envelopes(media, depth)]
        except Exception:
            return []

    def _verify_attacked(self, attack, target, depth):
        """Verify an attacked copy with the studio's settings, as Party B would."""
        label = attack.label

        def cannot(exc):
            self.attack_verdict.set("Cannot Verify")
            self.attack_result.set(str(exc))
            self.attack_output.set(f"{label}: Cannot Verify. {exc}")

        try:
            self._attack_inputs()
        except IntegrationError as exc:
            cannot(exc)
            return
        self.attack_verdict.set("Verifying…")
        self.attack_result.set("Checking the attacked copy the way Party B would.")
        manual = self.attack_start_mode.get() == "manual"
        typed = self.attack_manual_start.get().strip()

        def work():
            result = self.controller.verify(str(target), depth)
            hint = ""
            if result.verdict is Verdict.PAYLOAD_MISSING and not attack.targets_payload:
                if manual:
                    # A media-level attack leaves the payload where it was, so a missing
                    # payload in manual mode almost always means a wrong position.
                    positions = self._envelope_positions(self.controller.load(str(target)), depth)
                    if positions and str(positions[0]) != typed:
                        hint = (f" The payload actually sits at position {positions[0]:,}, not {typed or '?'}: "
                                f"set the lab position to {positions[0]:,} and run the attack again.")
                else:
                    hint = (" Why not Tampered: in Automatic mode the start position is derived from the "
                            "file content, so any edit moves it and the payload cannot be found "
                            "(verification docs, section 7). Use Manual with the position the file was "
                            "protected at to see Tampered.")
            return result, hint

        def show(outcome):
            result, hint = outcome
            self.attack_verdict.set(result.verdict.value)
            self.attack_result.set(result.message + hint)
            self.attack_decoded.set(getattr(result, "decoded_payload", None) or "")
            self._clear_table(self.attack_statuses_table)
            for stage, status in result.statuses.items():
                self.attack_statuses_table.insert("", "end", values=(stage.capitalize(), status))
            self.attack_output.set(f"{label}: {result.verdict.value}.")

        finish = self._watch_stages(self.attack_statuses_table)
        self._submit(work, finish(show), finish(cannot))

    def run_tests(self):
        if self.busy:
            return
        destination = self._dialog(filedialog.askdirectory, title="Choose test evidence folder")
        if not destination:
            return
        self._clear_table(self.results_table)
        self.test_summary.set("Running…")
        self.test_output.set(f"Evidence folder: {destination}\nProtecting, attacking and verifying every scenario…")
        builder = self.scenarios or self._real_scenarios
        self._submit(lambda: self.runner.run(builder(destination), destination),
                     self._show_report, self._test_error)

    def _real_scenarios(self, folder):
        covers = list(DEFAULT_COVERS)
        selected = self.attack_path.get()
        if selected and Path(selected).suffix.lower() in {".png", ".bmp", ".wav"} and Path(selected).is_file():
            covers.append(Path(selected))
        # The studio's file may itself be a stego file, so only the bundled
        # samples are treated as known-clean covers.
        message = self.attack_message.get().strip() or MESSAGE
        return build_real_scenarios(folder, covers=covers, clean_covers=DEFAULT_COVERS, message=message)

    def _show_report(self, report):
        for row in report["results"]:
            self.results_table.insert("", "end", values=(row["name"], row["expected"],
                row["actual"] or "Execution error", "PASS" if row["passed"] else "FAIL", row.get("note", "")),
                tags=("pass" if row["passed"] else "fail",))
        self.test_summary.set(f"{report['passed']}/{report['total']} passed · {report['failed']} failed")
        self.test_output.set(f"Evidence saved to {report['evidence_dir']}\nresults.json, results.log and results.md")

    def _test_error(self, exc):
        self.test_summary.set("Run failed")
        self.test_output.set(f"Cannot complete the attack suite: {exc}")

    def save(self):
        if self.busy or self.protected is None:
            return
        path = self._dialog(filedialog.asksaveasfilename, title="Save stego file",
            defaultextension=self.protected.suffix,
            initialfile=f"{Path(self.path.get()).stem}_stego{self.protected.suffix}",
            filetypes=[("Stego media", f"*{self.protected.suffix}")])
        if path:
            media = self.protected
            self._submit(lambda: self.controller.save(media, path),
                lambda _: self.output.set(f"Saved: {path}\nSelect this stego file to verify it as Party B."),
                self._save_error)

    def _save_error(self, exc):
        self.output.set(f"Save failed: {exc}")
        messagebox.showerror("Save failed", str(exc))

    def close(self):
        if self.busy:
            messagebox.showinfo("Operation in progress", "Wait for the current operation to finish before closing.")
            return
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()
