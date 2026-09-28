"""Run the automated attack suite and write evidence.

    python -m src.testing                       # bundled samples, LSB 1, both modes
    python -m src.testing --lsb 1 --lsb 4       # more depths
    python -m src.testing --cover photo.png     # your own covers instead
    python -m src.testing --demo                # canned reporting demo only
"""
import argparse
from pathlib import Path

from src.testing.demo_scenarios import build_demo_scenarios
from src.testing.runner import AutomatedTestRunner
from src.testing.scenarios import DEFAULT_COVERS, build_real_scenarios


def main(argv=None):
    parser = argparse.ArgumentParser(description="Attack simulation suite with expected-versus-actual evidence.")
    parser.add_argument("--output-dir", default="test-evidence")
    parser.add_argument("--cover", action="append", type=Path, help="cover file to protect and attack (repeatable)")
    parser.add_argument("--lsb", action="append", type=int, help="LSB depth to test (repeatable, default 1)")
    parser.add_argument("--mode", choices=("manual", "auto", "both"), default="both",
                        help="start-location mode(s) to cover")
    parser.add_argument("--demo", action="store_true", help="run the canned reporting demo instead of real attacks")
    args = parser.parse_args(argv)
    if args.demo:
        scenarios = build_demo_scenarios()
    else:
        modes = ("manual", "auto") if args.mode == "both" else (args.mode,)
        scenarios = build_real_scenarios(args.output_dir, covers=args.cover or DEFAULT_COVERS,
                                         lsbs=tuple(args.lsb or (1,)), modes=modes)
    report = AutomatedTestRunner().run(scenarios, args.output_dir)
    for row in report["results"]:
        if not row["passed"]:
            print(f"FAIL {row['name']}: expected {row['expected']}, got {row['actual'] or row['error']}")
    print(f"{'Runner demo' if args.demo else 'Attack suite'}: {report['passed']}/{report['total']} passed; "
          f"evidence: {report['evidence_dir']}")
    return 1 if report["failed"] or not report["total"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
