from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.controllers import ApplicationController
from src.exceptions import IntegrationError
from src.testing.demo_scenarios import build_demo_scenarios
from src.testing.runner import AutomatedTestRunner


class ApplicationWindow:
    def __init__(self, root: tk.Tk, controller: ApplicationController,
                 runner: AutomatedTestRunner | None = None):
        self.root, self.controller = root, controller
        self.runner = runner or AutomatedTestRunner()
        self.protected = None
        self.busy = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.path = tk.StringVar()
        self.lsb = tk.StringVar(value="1")
        self.output = tk.StringVar(value="Choose an original or stego file to begin.")
        self.verdict = tk.StringVar(value="Not verified")
        self.test_output = tk.StringVar(value="Run the reporting demo to generate a new evidence folder.")
        self.test_summary = tk.StringVar(value="No test run yet")
        root.title("Media Integrity | Protect & Verify")
        root.geometry("1140x860")
        root.minsize(940, 780)
        root.configure(background="#edf2f4")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._configure_styles()
        header = tk.Frame(root, bg="#12382f", padx=28, pady=22)
        header.pack(fill="x")
        tk.Label(header, text="INF2005  /  MEDIA AUTHENTICATION", bg="#12382f", fg="#b9ddcb",
                 font=("Helvetica", 10, "bold")).pack(anchor="w")
        tk.Label(header, text="Media Integrity", bg="#12382f", fg="white",
                 font=("Helvetica", 27, "bold")).pack(anchor="w", pady=(6, 3))
        tk.Label(header, text="Protect a file. Verify its integrity. Review test evidence.",
                 bg="#12382f", fg="#d4e5dd", font=("Helvetica", 12)).pack(anchor="w")
        body = ttk.Frame(root, padding=(24, 18))
        body.pack(fill="both", expand=True)
        self.tabs = ttk.Notebook(body)
        self.tabs.pack(fill="both", expand=True)
        workspace = ttk.Frame(self.tabs, padding=18)
        testing = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(workspace, text="  Protect & Verify  ")
        self.tabs.add(testing, text="  Automated Tests  ")
        self._build_workspace(workspace)
        self._build_testing(testing)
        ttk.Label(body, text="Service integration pending · Preview and playback will become available with media adapters.",
                  style="Muted.TLabel").pack(anchor="w", pady=(12, 0))
        self.lsb.trace_add("write", self.invalidate)
        self.path.trace_add("write", self.invalidate)

    def _build_workspace(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(2, weight=1)
        source = ttk.LabelFrame(parent, text="01 / Source file", padding=14)
        source.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        source.columnconfigure(0, weight=1)
        ttk.Label(source, text="Original file → Protect    •    Received stego file → Verify",
                  style="Muted.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Entry(source, textvariable=self.path, state="readonly").grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.browse_button = ttk.Button(source, text="Choose file…", command=self.choose)
        self.browse_button.grid(row=1, column=1)
        ttk.Label(source, text="PNG / BMP images  ·  PCM WAV audio", style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 0))
        actions = ttk.LabelFrame(parent, text="02 / Protect or verify", padding=14)
        actions.grid(row=1, column=0, sticky="nsew", padx=(0, 12), pady=(0, 12))
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
        preview = ttk.LabelFrame(parent, text="Media preview", padding=14)
        preview.grid(row=1, column=1, sticky="nsew", pady=(0, 12))
        ttk.Label(preview, text="Original  →  Stego", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(preview, text="Image comparison is awaiting integration.", style="Muted.TLabel", wraplength=290).pack(anchor="w", pady=(8, 12))
        ttk.Separator(preview).pack(fill="x", pady=(0, 10))
        ttk.Label(preview, text="Audio playback", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        play = ttk.Frame(preview)
        play.pack(fill="x")
        ttk.Button(play, text="Play original", state="disabled").pack(side="left", padx=(0, 8))
        ttk.Button(play, text="Play stego", state="disabled").pack(side="left")
        result = ttk.LabelFrame(parent, text="03 / File verification result", padding=14)
        result.grid(row=2, column=0, columnspan=2, sticky="nsew")
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
        self.results_table.tag_configure("pass", foreground="#166448")
        self.results_table.tag_configure("fail", foreground="#b42318")
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
        style.configure(".", font=("Helvetica", 11), background="#edf2f4", foreground="#203c37")
        style.configure("Muted.TLabel", foreground="#5b6c70", font=("Helvetica", 10))
        style.configure("Heading.TLabel", font=("Helvetica", 11, "bold"))
        style.configure("Title.TLabel", font=("Helvetica", 19, "bold"))
        style.configure("Verdict.TLabel", font=("Helvetica", 18, "bold"))
        style.configure("TLabelframe", bordercolor="#cbd6d6", relief="solid")
        style.configure("TLabelframe.Label", font=("Helvetica", 10, "bold"))
        style.configure("TButton", padding=(12, 9), background="white")
        style.configure("Primary.TButton", background="#176d54", foreground="white")
        style.map("Primary.TButton", background=[("disabled", "#d2dcda"), ("active", "#10563f")], foreground=[("disabled", "#647571")])
        style.configure("TNotebook.Tab", padding=(16, 10))
        style.configure("Treeview", rowheight=27, fieldbackground="white", background="white")
        style.configure("Treeview.Heading", font=("Helvetica", 10, "bold"), padding=7)

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
