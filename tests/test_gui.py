import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from src.exceptions import IntegrationError
from src.gui.app import ApplicationWindow
from src.models import Media, MediaType, Verdict, VerificationResult


class GuiCallbackTests(unittest.TestCase):
    """Exercise presentation/controller boundaries without requiring a desktop."""

    def setUp(self):
        self.window = ApplicationWindow.__new__(ApplicationWindow)
        for name in ("root", "controller", "runner", "path", "lsb", "output", "verdict",
                     "test_output", "test_summary", "save_button", "results_table",
                     "statuses_table", "browse_button", "protect_button", "verify_button",
                     "test_button", "lsb_box", "executor"):
            setattr(self.window, name, Mock())
        self.window.busy = False
        self.window.protected = None
        self.window.results_table.get_children.return_value = ()
        self.window.statuses_table.get_children.return_value = ()
        self.window.path.get.return_value = "input.png"
        self.window.lsb.get.return_value = "2"
        self.window._submit = Mock(side_effect=self.execute_immediately)

    @staticmethod
    def execute_immediately(work, success, failure):
        try:
            result = work()
        except Exception as exc:
            failure(exc)
        else:
            success(result)

    def test_verify_displays_each_verdict_and_stages(self):
        for verdict in Verdict:
            with self.subTest(verdict=verdict):
                self.window.controller.verify.return_value = VerificationResult(
                    verdict, "Result details", {"signature": "Checked", "hash": "Not run"})
                self.window.verify()
                self.window.controller.verify.assert_called_with("input.png", 2)
                self.window.verdict.set.assert_called_with(verdict.value)
                self.window.output.set.assert_called_with("Result details")
                self.window.statuses_table.insert.assert_any_call(
                    "", "end", values=("Hash", "Not run"))
        self.window.test_output.set.assert_not_called()

    def test_failed_protect_clears_stale_save(self):
        self.window.protected = Media(b"old", ".png", MediaType.IMAGE)
        self.window.controller.protect.side_effect = IntegrationError("Unavailable")
        self.window.protect()
        self.assertIsNone(self.window.protected)
        self.window.save_button.configure.assert_called_with(state="disabled")
        self.window.output.set.assert_called_with("Unavailable")

    def test_successful_protect_enables_save_without_authentic_verdict(self):
        media = Media(b"protected", ".wav", MediaType.AUDIO)
        self.window.controller.protect.return_value = media
        self.window.protect()
        self.window.controller.protect.assert_called_once_with("input.png", 2)
        self.assertIs(self.window.protected, media)
        self.window.save_button.configure.assert_called_with(state="normal")
        self.window.verdict.set.assert_called_with("Not verified")

    def test_invalid_inputs_do_not_reach_controller(self):
        for path, depth in (("", "2"), ("input.png", "0"), ("input.png", "9"),
                            ("input.png", "abc"), ("input.png", "1.5")):
            with self.subTest(path=path, depth=depth):
                self.window.path.get.return_value = path
                self.window.lsb.get.return_value = depth
                self.window.protect()
                self.window.verify()
                self.window.verdict.set.assert_called_with("Cannot Verify")
        self.window.controller.protect.assert_not_called()
        self.window.controller.verify.assert_not_called()
        self.window._submit.assert_not_called()

    def test_verification_exception_clears_previous_stage_results(self):
        self.window.statuses_table.get_children.return_value = ("old-stage",)
        self.window.controller.verify.side_effect = RuntimeError("Adapter failed")
        self.window.verify()
        self.window.statuses_table.delete.assert_called_with("old-stage")
        self.window.verdict.set.assert_called_with("Cannot Verify")
        self.window.output.set.assert_called_with("Adapter failed")

    def test_invalidation_clears_protected_verdict_and_stages(self):
        self.window.protected = Media(b"old", ".png", MediaType.IMAGE)
        self.window.statuses_table.get_children.return_value = ("old-stage",)
        self.window.invalidate()
        self.assertIsNone(self.window.protected)
        self.window.verdict.set.assert_called_with("Not verified")
        self.window.statuses_table.delete.assert_called_once_with("old-stage")
        self.window.save_button.configure.assert_called_with(state="disabled")

    @patch("src.gui.app.filedialog.askopenfilename", return_value="")
    def test_cancel_selection_preserves_current_state(self, dialog):
        media = Media(b"old", ".png", MediaType.IMAGE)
        self.window.protected = media
        self.window.choose()
        self.assertIs(self.window.protected, media)
        self.window.path.set.assert_not_called()
        self.window.verdict.set.assert_not_called()

    @patch("src.gui.app.filedialog.asksaveasfilename", return_value="")
    def test_cancel_save_preserves_buffer(self, dialog):
        media = Media(b"protected", ".png", MediaType.IMAGE)
        self.window.protected = media
        self.window.save()
        self.assertIs(self.window.protected, media)
        self.window.controller.save.assert_not_called()

    @patch("src.gui.app.filedialog.asksaveasfilename", return_value="stego.png")
    def test_save_delegates_protected_buffer(self, dialog):
        media = Media(b"protected", ".png", MediaType.IMAGE)
        self.window.protected = media
        self.window.save()
        self.window.controller.save.assert_called_once_with(media, "stego.png")
        self.assertIn("Saved: stego.png", self.window.output.set.call_args.args[0])

    @patch("src.gui.app.messagebox.showerror")
    @patch("src.gui.app.filedialog.asksaveasfilename", return_value="existing.png")
    def test_save_error_preserves_buffer_for_retry(self, dialog, error):
        media = Media(b"protected", ".png", MediaType.IMAGE)
        self.window.protected = media
        self.window.controller.save.side_effect = IntegrationError("Destination exists")
        self.window.save()
        self.assertIs(self.window.protected, media)
        error.assert_called_once_with("Save failed", "Destination exists")

    @patch("src.gui.app.filedialog.askdirectory", return_value="")
    def test_cancel_tests_preserves_existing_results(self, dialog):
        self.window.run_tests()
        self.window.runner.run.assert_not_called()
        self.window.results_table.delete.assert_not_called()
        self.window.test_output.set.assert_not_called()

    @patch("src.gui.app.filedialog.askdirectory", return_value="evidence")
    def test_mock_results_remain_separate_from_file_verification(self, dialog):
        self.window.runner.run.return_value = {
            "passed": 1, "total": 2, "failed": 1, "evidence_dir": "evidence/run-1",
            "results": [{"name": "exception", "expected": "Cannot Verify", "actual": None,
                         "passed": False}]}
        self.window.run_tests()
        cases, destination = self.window.runner.run.call_args.args
        self.assertEqual((len(cases), destination), (2, "evidence"))
        text = self.window.test_output.set.call_args.args[0]
        self.assertIn("Runner demo: 1/2", text)
        self.assertIn("1 failed", text)
        self.assertIn("evidence/run-1", text)
        self.window.results_table.insert.assert_called_once_with(
            "", "end", values=("exception", "Cannot Verify", "Execution error", "FAIL"),
            tags=("fail",))
        self.window.output.set.assert_not_called()
        self.window.verdict.set.assert_not_called()

    @patch("src.gui.app.filedialog.askdirectory", return_value="evidence")
    def test_evidence_error_shows_failed_run_without_affecting_verdict(self, dialog):
        self.window.runner.run.side_effect = OSError("Disk full")
        self.window.run_tests()
        self.window.test_summary.set.assert_called_with("Run failed")
        self.assertIn("Disk full", self.window.test_output.set.call_args.args[0])
        self.window.verdict.set.assert_not_called()

    def test_busy_actions_do_not_start_another_operation(self):
        self.window.busy = True
        self.window.protect()
        self.window.verify()
        self.window.save()
        self.window.run_tests()
        self.window._submit.assert_not_called()

    def test_dispatch_runs_work_off_thread_and_callbacks_on_polling_thread(self):
        del self.window._submit
        main_thread = threading.get_ident()
        with ThreadPoolExecutor(max_workers=1) as executor:
            self.window.executor = executor
            callback_threads = []
            success = Mock(side_effect=lambda _: callback_threads.append(threading.get_ident()))
            failure = Mock()
            self.window._submit(threading.get_ident, success, failure)
            executor.shutdown(wait=True)
            success.assert_not_called()
            self.assertTrue(self.window.busy)
            self.window.root.after.call_args.args[1]()
            self.assertNotEqual(success.call_args.args[0], main_thread)
            self.assertEqual(callback_threads, [main_thread])
            failure.assert_not_called()
            self.assertFalse(self.window.busy)
            self.window.lsb_box.configure.assert_called_with(state="readonly")

    def test_dispatch_failure_restores_controls_and_reports_error(self):
        del self.window._submit
        with ThreadPoolExecutor(max_workers=1) as executor:
            self.window.executor = executor
            success, failure = Mock(), Mock()
            error = RuntimeError("Worker error")
            self.window._submit(Mock(side_effect=error), success, failure)
            executor.shutdown(wait=True)
            self.window.root.after.call_args.args[1]()
            failure.assert_called_once_with(error)
            success.assert_not_called()
            self.assertFalse(self.window.busy)
            self.window.protect_button.configure.assert_called_with(state="normal")

    def test_drag_preserves_loaded_media_and_running_operation(self):
        del self.window._submit
        media = Media(b"protected", ".png", MediaType.IMAGE)
        self.window.protected = media
        self.window.root.state.return_value = "normal"
        self.window.root.winfo_x.return_value = 100
        self.window.root.winfo_y.return_value = 80
        event = Mock(x_root=140, y_root=100)
        event.widget.winfo_class.return_value = "Canvas"
        release = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            self.window.executor = executor
            success, failure = Mock(), Mock()
            self.window._submit(lambda: release.wait(5), success, failure)
            try:
                self.window._start_drag(event)
                event.x_root, event.y_root = 190, 160
                self.window._drag_window(event)
                self.window._stop_drag(event)
                self.window.root.geometry.assert_called_once_with("+150+140")
                self.assertTrue(self.window.busy)
                self.assertIs(self.window.protected, media)
                for variable in (self.window.path, self.window.lsb, self.window.output,
                                 self.window.verdict, self.window.test_output):
                    variable.set.assert_not_called()
                self.window.statuses_table.delete.assert_not_called()
                success.assert_not_called()
            finally:
                release.set()
            executor.shutdown(wait=True)
            self.window.root.after.call_args.args[1]()
            success.assert_called_once_with(True)
            failure.assert_not_called()
            self.assertFalse(self.window.busy)
            self.assertIs(self.window.protected, media)

    def test_drag_does_not_capture_controls_or_maximized_window(self):
        self.window.root.state.return_value = "normal"
        for widget_class in ("TButton", "TEntry", "TCombobox", "Treeview", "TNotebook", "TScrollbar"):
            event = Mock(x_root=10, y_root=10)
            event.widget.winfo_class.return_value = widget_class
            self.window._start_drag(event)
            self.window._drag_window(event)
        self.window.root.state.return_value = "zoomed"
        event.widget.winfo_class.return_value = "Canvas"
        self.window._start_drag(event)
        self.window._drag_window(event)
        self.window.root.geometry.assert_not_called()

    @patch("src.gui.app.messagebox.showinfo")
    def test_close_waits_for_active_operation(self, info):
        self.window.busy = True
        self.window.close()
        info.assert_called_once()
        self.window.root.destroy.assert_not_called()
        self.window.busy = False
        self.window.close()
        self.window.executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        self.window.root.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
