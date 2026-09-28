"""Automated test runner: executes scenarios and records expected versus actual.

Every run writes a fresh evidence folder holding ``results.json`` (machine
readable), ``results.log`` (one line per case) and ``results.md`` (a table
for reports). A scenario passes when the verdict it produced equals the
verdict it expected; an execution error always fails, even when the expected
verdict is Cannot Verify.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.models import Verdict, VerificationResult


@dataclass(frozen=True)
class Scenario:
    name: str
    expected: Verdict
    execute: Callable[[], VerificationResult]
    media_type: str
    lsb: int
    mode: str = "mock"
    attack: str = ""
    note: str = ""


class AutomatedTestRunner:
    def run(self, scenarios: list[Scenario], output_dir: str = "test-evidence") -> dict:
        rows = []
        for case in scenarios:
            row = {"name": case.name, "mode": case.mode, "attack": case.attack,
                   "media_type": case.media_type, "lsb": case.lsb,
                   "expected": case.expected.value, "actual": None,
                   "passed": False, "statuses": {}, "error": None, "note": case.note}
            try:
                result = case.execute()
                row.update(actual=result.verdict.value,
                           passed=result.verdict == case.expected,
                           statuses=dict(result.statuses), message=result.message)
            except Exception as exc:
                # An execution error must fail even when Cannot Verify is expected.
                row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
        report = {"created_utc": datetime.now(timezone.utc).isoformat(),
                  "total": len(rows), "passed": sum(row["passed"] for row in rows),
                  "failed": sum(not row["passed"] for row in rows),
                  "results": rows}
        parent = Path(output_dir)
        parent.mkdir(parents=True, exist_ok=True)
        # One folder per run, named by the date and time it was made.
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder, counter = parent / f"run-{stamp}", 1
        while folder.exists():
            counter += 1
            folder = parent / f"run-{stamp}-{counter}"
        folder.mkdir()
        report["evidence_dir"] = str(folder)
        (folder / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        lines = ["Expected vs actual verification evidence (mode recorded per case)"]
        lines.extend(f"{'PASS' if row['passed'] else 'FAIL'} {row['name']} "
                     f"mode={row['mode']} expected={row['expected']} actual={row['actual']} "
                     f"error={row['error']}" + (f" note={row['note']}" if row["note"] else "")
                     for row in rows)
        (folder / "results.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (folder / "results.md").write_text(self.markdown(report), encoding="utf-8")
        return report

    @staticmethod
    def markdown(report: dict) -> str:
        head = [f"# Verification evidence", "",
                f"Generated {report['created_utc']}. "
                f"{report['passed']} of {report['total']} scenarios passed, {report['failed']} failed.", "",
                "| Result | Scenario | Media | LSB | Mode | Attack | Expected | Actual | Note |",
                "|---|---|---|---|---|---|---|---|---|"]
        body = [f"| {'PASS' if row['passed'] else 'FAIL'} | {row['name']} | {row['media_type']} | {row['lsb']} "
                f"| {row['mode']} | {row['attack'] or ''} | {row['expected']} "
                f"| {row['actual'] or row['error'] or ''} | {row['note']} |" for row in report["results"]]
        return "\n".join(head + body) + "\n"
