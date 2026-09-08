import argparse

from src.testing.demo_scenarios import build_demo_scenarios
from src.testing.runner import AutomatedTestRunner


def main():
    parser = argparse.ArgumentParser(description="Demonstrate runner reporting with canned results; no integration tests.")
    parser.add_argument("--output-dir", default="test-evidence")
    args = parser.parse_args()
    report = AutomatedTestRunner().run(build_demo_scenarios(), args.output_dir)
    print(f"Runner demo: {report['passed']}/{report['total']} passed; "
          f"evidence: {report['evidence_dir']}")
    return 1 if report["failed"] or not report["total"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
