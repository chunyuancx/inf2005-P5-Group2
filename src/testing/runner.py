import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
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


class AutomatedTestRunner:
    def run(self, scenarios: list[Scenario], output_dir: str = "test-evidence") -> dict:
        rows = []
        for case in scenarios:
            row = {"name": case.name, "mode": case.mode,
                   "media_type": case.media_type, "lsb": case.lsb,
                   "expected": case.expected.value, "actual": None,
                   "passed": False, "statuses": {}, "error": None}
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
        folder = Path(mkdtemp(prefix="run-", dir=parent))
        report["evidence_dir"] = str(folder)
        (folder / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        lines = ["Expected vs actual verification evidence (mode recorded per case)"]
        lines.extend(f"{'PASS' if row['passed'] else 'FAIL'} {row['name']} "
                     f"mode={row['mode']} expected={row['expected']} actual={row['actual']} "
                     f"error={row['error']}" for row in rows)
        (folder / "results.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report
