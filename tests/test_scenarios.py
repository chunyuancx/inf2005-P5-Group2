"""The real attack suite must pass end to end and leave complete evidence."""
import json
from pathlib import Path

from src.models import Verdict
from src.testing.runner import AutomatedTestRunner
from src.testing.scenarios import build_real_scenarios


def test_full_attack_suite_passes_and_writes_evidence(tmp_path):
    scenarios = build_real_scenarios(tmp_path)
    names = [case.name for case in scenarios]
    assert len(names) == len(set(names)) and len(names) >= 50
    assert {case.media_type for case in scenarios} == {"image", "audio"}
    assert {case.mode for case in scenarios} == {"manual", "auto"}
    assert {case.expected for case in scenarios} == set(Verdict) - {Verdict.WRONG_START_LOCATION}, \
        "Wrong Start Location is unreachable today (docs section 4); every other verdict must be exercised"

    report = AutomatedTestRunner().run(scenarios, tmp_path / "evidence")
    failures = [(row["name"], row["expected"], row["actual"] or row["error"])
                for row in report["results"] if not row["passed"]]
    assert not failures, failures
    folder = Path(report["evidence_dir"])
    assert json.loads((folder / "results.json").read_text())["failed"] == 0
    markdown = (folder / "results.md").read_text(encoding="utf-8")
    assert markdown.count("| PASS |") == report["total"]
    assert "docs section 7" in markdown  # the degradation notes travel with the evidence


def test_degraded_verdicts_are_annotated(tmp_path):
    scenarios = build_real_scenarios(tmp_path, modes=("auto",))
    tampering = [case for case in scenarios if case.attack in {"pixel_edit", "sample_edit", "crop_bottom"}]
    assert tampering and all(case.expected is Verdict.PAYLOAD_MISSING and "section 7" in case.note
                             for case in tampering)
    wrong_passphrase = next(case for case in scenarios if case.attack == "wrong_passphrase")
    assert wrong_passphrase.expected is Verdict.PAYLOAD_MISSING and "section 4" in wrong_passphrase.note
