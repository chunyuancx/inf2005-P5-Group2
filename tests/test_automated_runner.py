import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.models import Verdict, VerificationResult
from src.testing.demo_scenarios import build_demo_scenarios
from src.testing.runner import AutomatedTestRunner, Scenario


class RunnerTests(unittest.TestCase):
    def test_demo_evidence_matches_report(self):
        scenarios = build_demo_scenarios()
        self.assertEqual(len(scenarios), 2)
        self.assertEqual(len({case.name for case in scenarios}), 2)
        with tempfile.TemporaryDirectory() as folder:
            report = AutomatedTestRunner().run(scenarios, folder)
            self.assertEqual((report["passed"], report["failed"]), (2, 0))
            saved = json.loads((Path(report["evidence_dir"]) / "results.json").read_text())
            self.assertEqual(saved, report)
            self.assertTrue(all(row["mode"] == "runner-demo" for row in saved["results"]))
            self.assertEqual(len((Path(report["evidence_dir"]) / "results.log").read_text().splitlines()), 3)

    def test_mismatch_and_exception_fail_but_runner_continues(self):
        cases = [
            Scenario("mismatch", Verdict.AUTHENTIC,
                     lambda: VerificationResult(Verdict.TAMPERED, "Mismatch"), "image", 1),
            Scenario("exception", Verdict.CANNOT_VERIFY, Mock(side_effect=RuntimeError("boom")), "audio", 8),
            Scenario("success", Verdict.AUTHENTIC,
                     lambda: VerificationResult(Verdict.AUTHENTIC, "OK"), "image", 1),
        ]
        with tempfile.TemporaryDirectory() as folder:
            runner = AutomatedTestRunner()
            report = runner.run(cases, folder)
            self.assertEqual((report["passed"], report["failed"]), (1, 2))
            self.assertIsNone(report["results"][1]["actual"])
            self.assertIn("RuntimeError", report["results"][1]["error"])
            second = runner.run(cases, folder)
            self.assertNotEqual(report["evidence_dir"], second["evidence_dir"])
            self.assertTrue((Path(report["evidence_dir"]) / "results.json").exists())


if __name__ == "__main__":
    unittest.main()
