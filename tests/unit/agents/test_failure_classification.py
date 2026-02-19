import json
from pathlib import Path

import pytest

from src.agents.failure_classification import (
    evaluate_classification_accuracy,
    run_failure_classification,
)


@pytest.mark.parametrize(
    ("name", "failure_events", "dependency_flags", "expected_class", "expected_signal"),
    [
        (
            "infra-timeout",
            [{"error_signature": "connection reset", "log_excerpt": "network is unreachable"}],
            None,
            "INFRA",
            "pattern:connection reset",
        ),
        (
            "dependency-manifest-change",
            [{"error_signature": "build failed", "log_excerpt": "dependency conflict found"}],
            {"has_lockfile_change": False, "has_manifest_change": True},
            "DEPENDENCY",
            "flag:dependency_change",
        ),
        (
            "typecheck",
            [{"error_signature": "TS2345", "log_excerpt": "typescript error"}],
            None,
            "TYPECHECK",
            "pattern:ts2345",
        ),
        (
            "lint",
            [{"error_signature": "ruff failed", "log_excerpt": "style violation"}],
            None,
            "LINT",
            "pattern:ruff",
        ),
        (
            "test",
            [{"error_signature": "AssertionError", "log_excerpt": "pytest failed"}],
            None,
            "TEST",
            "pattern:assertionerror",
        ),
        (
            "build",
            [{"error_signature": "cannot compile", "log_excerpt": "build failed"}],
            None,
            "BUILD",
            "pattern:cannot compile",
        ),
    ],
)
def test_table_driven_classification_and_signals(
    name: str,
    failure_events: list[dict],
    dependency_flags: dict | None,
    expected_class: str,
    expected_signal: str,
) -> None:
    result = run_failure_classification(failure_events, dependency_flags)

    assert result["classification"] == expected_class, name
    assert expected_signal in result["signals"], name


def test_regression_ambiguous_log_falls_back_to_unknown() -> None:
    result = run_failure_classification(
        failure_events=[{"error_signature": "job failed", "log_excerpt": "step failed"}],
        dependency_change_flags=None,
    )

    assert result["classification"] == "UNKNOWN"
    assert "fallback:insufficient_classification_signals" in result["signals"]


def test_regression_priority_prefers_infra_over_test_like_text() -> None:
    result = run_failure_classification(
        failure_events=[
            {
                "error_signature": "pytest failed due to network is unreachable",
                "log_excerpt": "connection reset",
            }
        ],
        dependency_change_flags=None,
    )

    assert result["classification"] == "INFRA"


def test_fixture_accuracy_tracks_misclassification_rate() -> None:
    cases = json.loads(Path("fixtures/classification/cases.json").read_text())

    metrics = evaluate_classification_accuracy(cases)

    assert metrics["total"] == 7
    assert metrics["correct"] >= 6
    assert metrics["misclassification_rate"] <= 0.15
