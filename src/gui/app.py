from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.controllers import ApplicationController
from src.exceptions import IntegrationError
from src.testing.demo_scenarios import build_demo_scenarios
from src.testing.runner import AutomatedTestRunner
from src.gui.theme import ACCENT, BACKDROP, INSET, MUTED, PANEL, TEXT, CosmicHeader, GlassCard


class ApplicationWindow:
    def _initialize_state(self, root, controller, runner=None):
        """Shared workflow state for the native and glass desktop views."""
        self.root, self.controller = root, controller
        self.runner = runner or AutomatedTestRunner()
        self.protected = None
        self.busy = False
        self._drag_offset = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.path = tk.StringVar()
        self.lsb = tk.StringVar(value="1")
        self.output = tk.StringVar(value="Choose an original or stego file to begin.")
        self.verdict = tk.StringVar(value="Not verified")
        self.test_output = tk.StringVar(value="Run the reporting demo to generate a new evidence folder.")
        self.test_summary = tk.StringVar(value="No test run yet")

    def __init__(self, root: tk.Tk, controller: ApplicationController,
                 runner: AutomatedTestRunner | None = None):
        self._initialize_state(root, controller, runner)
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
        ttk.Label(body, text="Media preview and playback will be available when media adapters are connected.",
                  style="Footer.TLabel").pack(anchor="w", pady=(10, 0))
        self.lsb.trace_add("write", self.invalidate)
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
        ttk.Label(settings, text="bits (1–8)", style="Muted.TLabel").pack(side="left", padx=8)
        ttk.Label(actions, text="Use the same depth for encoding and verification.", style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
        buttons = ttk.Frame(actions)
        buttons.pack(fill="x")
        buttons.columnconfigure((0, 1), weight=1)
        self.protect_button = ttk.Button(buttons, text="Protect / encode", style="Primary.TButton", command=self.protect)
        self.protect_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.verify_button = ttk.Button(buttons, text="Verify file", command=self.verify)
        self.verify_button.grid(row=0, column=1, sticky="ew")
        self.save_button = ttk.Button(actions, text="Save stego file…", command=self.save, state="disabled")
        self.save_button.pack(fill="x", pady=(8, 0))
        preview = self._workspace_card(parent, "MEDIA PREVIEW", row=1, column=1,
                                      sticky="nsew", pady=(0, 12))
        ttk.Label(preview, text="Original  →  Stego", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(preview, text="Image comparison is awaiting integration.", style="Muted.TLabel", wraplength=290).pack(anchor="w", pady=(8, 12))
        ttk.Separator(preview).pack(fill="x", pady=(0, 10))
        ttk.Label(preview, text="Audio playback", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        play = ttk.Frame(preview)
        play.pack(fill="x")
        ttk.Button(play, text="Play original", state="disabled").pack(side="left", padx=(0, 8))
        ttk.Button(play, text="Play stego", state="disabled").pack(side="left")
        result = self._workspace_card(parent, "03 / VERIFICATION RESULT", row=2,
                                     column=0, columnspan=2, sticky="nsew")
        ttk.Label(result, textvariable=self.verdict, style="Verdict.TLabel").pack(anchor="w")
        ttk.Label(result, textvariable=self.output, wraplength=820, justify="left").pack(anchor="w", pady=(6, 10))
        self.statuses_table = self._table(result, (("stage", "Verification stage", 240), ("status", "Status", 540)), height=4)

    def _build_testing(self, parent):
        ttk.Label(parent, text="Automated test runner", style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text="REPORTING DEMO  /  Canned results  /  No media processing", style="Muted.TLabel").pack(anchor="w", pady=(6, 12))
        ttk.Label(parent, text="Demonstrate expected-versus-actual reporting using two canned results.\nThis does not run integration tests or verify the selected file.", justify="left").pack(anchor="w", pady=(0, 14))
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(0, 14))
        self.test_button = ttk.Button(toolbar, text="Run reporting demo…", style="Primary.TButton", command=self.run_tests)
        self.test_button.pack(side="left")
        ttk.Label(toolbar, textvariable=self.test_summary, style="Heading.TLabel").pack(side="left", padx=18)
        self.results_table = self._table(parent, (("case", "Scenario", 330), ("expected", "Expected", 150), ("actual", "Actual", 150), ("result", "Result", 70)), height=9)
        self.results_table.tag_configure("pass", foreground="#8fe0c3")
        self.results_table.tag_configure("fail", foreground="#ff9aaf")
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
        self.save_button.configure(state="disabled")
        self.verdict.set("Not verified")
        self._clear_table(self.statuses_table)
        self.output.set("Selection changed. Run protect or verify.")

    def choose(self):
        path = filedialog.askopenfilename(filetypes=[("Supported media", "*.png *.bmp *.wav")])
        if path:
            self.path.set(path)

    def _inputs(self):
        if not self.path.get():
            raise IntegrationError("Choose an image or audio file first.")
        try:
            depth = int(self.lsb.get())
        except ValueError as exc:
            raise IntegrationError("Choose an LSB depth from 1 to 8.") from exc
        if not 1 <= depth <= 8:
            raise IntegrationError("Choose an LSB depth from 1 to 8.")
        return self.path.get(), depth

    def _set_busy(self, busy):
        self.busy = busy
        for button in (self.browse_button, self.protect_button, self.verify_button, self.test_button):
            button.configure(state="disabled" if busy else "normal")
        self.lsb_box.configure(state="disabled" if busy else "readonly")
        self.save_button.configure(state="normal" if not busy and self.protected is not None else "disabled")

    def _submit(self, work, success, failure):
        if self.busy:
            return
        self._set_busy(True)
        future = self.executor.submit(work)

        def poll():
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
            self.save_button.configure(state="normal")
            self.output.set("Protection complete. Save the stego file to share with Party B.")
        self._submit(lambda: self.controller.protect(path, depth), complete,
                     lambda exc: self.output.set(str(exc)))

    def verify(self):
        if self.busy:
            return
        self.verdict.set("Not verified")
        self._clear_table(self.statuses_table)
        try:
            path, depth = self._inputs()
        except IntegrationError as exc:
            self._verification_error(exc)
            return
        self.output.set("Verifying selected file…")
        self._submit(lambda: self.controller.verify(path, depth), self.show_result, self._verification_error)

    def _verification_error(self, exc):
        self.verdict.set("Cannot Verify")
        self.output.set(str(exc))

    def show_result(self, result):
        self.verdict.set(result.verdict.value)
        self.output.set(result.message)
        self._clear_table(self.statuses_table)
        for stage, status in result.statuses.items():
            self.statuses_table.insert("", "end", values=(stage.capitalize(), status))

    def run_tests(self):
        if self.busy:
            return
        destination = filedialog.askdirectory(title="Choose test evidence folder")
        if not destination:
            return
        self._clear_table(self.results_table)
        self.test_summary.set("Running…")
        self.test_output.set("Processing canned results and writing evidence…")
        self._submit(lambda: self.runner.run(build_demo_scenarios(), destination),
                     self._show_report, self._test_error)

    def _show_report(self, report):
        for row in report["results"]:
            self.results_table.insert("", "end", values=(row["name"], row["expected"],
                row["actual"] or "Execution error", "PASS" if row["passed"] else "FAIL"),
                tags=("pass" if row["passed"] else "fail",))
        self.test_summary.set(f"{report['passed']}/{report['total']} passed · {report['failed']} failed")
        self.test_output.set(f"Runner demo: {report['passed']}/{report['total']} passed; {report['failed']} failed.\nEvidence: {report['evidence_dir']}")

    def _test_error(self, exc):
        self.test_summary.set("Run failed")
        self.test_output.set(f"Cannot complete reporting demo: {exc}")

    def save(self):
        if self.busy or self.protected is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=self.protected.suffix,
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
