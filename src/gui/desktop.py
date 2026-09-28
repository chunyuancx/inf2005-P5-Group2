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

from src.attacks import ATTACKS, describe
from src.gui.app import ApplicationWindow
from src.gui.preview import audio_difference, image_difference
from src.models import MediaType

MEDIA_TYPES = {".png": "image/png", ".bmp": "image/bmp", ".wav": "audio/wav"}


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
                "test_button", "lsb_box", "passphrase_box", "payload_box", "mode_box", "manual_box",
                "attack_button", "attack_box")

    def __init__(self, root, controller, runner=None, scenarios=None):
        self._initialize_state(root, controller, runner, scenarios)
        root.withdraw()
        for name in self.controls:
            setattr(self, name, ControlState())
        self.save_button.configure(state="disabled")
        self.lsb_box.configure(state="readonly")
        self.statuses_table, self.results_table = TableState(), TableState()
        self.path.trace_add("write", self.invalidate)
        self.lsb.trace_add("write", self.invalidate)
        self.payload.trace_add("write", self.invalidate)
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
            # Report only that a passphrase is held, never the passphrase itself.
            "passphrase_set": bool(self.passphrase.get()),
            "payload": self.payload.get(),
            "start_mode": self.start_mode.get(),
            "manual_start": self.manual_start.get(),
            "output": self.output.get(), "verdict": self.verdict.get(),
            "decoded_payload": self.decoded_payload.get(),
            "test_output": self.test_output.get(), "test_summary": self.test_summary.get(),
            "attack_output": self.attack_output.get(),
            # Only the attacks that apply to the selected file's type; none until a file is chosen.
            "attacks": describe(MediaType(self.media_kind())) if self.media_kind() else [],
            "protected": self.protected is not None,
            "save_ready": self.protected is not None and self.verified_protected,
            "media_kind": self.media_kind(),
            "preview_version": self.preview_version,
            "controls": {name: getattr(self, name).state for name in self.controls},
            "statuses": list(self.statuses_table.rows.values()),
            "results": list(self.results_table.rows.values()),
        }

    def media_kind(self):
        suffix = Path(self.path.get()).suffix.lower()
        if suffix in {".png", ".bmp"}:
            return "image"
        if suffix == ".wav":
            return "audio"
        return None

    def preview_sources(self):
        """Selected path and protected buffer for the preview endpoints.

        Runs on the Tk thread; the HTTP handler reads the file and computes
        the difference on its own thread afterwards.
        """
        return {"path": self.path.get(),
                "suffix": Path(self.path.get()).suffix.lower(),
                "protected": self.protected.data if self.protected is not None else None}

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
        if name == "passphrase":
            value = payload.get("value")
            if value is not None and not isinstance(value, str):
                raise ValueError("Passphrase must be text.")
            self.passphrase.set(value or "")
        elif name == "payload":
            value = payload.get("value")
            if value is not None and not isinstance(value, str):
                raise ValueError("Payload must be text.")
            self.payload.set(value or "")
        elif name == "start_mode":
            if payload.get("value") not in {"auto", "manual"}:
                raise ValueError("Start mode must be automatic or manual.")
            self.start_mode.set(payload["value"])
        elif name == "manual_start":
            value = payload.get("value")
            if value is not None and not isinstance(value, str):
                raise ValueError("Start position must be text.")
            self.manual_start.set(value or "")
        elif name == "depth":
            depth = payload.get("value")
            if str(depth) not in {str(i) for i in range(1, 9)}:
                raise ValueError("Choose an LSB depth from 1 to 8.")
            self.lsb.set(str(depth))
        elif name == "attack":
            if payload.get("value") not in ATTACKS:
                raise ValueError("Choose an attack from the list.")
            self.attack(payload["value"])
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

        def send(self, status, body, kind="application/json", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            for header, value in (extra or {}).items():
                self.send_header(header, value)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; base-uri 'none'")
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
            name = self.path.removeprefix(f"/{token}/").partition("?")[0]
            if name.startswith("preview/"):
                self.send_preview(name.removeprefix("preview/"))
                return
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

        def send_preview(self, which):
            try:
                sources = desktop.invoke(desktop.preview_sources)
                kind = MEDIA_TYPES.get(sources["suffix"])
                if which not in {"original", "protected", "difference"} or not kind or not sources["path"]:
                    raise ValueError("No preview")
                if which == "original":
                    self.send(200, Path(sources["path"]).read_bytes(), kind)
                    return
                if sources["protected"] is None:
                    raise ValueError("Nothing protected yet")
                if which == "protected":
                    self.send(200, sources["protected"], kind)
                    return
                original = Path(sources["path"]).read_bytes()
                if kind.startswith("image/"):
                    diff = image_difference(original, sources["protected"])
                    self.send(200, diff.png, "image/png",
                              extra={"X-Changed": str(diff.changed), "X-Total": str(diff.total),
                                     "X-Box": ",".join(map(str, diff.box)) if diff.box else "",
                                     "X-Scale": f"{diff.scale:.2f}"})
                else:
                    changed, total = audio_difference(original, sources["protected"])
                    self.send(200, json.dumps({"changed": changed, "total": total}).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                # Unreadable media or a size mismatch simply shows no preview.
                self.send(404, b'{}')

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


WINDOW_TITLE = "Media Integrity | Glass workspace"


def _windows_titled(title: str) -> list:
    """Handles of visible top-level windows with exactly this title (Windows only)."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = []

    def collect(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buffer, 256)
            if buffer.value == title:
                found.append(hwnd)
        return True
    user32.EnumWindows(callback_type(collect), 0)
    return found


def _close_stale_windows(title: str) -> int:
    """Close app windows left over from earlier sessions, which can only show
    'Session disconnected' and would otherwise sit in front of the new one."""
    if os.name != "nt":
        return 0
    import ctypes
    stale = _windows_titled(title)
    for hwnd in stale:
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    return len(stale)


def _maximize_when_visible(title: str, ignore=(), timeout: float = 15.0) -> bool:
    """Maximise and raise the first new window with this title (Windows only)."""
    if os.name != "nt":
        return False
    import ctypes
    user32 = ctypes.windll.user32
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = [hwnd for hwnd in _windows_titled(title) if hwnd not in ignore]
        if found:
            user32.ShowWindow(found[0], 3)  # SW_MAXIMIZE
            user32.SetForegroundWindow(found[0])
            return True
        time.sleep(0.2)
    return False


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
            # Edge/Chrome app windows restore their last bounds and can ignore
            # --start-maximized, so the window is also maximised once it appears.
            stale = tuple(_windows_titled(WINDOW_TITLE))
            _close_stale_windows(WINDOW_TITLE)
            subprocess.Popen([str(browser), f"--app={url}", "--start-maximized"])
            Thread(target=_maximize_when_visible, args=(WINDOW_TITLE, stale), daemon=True).start()
        else:
            webbrowser.open(url)
    try:
        root.mainloop()
    finally:
        server.shutdown()
        server.server_close()
        desktop.executor.shutdown(wait=False, cancel_futures=True)
