import json
from threading import Thread
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.gui.desktop import GlassDesktop, make_server
from src.models import Media, MediaType, Verdict, VerificationResult


class Variable:
    def __init__(self, value=""):
        self.value = value
        self.callbacks = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        for callback in self.callbacks:
            callback()

    def trace_add(self, _, callback):
        self.callbacks.append(callback)


class GlassDesktopTests(unittest.TestCase):
    def setUp(self):
        with patch("src.gui.app.tk.StringVar", side_effect=Variable):
            self.desktop = GlassDesktop(Mock(), Mock())

    def tearDown(self):
        self.desktop.executor.shutdown(wait=True)

    def test_view_reads_preserve_selected_file_and_protected_buffer(self):
        self.desktop.path.set("sample.png")
        media = Media(b"protected", ".png", MediaType.IMAGE)
        self.desktop.protected = media
        self.desktop._set_busy(True)
        for _ in range(3):
            state = self.desktop.snapshot()
            self.assertEqual(state["path"], "sample.png")
            self.assertTrue(state["busy"])
            self.assertTrue(state["protected"])
            self.assertEqual(state["controls"]["save_button"], "disabled")
        self.assertIs(self.desktop.protected, media)
        self.desktop.controller.protect.assert_not_called()

    def test_depth_change_invalidates_but_is_ignored_during_work(self):
        self.desktop.action({"action": "depth", "value": "3"})
        self.assertEqual(self.desktop.snapshot()["lsb"], "3")
        self.desktop._set_busy(True)
        self.desktop.action({"action": "depth", "value": "5"})
        self.assertEqual(self.desktop.snapshot()["lsb"], "3")
        self.desktop._set_busy(False)
        with self.assertRaises(ValueError):
            self.desktop.action({"action": "depth", "value": "9"})

    def test_verify_uses_existing_worker_and_exposes_result(self):
        self.desktop.path.set("sample.png")
        self.desktop.controller.verify.return_value = VerificationResult(
            Verdict.AUTHENTIC, "Signature checked", {"signature": "Valid"})
        self.desktop.action({"action": "verify"})
        self.desktop.executor.shutdown(wait=True)
        self.assertTrue(self.desktop.snapshot()["busy"])
        self.desktop.root.after.call_args.args[1]()
        state = self.desktop.snapshot()
        self.assertFalse(state["busy"])
        self.assertEqual(state["verdict"], Verdict.AUTHENTIC.value)
        self.assertEqual(state["statuses"][0]["values"], ("Signature", "Valid"))
        self.desktop.controller.verify.assert_called_once_with("sample.png", 1)

    def test_close_request_waits_for_worker(self):
        self.desktop._set_busy(True)
        self.desktop.action({"action": "close"})
        self.desktop._drain()
        self.desktop.root.destroy.assert_not_called()
        self.desktop._set_busy(False)
        self.desktop._drain()
        self.desktop.root.destroy.assert_called_once()

    def test_reload_reconnects_without_clearing_selected_media(self):
        self.desktop.path.set("sample.png")
        self.desktop.protected = object()
        self.desktop.action({"action": "detach"})
        self.assertIsNotNone(self.desktop.close_deadline)
        state = self.desktop.snapshot()
        self.assertIsNone(self.desktop.close_deadline)
        self.assertEqual(state["path"], "sample.png")
        self.assertTrue(state["protected"])
        self.desktop._drain()
        self.desktop.root.destroy.assert_not_called()


class LocalRendererTests(unittest.TestCase):
    def setUp(self):
        self.desktop = Mock()
        self.desktop.snapshot.return_value = {"path": "private.png", "busy": False}
        self.desktop.invoke.side_effect = lambda function: function()
        self.server, self.url = make_server(self.desktop)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_serves_glass_assets_and_snapshot(self):
        with urlopen(self.url) as response:
            self.assertIn(b'Glass workspace', response.read())
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        with urlopen(self.url.replace("index.html", "state")) as response:
            self.assertEqual(json.load(response)["path"], "private.png")

    def test_blocks_missing_token_external_origin_and_arbitrary_files(self):
        for request, status in (
            (f"http://127.0.0.1:{self.server.server_port}/state", 403),
            (Request(self.url.replace("index.html", "state"), headers={"Origin": "https://example.com"}), 403),
            (self.url.replace("index.html", "../../controllers/application.py"), 404),
        ):
            with self.subTest(request=request), self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, status)
        self.desktop.invoke.assert_not_called()

    def test_rejects_malformed_action_without_dispatch(self):
        request = Request(self.url.replace("index.html", "action"), data=b'[]',
                          headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)
        self.desktop.action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
