"""Canned results for demonstrating reporting, without calling any services."""
from src.models import Verdict, VerificationResult
from src.testing.runner import Scenario


def build_demo_scenarios() -> list[Scenario]:
    return [
        Scenario("reporting/success", Verdict.AUTHENTIC,
                 lambda: VerificationResult(Verdict.AUTHENTIC, "Canned result; no media verified."),
                 "none", 0, mode="runner-demo"),
        Scenario("reporting/unavailable", Verdict.CANNOT_VERIFY,
                 lambda: VerificationResult(Verdict.CANNOT_VERIFY, "Canned unavailable result."),
                 "none", 0, mode="runner-demo"),
    ]
