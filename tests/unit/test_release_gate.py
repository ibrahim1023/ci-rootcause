from __future__ import annotations

from src.release_gate import evaluate_release_gates


def _base_report() -> dict[str, float]:
    return {
        "classification_match_rate": 1.0,
        "artifact_hash_reproducibility": 1.0,
        "confidence_reproducibility": 1.0,
        "completion_rate": 1.0,
    }


def _base_policy() -> dict:
    return {
        "stage": 1,
        "agentic_enabled": False,
        "stage2_allowed_classifications": ["TYPECHECK"],
        "thresholds": {
            "classification_match_rate_min": 0.95,
            "artifact_hash_reproducibility_min": 1.0,
            "confidence_reproducibility_min": 1.0,
            "completion_rate_min": 1.0,
            "agentic_validation_pass_rate_min": 1.0,
        },
    }


def test_release_gate_passes_for_stage_one_deterministic() -> None:
    errors = evaluate_release_gates(
        benchmark_report=_base_report(),
        policy=_base_policy(),
        validation_passed=True,
    )
    assert errors == []


def test_release_gate_fails_when_stage_two_scope_is_not_typecheck_only() -> None:
    policy = _base_policy()
    policy["stage"] = 2
    policy["agentic_enabled"] = True
    policy["stage2_allowed_classifications"] = ["TYPECHECK", "TEST"]

    errors = evaluate_release_gates(
        benchmark_report=_base_report(),
        policy=policy,
        validation_passed=True,
    )

    assert any("Stage 2 must restrict" in item for item in errors)


def test_release_gate_fails_on_threshold_regression() -> None:
    report = _base_report()
    report["classification_match_rate"] = 0.5

    errors = evaluate_release_gates(
        benchmark_report=report,
        policy=_base_policy(),
        validation_passed=True,
    )

    assert any("classification_match_rate" in item for item in errors)


def test_release_gate_requires_validation_for_agentic_enabled_release() -> None:
    policy = _base_policy()
    policy["stage"] = 2
    policy["agentic_enabled"] = True

    errors = evaluate_release_gates(
        benchmark_report=_base_report(),
        policy=policy,
        validation_passed=False,
    )

    assert any("agentic_validation_pass_rate" in item for item in errors)
