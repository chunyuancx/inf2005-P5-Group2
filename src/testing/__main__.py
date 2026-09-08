import argparse

from src.testing.mock_scenarios import build_mock_scenarios
from src.testing.runner import AutomatedTestRunner


def main():
    parser = argparse.ArgumentParser(description="Run Member 6 MOCK scenarios and save evidence.")
    parser.add_argument("--output-dir", default="test-evidence")
    args = parser.parse_args()
    report = AutomatedTestRunner().run(build_mock_scenarios(), args.output_dir)
    print(f"MOCK scenarios: {report['passed']}/{report['total']} passed; "
          f"evidence: {report['evidence_dir']}")
    return 1 if report["failed"] or not report["total"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
