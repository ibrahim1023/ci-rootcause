from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.orchestration import PipelineRequest, run_pipeline
from src.github_app_comments import build_app_comment_body


class EvaluationError(RuntimeError):
    """Raised when eval loading or execution fails."""


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    case_type: str
    passed: bool
    checks: dict[str, bool]
    details: dict[str, Any]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EvaluationError(f"unable to read eval dataset {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"invalid eval dataset JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvaluationError("eval dataset root must be a JSON object")
    return payload


def _require_cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvaluationError("eval dataset must include a non-empty cases list")
    for item in cases:
        if not isinstance(item, dict):
            raise EvaluationError("each eval case must be a JSON object")
    return cases


def _contains(value: str, expected: str | None) -> bool:
    if expected is None or expected == "":
        return True
    return expected.lower() in value.lower()


def _evidence_matches(
    evidence: list[dict[str, Any]],
    *,
    expected_file: str | None,
    expected_line: int | None,
) -> bool:
    if expected_file is None and expected_line is None:
        return bool(evidence)
    for item in evidence:
        if expected_file is not None and str(item.get("file", "")) != expected_file:
            continue
        if expected_line is not None and item.get("line") != expected_line:
            continue
        return True
    return False


def _comment_is_actionable(comment: str) -> bool:
    required_fragments = (
        "## Likely cause",
        "## Evidence",
        "## Suggested fix",
        "## Confidence",
        "## App outcome",
    )
    return all(fragment in comment for fragment in required_fragments)


def _contains_all(value: str, expected: list[str]) -> bool:
    lowered = value.lower()
    return all(item.lower() in lowered for item in expected)


def _contains_none(value: str, forbidden: list[str]) -> bool:
    lowered = value.lower()
    return all(item.lower() not in lowered for item in forbidden)


def _run_pipeline_case(case: dict[str, Any], output_root: Path) -> EvalResult:
    case_id = str(case.get("id", "")).strip()
    if not case_id:
        raise EvaluationError("pipeline eval case missing id")
    expected = case.get("expected")
    if not isinstance(expected, dict):
        raise EvaluationError(f"pipeline eval case {case_id} missing expected object")

    request = PipelineRequest(
        raw_log=str(case.get("raw_log", "")),
        raw_diff=str(case.get("raw_diff", "")),
        timestamp="2026-01-01T00:00:00Z",
        commit=f"eval-{case_id}",
        run_id=f"eval_{case_id}",
        base_commit="eval-base",
        head_commit="eval-head",
        output_dir=str(output_root / case_id),
        create_fix_pr=False,
    )
    state = run_pipeline(request=request)
    classification_output = state.agent_outputs["failure_classification"]
    ranker_output = state.agent_outputs["root_cause_ranker"]
    reporter_output = state.agent_outputs["reporter"]
    fix_output = state.agent_outputs["fix_planner"]

    primary = ranker_output.get("primary_root_cause") or {}
    evidence = primary.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
    fix_steps = fix_output.get("fix_steps", [])
    first_fix = fix_steps[0] if isinstance(fix_steps, list) and fix_steps else {}
    suggested_fix = (
        str(first_fix.get("instruction", ""))
        if isinstance(first_fix, dict)
        else "No suggested fix generated."
    )
    comment = build_app_comment_body(
        classification=str(classification_output.get("classification", "")),
        confidence=float(ranker_output.get("confidence", 0.0)),
        primary_root_cause_title=str(primary.get("title", "")),
        run_id=request.run_id,
        rca_json_path=str(reporter_output.get("ci_rca_json_path", "")),
        rca_md_path=str(reporter_output.get("ci_rca_md_path", "")),
        confidence_reason=", ".join(str(item) for item in primary.get("confidence_reasons", [])),
        evidence=evidence,
        suggested_fix=suggested_fix,
        app_outcome="Comment-only RCA generated; fix PR creation was not requested.",
        pr_created=False,
        pr_failure_reason="create_fix_pr=false",
        pr_failure_reason_code="CREATE_FIX_PR_DISABLED",
    )

    expected_file = expected.get("primary_file")
    expected_line = expected.get("primary_line")
    checks = {
        "classification": str(classification_output.get("classification"))
        == expected.get("classification"),
        "top1_root_cause": _contains(
            str(primary.get("title", "")),
            expected.get("primary_contains"),
        )
        and _evidence_matches(
            evidence,
            expected_file=str(expected_file) if expected_file is not None else None,
            expected_line=int(expected_line) if isinstance(expected_line, int) else None,
        ),
        "evidence_grounded": bool(expected.get("evidence_grounded")) == bool(evidence),
        "comment_actionable": _comment_is_actionable(comment)
        if expected.get("comment_actionable")
        else True,
    }
    return EvalResult(
        case_id=case_id,
        case_type="pipeline",
        passed=all(checks.values()),
        checks=checks,
        details={
            "classification": classification_output.get("classification"),
            "primary_title": primary.get("title", ""),
            "confidence": ranker_output.get("confidence", 0.0),
            "comment_preview": comment,
        },
    )


def _run_diagnostic_case(case: dict[str, Any]) -> EvalResult:
    case_id = str(case.get("id", "")).strip()
    observed = case.get("observed")
    expected = case.get("expected")
    if not case_id or not isinstance(observed, dict) or not isinstance(expected, dict):
        raise EvaluationError("diagnostic eval case requires id, observed, and expected objects")
    checks = {
        "status": observed.get("status") == expected.get("status"),
        "reason_code": observed.get("reason_code") == expected.get("reason_code"),
        "reason_contains": _contains(
            str(observed.get("reason", "")),
            str(expected.get("reason_contains", "")),
        ),
    }
    return EvalResult(
        case_id=case_id,
        case_type="diagnostic",
        passed=all(checks.values()),
        checks=checks,
        details={"observed": observed},
    )


def _run_compression_case(case: dict[str, Any]) -> EvalResult:
    case_id = str(case.get("id", "")).strip()
    observed = str(case.get("observed", ""))
    expected = case.get("expected")
    if not case_id or not isinstance(expected, dict):
        raise EvaluationError("compression eval case requires id and expected object")

    required_signals = [
        str(item).strip() for item in expected.get("must_contain", []) if str(item).strip()
    ]
    dropped_noise = [
        str(item).strip() for item in expected.get("must_not_contain", []) if str(item).strip()
    ]
    checks = {
        "compression_signal_preservation": _contains_all(observed, required_signals),
        "compression_noise_pruning": _contains_none(observed, dropped_noise),
    }
    return EvalResult(
        case_id=case_id,
        case_type="compression",
        passed=all(checks.values()),
        checks=checks,
        details={
            "observed": observed,
            "required_signals": required_signals,
            "dropped_noise": dropped_noise,
        },
    )


def _rate(results: list[EvalResult], check_name: str) -> float | None:
    applicable = [result for result in results if check_name in result.checks]
    if not applicable:
        return None
    passed = sum(1 for result in applicable if result.checks[check_name])
    return round(passed / len(applicable), 4)


def _build_summary(results: list[EvalResult], thresholds: dict[str, Any]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    metrics = {
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "classification_accuracy": _rate(results, "classification"),
        "top1_root_cause_accuracy": _rate(results, "top1_root_cause"),
        "evidence_grounding_pass_rate": _rate(results, "evidence_grounded"),
        "comment_actionability_pass_rate": _rate(results, "comment_actionable"),
        "compression_signal_preservation_rate": _rate(results, "compression_signal_preservation"),
        "compression_noise_pruning_rate": _rate(results, "compression_noise_pruning"),
    }
    threshold_map = {
        "classification_accuracy": "classification_accuracy_min",
        "top1_root_cause_accuracy": "top1_root_cause_accuracy_min",
        "evidence_grounding_pass_rate": "evidence_grounding_pass_rate_min",
        "comment_actionability_pass_rate": "comment_actionability_pass_rate_min",
        "compression_signal_preservation_rate": "compression_signal_preservation_rate_min",
        "compression_noise_pruning_rate": "compression_noise_pruning_rate_min",
    }
    gates: dict[str, bool] = {}
    for metric_name, threshold_name in threshold_map.items():
        metric_value = metrics[metric_name]
        if threshold_name not in thresholds or metric_value is None:
            continue
        gates[metric_name] = metric_value >= float(thresholds.get(threshold_name, 0.0))
    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "metrics": metrics,
        "gates": gates,
        "passed": all(gates.values()) and passed == total,
    }


def run_eval_dataset(
    dataset_path: str = "evals/datasets/rca-quality.json",
    output_path: str = "evals/results/rca-quality.latest.json",
) -> dict[str, Any]:
    dataset = _load_json(Path(dataset_path))
    cases = _require_cases(dataset)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output_root = output.parent / "artifacts"

    results: list[EvalResult] = []
    for case in cases:
        case_type = str(case.get("type", "")).strip()
        if case_type == "pipeline":
            results.append(_run_pipeline_case(case, output_root=output_root))
        elif case_type == "diagnostic":
            results.append(_run_diagnostic_case(case))
        elif case_type == "compression":
            results.append(_run_compression_case(case))
        else:
            raise EvaluationError(f"unsupported eval case type: {case_type}")

    payload = {
        "suite_name": str(dataset.get("suite_name", "")),
        "summary": _build_summary(results, dict(dataset.get("thresholds", {}))),
        "cases": [
            {
                "id": result.case_id,
                "type": result.case_type,
                "passed": result.passed,
                "checks": result.checks,
                "details": result.details,
            }
            for result in results
        ],
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ci-rootcause behavior evals")
    parser.add_argument("--dataset", default="evals/datasets/rca-quality.json")
    parser.add_argument("--output", default="evals/results/rca-quality.latest.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = run_eval_dataset(dataset_path=args.dataset, output_path=args.output)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0 if result["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
