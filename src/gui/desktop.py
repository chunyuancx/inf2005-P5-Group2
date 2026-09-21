"""Local glass desktop renderer; all workflows remain in ApplicationWindow.

Only a random loopback address is served. Native file dialogs and callbacks run
on the Tk thread; encoding and verification retain the existing worker thread.
"""

import json
import os
from pathlib import Path
from queue import Empty, Queue
import secrets
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import webbrowser

from src.gui.app import ApplicationWindow


class ControlState:
    """Small view adapter for the existing workflow's enabled/disabled controls."""

    def __init__(self, state="normal"):
        self.state = state

    def configure(self, *, state):
        self.state = state


class TableState:
    def __init__(self):
        self.rows = {}
        self.sequence = 0

    def get_children(self):
        return tuple(self.rows)

    def delete(self, key):
        del self.rows[key]

    def insert(self, _parent, _position, *, values, tags=()):
        self.sequence += 1
        self.rows[self.sequence] = {"values": values, "tags": tags}


class GlassDesktop(ApplicationWindow):
    controls = ("browse_button", "protect_button", "verify_button", "save_button",
                "test_button", "lsb_box")

    def __init__(self, root, controller, runner=None):
        self._initialize_state(root, controller, runner)
        root.withdraw()
        for name in self.controls:
            setattr(self, name, ControlState())
        self.save_button.configure(state="disabled")
        self.lsb_box.configure(state="readonly")
        self.statuses_table, self.results_table = TableState(), TableState()
        self.path.trace_add("write", self.invalidate)
        self.lsb.trace_add("write", self.invalidate)
        self.requests = Queue()
        self.close_requested = False
        self.closed = False
        self.close_deadline = None
        self.root.after(25, self._drain)

    def snapshot(self):
        # A refresh reconnects to the same state instead of closing the session.
        self.close_deadline = None
        return {
            "path": self.path.get(), "lsb": self.lsb.get(), "busy": self.busy,
            "output": self.output.get(), "verdict": self.verdict.get(),
            "test_output": self.test_output.get(), "test_summary": self.test_summary.get(),
            "protected": self.protected is not None,
            "controls": {name: getattr(self, name).state for name in self.controls},
            "statuses": list(self.statuses_table.rows.values()),
            "results": list(self.results_table.rows.values()),
        }

    def action(self, payload):
        name = payload.get("action")
        if name == "detach":
            self.close_deadline = time.monotonic() + 5
            return {}
        if name == "close":
            self.close_requested = True
            return self.snapshot()
        if self.busy:
            return self.snapshot()
        if name == "depth":
            depth = payload.get("value")
            if str(depth) not in {str(i) for i in range(1, 9)}:
                raise ValueError("Choose an LSB depth from 1 to 8.")
            self.lsb.set(str(depth))
        elif name in {"choose", "protect", "verify", "save", "run_tests"}:
            getattr(self, name)()
        else:
            raise ValueError("Unknown action")
        return self.snapshot()

    def _drain(self):
        for _ in range(20):
            try:
                function, reply = self.requests.get_nowait()
            except Empty:
                break
            try:
                reply.put((True, function()))
            except Exception as exc:
                reply.put((False, str(exc)))
        detached = self.close_deadline is not None and time.monotonic() >= self.close_deadline
        if (self.close_requested or detached) and not self.busy:
            self.closed = True
            self.close()
            return
        self.root.after(25, self._drain)

    def invoke(self, function):
        reply = Queue(maxsize=1)
        self.requests.put((function, reply))
        success, value = reply.get(timeout=300)
        if not success:
            raise ValueError(value)
        return value


def make_server(desktop):
    token = secrets.token_urlsafe(32)
    assets = Path(__file__).with_name("web")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, body, kind="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def authorized(self):
            host = f"127.0.0.1:{self.server.server_port}"
            return (self.headers.get("Host") == host
                    and self.path.startswith(f"/{token}/")
                    and self.headers.get("Origin", f"http://{host}") == f"http://{host}")

        def do_GET(self):
            if not self.authorized():
                self.send(403, b'{}')
                return
            name = self.path.removeprefix(f"/{token}/")
            if name == "state":
                try:
                    self.send(200, json.dumps(desktop.invoke(desktop.snapshot)).encode())
                except (ValueError, Empty):
                    self.send(503, b'{}')
                return
            types = {"index.html": "text/html; charset=utf-8", "style.css": "text/css; charset=utf-8",
                     "app.js": "text/javascript; charset=utf-8"}
            if name not in types:
                self.send(404, b'{}')
                return
            self.send(200, (assets / name).read_bytes(), types[name])

        def do_POST(self):
            if not self.authorized() or self.path != f"/{token}/action":
                self.send(403, b'{}')
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2048:
                    raise ValueError("Invalid request")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Invalid request")
                result = desktop.invoke(lambda: desktop.action(payload))
                self.send(200, json.dumps(result).encode())
            except (ValueError, Empty) as exc:
                self.send(400, json.dumps({"error": str(exc)}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    return server, f"http://127.0.0.1:{server.server_port}/{token}/index.html"


def launch(root, controller, *, open_window=True):
    desktop = GlassDesktop(root, controller)
    server, url = make_server(desktop)
    Thread(target=server.serve_forever, daemon=True).start()
    print(f"Glass desktop: {url}", flush=True)
    if open_window:
        browsers = [Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
                    Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe"]
        browser = next((path for path in browsers if path.is_file()), None)
        if browser:
            subprocess.Popen([str(browser), f"--app={url}", "--window-size=1440,1000"])
        else:
            webbrowser.open(url)
    try:
        root.mainloop()
    finally:
        server.shutdown()
        server.server_close()
        desktop.executor.shutdown(wait=False, cancel_futures=True)
