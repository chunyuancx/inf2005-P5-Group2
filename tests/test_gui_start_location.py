"""GUI plumbing for the passphrase and manual start position.

Covers both front-ends: the Tk ApplicationWindow and the GlassDesktop bridge
that drives the web view.
"""
import unittest
from unittest.mock import Mock, patch

from src.exceptions import IntegrationError
from src.gui.app import ApplicationWindow
from src.gui.desktop import GlassDesktop
from src.services.start_location import KeyedStartLocation
from tests.test_glass_desktop import Variable

WIDGETS = ("root", "runner", "output", "verdict", "test_output", "test_summary",
           "save_button", "results_table", "statuses_table", "browse_button",
           "protect_button", "verify_button", "test_button", "lsb_box",
           "passphrase_box", "mode_box", "manual_box", "executor")


class StartLocationGuiTests(unittest.TestCase):
    """The Tk view, with a real locator behind a mock controller."""

    def setUp(self):
        self.window = ApplicationWindow.__new__(ApplicationWindow)
        for name in WIDGETS:
            setattr(self.window, name, Mock())
        self.locator = KeyedStartLocation()
        self.window.controller = Mock()
        self.window.controller.location = self.locator
        self.window.busy = False
        self.window.protected = None
        self.window.statuses_table.get_children.return_value = ()
        self.window.path = Variable("input.png")
        self.window.lsb = Variable("2")
        self.window.passphrase = Variable("")
        self.window.start_mode = Variable("auto")
        self.window.manual_start = Variable("")
        self.window._submit = Mock()

    # ------------------------------------------------------------ auto mode

    def test_typed_passphrase_reaches_the_locator(self):
        self.window.passphrase.set("party-A-passphrase")
        self.window._apply_start_location()
        self.assertEqual(self.locator.key, b"party-A-passphrase")
        self.assertIsNone(self.locator.manual_start)

    def test_empty_passphrase_is_refused_before_any_work(self):
        with self.assertRaises(IntegrationError) as caught:
            self.window._apply_start_location()
        self.assertIn("passphrase", str(caught.exception).lower())

    def test_protect_and_verify_refuse_to_dispatch_without_a_passphrase(self):
        self.window.protect()
        self.window.verify()
        self.window._submit.assert_not_called()
        self.window.controller.protect.assert_not_called()
        self.window.controller.verify.assert_not_called()
        self.assertIn("passphrase", self.window.output.set.call_args[0][0].lower())

    def test_switching_back_to_auto_clears_the_manual_position(self):
        self.locator.manual_start = 4_000
        self.window.passphrase.set("party-A-passphrase")
        self.window._apply_start_location()
        self.assertIsNone(self.locator.manual_start)

    # ---------------------------------------------------------- manual mode

    def test_manual_position_reaches_the_locator_without_a_passphrase(self):
        self.window.start_mode.set("manual")
        self.window.manual_start.set("  4000  ")      # spaces tolerated
        self.window._apply_start_location()
        self.assertEqual(self.locator.manual_start, 4_000)
        self.assertEqual(self.locator.key, b"")

    def test_blank_manual_position_is_refused(self):
        self.window.start_mode.set("manual")
        with self.assertRaises(IntegrationError):
            self.window._apply_start_location()

    def test_non_numeric_manual_position_is_refused(self):
        self.window.start_mode.set("manual")
        self.window.manual_start.set("somewhere")
        with self.assertRaises(IntegrationError) as caught:
            self.window._apply_start_location()
        self.assertIn("whole number", str(caught.exception))

    def test_manual_position_zero_is_refused(self):
        """The very first unit is rejected even when typed by hand."""
        self.window.start_mode.set("manual")
        self.window.manual_start.set("0")
        with self.assertRaises(IntegrationError):
            self.window._apply_start_location()

    # ------------------------------------------------------ other locators

    def test_a_locator_without_a_passphrase_is_left_alone(self):
        """Other locator designs and test doubles must keep working."""
        self.window.controller.location = object()
        self.window._apply_start_location()      # must not raise


class GlassStartLocationTests(unittest.TestCase):
    """The web bridge: actions in, snapshot out."""

    def setUp(self):
        with patch("src.gui.app.tk.StringVar", side_effect=Variable):
            self.desktop = GlassDesktop(Mock(), Mock())

    def tearDown(self):
        self.desktop.executor.shutdown(wait=True)

    def test_passphrase_action_is_stored(self):
        self.desktop.action({"action": "passphrase", "value": "secret"})
        self.assertEqual(self.desktop.passphrase.get(), "secret")

    def test_snapshot_never_returns_the_passphrase(self):
        self.assertFalse(self.desktop.snapshot()["passphrase_set"])
        self.desktop.action({"action": "passphrase", "value": "super-secret"})
        state = self.desktop.snapshot()
        self.assertTrue(state["passphrase_set"])
        self.assertNotIn("super-secret", str(state))

    def test_text_fields_reject_non_text_payloads(self):
        for name, value in (("passphrase", 1234), ("manual_start", 4000)):
            with self.assertRaises(ValueError):
                self.desktop.action({"action": name, "value": value})

    def test_start_mode_action_is_stored(self):
        self.desktop.action({"action": "start_mode", "value": "manual"})
        self.assertEqual(self.desktop.snapshot()["start_mode"], "manual")

    def test_start_mode_rejects_anything_else(self):
        for bad in ("sideways", "", None, 7):
            with self.assertRaises(ValueError):
                self.desktop.action({"action": "start_mode", "value": bad})

    def test_manual_start_action_is_stored_and_echoed(self):
        self.desktop.action({"action": "manual_start", "value": "4000"})
        self.assertEqual(self.desktop.snapshot()["manual_start"], "4000")

    def test_new_controls_are_reported_to_the_page(self):
        controls = self.desktop.snapshot()["controls"]
        for name in ("passphrase_box", "mode_box", "manual_box"):
            self.assertIn(name, controls)

    def test_controls_disable_while_busy(self):
        self.desktop._set_busy(True)
        controls = self.desktop.snapshot()["controls"]
        for name in ("passphrase_box", "mode_box", "manual_box"):
            self.assertEqual(controls[name], "disabled", name)


if __name__ == "__main__":
    unittest.main()
