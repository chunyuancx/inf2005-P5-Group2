"""Run the real glass GUI in an isolated headless Edge/Chrome test profile.

Usage: python -m tests.gui_browser --tk-python <Python with working Tk>
Requires websocket-client in the Python running this test driver.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from urllib.request import urlopen

import websocket


class Browser:
    def __init__(self, endpoint):
        self.socket = websocket.create_connection(endpoint, suppress_origin=True, timeout=10)
        self.sequence = 0
        self.errors = []
        self.command("Runtime.enable")

    def command(self, method, params=None):
        self.sequence += 1
        self.socket.send(json.dumps({"id": self.sequence, "method": method, "params": params or {}}))
        while True:
            response = json.loads(self.socket.recv())
            if response.get("method") == "Runtime.exceptionThrown":
                self.errors.append(response)
            if response.get("id") == self.sequence:
                assert "error" not in response, response
                return response.get("result", {})

    def evaluate(self, expression):
        response = self.command("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        assert "exceptionDetails" not in response, response
        return response.get("result", {}).get("value")

    def until(self, expression):
        wait_for(lambda: self.evaluate(expression), expression)

    def point(self, selector):
        self.evaluate(f"document.querySelector({json.dumps(selector)}).scrollIntoView({{block:'nearest'}})")
        return self.evaluate(f"(() => {{const r=document.querySelector({json.dumps(selector)}).getBoundingClientRect(); return {{x:r.x+r.width/2,y:r.y+r.height/2}};}})()")

    def click(self, selector):
        point = self.point(selector)
        for event in ("mousePressed", "mouseReleased"):
            self.command("Input.dispatchMouseEvent", {"type": event, **point, "button": "left", "clickCount": 1})

    def action(self, name):
        self.click(f'[data-action="{name}"]')
        self.until("!requestPending")

    def screenshot(self, path):
        result = self.command("Page.captureScreenshot", {"format": "png"})
        path.write_bytes(base64.b64decode(result["data"]))


def wait_for(check, description, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError(f"Timed out: {description}")


def exercise(browser, folder):
    checks = []

    def passed(name):
        checks.append(name)
        print(f"PASS: {name}", flush=True)

    browser.until("typeof state !== 'undefined' && state !== null")
    assert browser.evaluate("document.querySelector('[data-action=save]').disabled && !state.path")
    assert browser.evaluate("!document.querySelector('#reset, .grip, .coming-soon, [data-sortable]')")
    browser.action("verify")
    browser.until("state.verdict==='Cannot Verify'")
    assert "Choose" in browser.evaluate("document.querySelector('#output').textContent")
    browser.action("choose")  # cancel
    assert browser.evaluate("!state.path && state.verdict==='Cannot Verify'")
    passed("empty-file validation and cancelled selection")

    browser.action("choose")
    browser.until("state.path.endsWith('cover.png')")
    browser.click('[data-depth="3"]')
    browser.until("!requestPending && state.lsb==='3'")
    browser.action("protect")
    browser.until("state.busy")
    assert browser.evaluate("[...document.querySelectorAll('[data-control], [data-depth]')].every(b=>b.disabled)")
    browser.click('#close')
    assert "still processing" in browser.evaluate("document.querySelector('#toast').textContent")
    browser.click('[data-view="testing"]')
    assert browser.evaluate("!document.querySelector('#testing').hidden")
    browser.click('[data-view="workspace"]')
    browser.until("!state.busy && state.protected")
    assert browser.evaluate("!document.querySelector('[data-action=save]').disabled && state.lsb==='3'")
    passed("protect workflow, busy controls, view switching and close guard")

    browser.action("save")  # cancel
    assert browser.evaluate("state.protected") and not (folder / "stego.png").exists()
    browser.action("save")
    browser.until("!state.busy && state.output.startsWith('Saved:')")
    saved = (folder / "stego.png").read_bytes()
    assert saved != (folder / "cover.png").read_bytes()
    browser.action("save")  # exclusive creation must fail
    browser.until("!state.busy && state.output.startsWith('Save failed:')")
    assert browser.evaluate("state.protected && !document.querySelector('[data-action=save]').disabled")
    assert (folder / "stego.png").read_bytes() == saved
    passed("cancelled save, saved bytes and overwrite-error recovery")

    browser.action("choose")  # saved stego
    browser.action("verify")
    browser.until("!state.busy && state.verdict==='Authentic'")
    assert browser.evaluate("document.querySelectorAll('.stage-row').length > 0")
    browser.command("Page.reload")
    browser.until("typeof state !== 'undefined' && state?.verdict==='Authentic'")
    assert browser.evaluate("state.path.endsWith('stego.png') && state.lsb==='3'")
    passed("authentic round trip, verification stages and refresh persistence")

    browser.click('[data-view="testing"]')
    browser.action("run_tests")  # cancel
    assert browser.evaluate("state.results.length===0 && state.verdict==='Authentic'")
    for iteration in range(2):
        browser.action("run_tests")
        browser.until("!state.busy && state.test_summary.startsWith('2/2 passed')")
        assert browser.evaluate("document.querySelectorAll('#results tr.pass').length===2 && document.querySelector('#report-empty').hidden")
        assert browser.evaluate("state.verdict==='Authentic'")
        reports = list((folder / "reports").glob("run-*/results.json"))
        assert len(reports) == iteration + 1
        for path in reports:
            report = json.loads(path.read_text())
            assert (report["passed"], report["failed"], report["total"]) == (2, 0, 2)
            assert path.with_name("results.log").is_file()
    browser.screenshot(folder / "test-studio.png")
    passed("Test studio cancel, two repeated demo runs, table rows and JSON/log evidence")

    browser.click('[data-view="workspace"]')
    browser.action("choose")  # tampered
    browser.action("verify")
    browser.until("!state.busy && state.verdict==='Tampered'")
    browser.action("choose")  # tiny
    browser.action("protect")
    browser.until("!state.busy && state.output.includes('capacity')")
    assert browser.evaluate("!state.protected && document.querySelector('[data-action=save]').disabled && !document.querySelector('[data-action=protect]').disabled")
    browser.action("choose")  # cover
    browser.action("choose")  # cancel
    assert browser.evaluate("state.path.endsWith('cover.png')")
    passed("tampering verdict, failed protection recovery and cancelled replacement")

    for width in (1440, 1100, 900, 640, 390, 360):
        browser.command("Emulation.setDeviceMetricsOverride", {"width": width, "height": 960, "deviceScaleFactor": 1, "mobile": False})
        browser.until(f"innerWidth=={width}")
        assert browser.evaluate("""(() => {
          const preview=document.querySelector('.preview-card').getBoundingClientRect();
          const cards=[...document.querySelector('.steps-grid').children].map(c=>c.getBoundingClientRect());
          return document.documentElement.scrollWidth<=innerWidth && cards.every(a=>a.top>=preview.bottom)
            && cards.every((a,i)=>cards.every((b,j)=>i===j || a.right<=b.left+1 || b.right<=a.left+1 || a.bottom<=b.top+1 || b.bottom<=a.top+1));
        })()"""), width
        assert browser.evaluate("state.path.endsWith('cover.png') && state.lsb==='3'")
    browser.command("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 960, "deviceScaleFactor": 1, "mobile": False})
    browser.until("innerWidth===1440")
    browser.evaluate("scrollTo(0,0)")
    assert browser.evaluate("new Set([...document.querySelector('.steps-grid').children].map(c=>Math.round(c.getBoundingClientRect().top))).size===1")
    start, end = browser.point('.source-card .card-heading'), browser.point('.settings-card .card-heading')
    browser.command("Input.dispatchMouseEvent", {"type": "mousePressed", **start, "button": "left", "clickCount": 1})
    browser.command("Input.dispatchMouseEvent", {"type": "mouseMoved", **end, "button": "left", "buttons": 1})
    browser.command("Input.dispatchMouseEvent", {"type": "mouseReleased", **end, "button": "left", "clickCount": 1})
    assert browser.evaluate("[...document.querySelector('.steps-grid').children].map(c=>c.classList[1]).join(',')==='source-card,settings-card,result-card'")
    assert browser.evaluate("[...document.querySelector('.steps-grid').children].every(c=>getComputedStyle(c).transform==='none')")
    browser.screenshot(folder / "workspace.png")
    passed("six responsive widths, preview first, three desktop steps and non-draggable cards")
    assert not browser.errors, browser.errors
    passed("no browser JavaScript exceptions")
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tk-python", default=sys.executable)
    parser.add_argument("--browser", type=Path, default=Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe")
    args = parser.parse_args()
    assert args.browser.is_file(), "Pass --browser with an installed Edge/Chrome executable."
    repo = Path(__file__).resolve().parents[1]
    evidence = repo / "test-evidence"
    evidence.mkdir(exist_ok=True)
    folder = evidence / f"gui-{uuid.uuid4().hex[:12]}"
    folder.mkdir()
    hidden = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    fixture = renderer = browser = None
    try:
        with (folder / "backend.log").open("w") as log:
            fixture = subprocess.Popen([args.tk_python, "-m", "tests.gui_browser_fixture", "--output", str(folder)], cwd=repo, stdout=log, stderr=log, **hidden)
            wait_for(lambda: (folder / "ready.json").is_file(), "fixture startup")
            url = json.loads((folder / "ready.json").read_text())["url"]
            profile = folder / "browser-profile"
            renderer = subprocess.Popen([str(args.browser), "--headless", "--no-first-run", "--no-default-browser-check", "--remote-debugging-port=0", f"--user-data-dir={profile}", "--window-size=1440,960", url], stdout=log, stderr=log, **hidden)
            wait_for(lambda: (profile / "DevToolsActivePort").is_file(), "browser startup")
            port = (profile / "DevToolsActivePort").read_text().splitlines()[0]
            def page():
                pages = json.load(urlopen(f"http://127.0.0.1:{port}/json", timeout=3))
                return next((p for p in pages if p.get("url") == url), None)
            target = wait_for(page, "GUI tab")
            browser = Browser(target["webSocketDebuggerUrl"])
            checks = exercise(browser, folder)
            # Test the app's close control. Browser.close can terminate a headless
            # tab without delivering pagehide, so it is not an app-close test.
            browser.click('#close')
            fixture.wait(timeout=15)
            assert fixture.returncode == 0
            backend = json.loads((folder / "backend.json").read_text())
            assert len(backend["dialog_errors"]) == 1
            assert [call[0] for call in backend["calls"]] == ["protect", "verify", "verify", "protect"]
            checks.append("app Close button shuts down the Python session")
            (folder / "checks.json").write_text(json.dumps({"passed": checks, "service_mode": "test doubles", "native_dialogs": "stubbed"}, indent=2))
            try:
                browser.command("Browser.close")
            except (websocket.WebSocketException, OSError):
                pass
            browser.socket.close()
            browser = None
            print(f"GUI browser checks passed. Evidence: {folder}", flush=True)
    finally:
        if browser:
            try:
                browser.screenshot(folder / "failure.png")
                browser.command("Browser.close")
            except Exception:
                pass
            browser.socket.close()
        for process in (renderer, fixture):
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
