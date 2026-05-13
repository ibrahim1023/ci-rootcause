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
            "typecheck-tsc",
            [{"error_signature": "tsc error TS7006", "log_excerpt": "cannot find name Foo"}],
            None,
            "TYPECHECK",
            "pattern:ts7006",
        ),
        (
            "mypy-arg-type",
            [
                {
                    "error_signature": (
                        "app.py:4: error: Argument 1 has incompatible type "
                        '"str"; expected "int" [arg-type]'
                    ),
                    "log_excerpt": "mypy app.py",
                }
            ],
            None,
            "TYPECHECK",
            "pattern:incompatible type",
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
            "test-vitest",
            [{"error_signature": "FAIL src/math.test.ts", "log_excerpt": "vitest failed"}],
            None,
            "TEST",
            "pattern:vitest",
        ),
        (
            "test-go",
            [{"error_signature": "--- FAIL: TestAdd", "log_excerpt": "go test ./..."}],
            None,
            "TEST",
            "pattern:--- fail:",
        ),
        (
            "build",
            [{"error_signature": "cannot compile", "log_excerpt": "build failed"}],
            None,
            "BUILD",
            "pattern:cannot compile",
        ),
        (
            "build-rust",
            [{"error_signature": "error[E0308]: mismatched types", "log_excerpt": "cargo build"}],
            None,
            "BUILD",
            "pattern:error[e",
        ),
        (
            "build-docker-buildx",
            [{"error_signature": "failed to solve", "log_excerpt": "docker buildx build ."}],
            None,
            "BUILD",
            "pattern:failed to solve",
        ),
        (
            "dependency-node-install",
            [
                {
                    "error_signature": "npm ERR! code ERESOLVE",
                    "log_excerpt": "unable to resolve dependency tree",
                }
            ],
            {"has_lockfile_change": True, "has_manifest_change": True},
            "DEPENDENCY",
            "pattern:npm err! code eresolve",
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
    assert result["flaky_test_detection"]["detected"] is False


def test_regression_ambiguous_log_falls_back_to_unknown() -> None:
    result = run_failure_classification(
        failure_events=[{"error_signature": "job failed", "log_excerpt": "step failed"}],
        dependency_change_flags=None,
    )

    assert result["classification"] == "UNKNOWN"
    assert "fallback:insufficient_classification_signals" in result["signals"]
    assert result["flaky_test_detection"]["detected"] is False


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


def test_flaky_test_detection_adds_flake_signals_for_test_classification() -> None:
    current = [
        {
            "error_signature": "AssertionError in tests/test_api.py::test_retry",
            "log_excerpt": "tests/test_api.py::test_retry failed",
        }
    ]
    historical_runs = [
        {
            "run_id": "gha_1",
            "failure_events": [
                {
                    "error_signature": "AssertionError in tests/test_api.py::test_retry",
                    "log_excerpt": "tests/test_api.py::test_retry failed",
                }
            ],
        },
        {
            "run_id": "gha_2",
            "failure_events": [
                {
                    "error_signature": "TimeoutError in tests/test_api.py::test_retry",
                    "log_excerpt": "tests/test_api.py::test_retry timed out",
                }
            ],
        },
    ]

    result = run_failure_classification(
        failure_events=current,
        dependency_change_flags=None,
        historical_runs=historical_runs,
    )

    assert result["classification"] == "TEST"
    assert "flake:historical_pattern_detected" in result["signals"]
    assert result["flaky_test_detection"]["detected"] is True
    assert result["flaky_test_detection"]["matched_failure_runs"] == 2
    assert result["flaky_test_detection"]["unique_failure_signatures"] >= 2


def test_flaky_detection_can_classify_as_test_without_primary_rule_match() -> None:
    current = [
        {
            "error_signature": "tests/test_jobs.py::test_queue_backoff",
            "log_excerpt": "intermittent failure observed",
        }
    ]
    historical_runs = [
        {
            "run_id": "gha_3",
            "failure_events": [
                {
                    "error_signature": "tests/test_jobs.py::test_queue_backoff",
                    "log_excerpt": "assertion mismatch",
                }
            ],
        },
        {
            "run_id": "gha_4",
            "failure_events": [
                {
                    "error_signature": "tests/test_jobs.py::test_queue_backoff",
                    "log_excerpt": "timed out",
                }
            ],
        },
    ]

    result = run_failure_classification(
        failure_events=current,
        dependency_change_flags=None,
        historical_runs=historical_runs,
    )

    assert result["classification"] == "TEST"
    assert "flake:historical_pattern_detected" in result["signals"]


def test_fixture_accuracy_tracks_misclassification_rate() -> None:
    cases = json.loads(Path("fixtures/classification/cases.json").read_text())

    metrics = evaluate_classification_accuracy(cases)

    assert metrics["total"] == 21
    assert metrics["correct"] >= 20
    assert metrics["misclassification_rate"] <= 0.1
