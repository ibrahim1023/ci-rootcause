from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class ReleaseGateError(RuntimeError):
    """Raised when release quality gates fail."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReleaseGateError(f"Unable to read JSON file '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseGateError(f"Invalid JSON in '{path}': {exc}") from exc
    if not isinstance(raw, dict):
        raise ReleaseGateError(f"Expected JSON object in '{path}'")
    return raw


def _require_threshold(
    *,
    report: dict[str, Any],
    key: str,
    minimum: float,
    errors: list[str],
) -> None:
    value = report.get(key)
    if not isinstance(value, (int, float)):
        errors.append(f"benchmark report missing numeric field: {key}")
        return
    if float(value) < minimum:
        errors.append(f"{key}={float(value):.4f} is below required minimum {minimum:.4f}")


def evaluate_release_gates(
    *,
    benchmark_report: dict[str, Any],
    policy: dict[str, Any],
    validation_passed: bool,
) -> list[str]:
    errors: list[str] = []

    stage = int(policy.get("stage", 1))
    agentic_enabled = bool(policy.get("agentic_enabled", False))

    if stage not in {1, 2, 3}:
        errors.append(f"Unsupported agentic release stage: {stage}")

    if stage == 1 and agentic_enabled:
        errors.append("Stage 1 requires agentic_enabled=false")
    if stage in {2, 3} and not agentic_enabled:
        errors.append(f"Stage {stage} requires agentic_enabled=true")

    if stage == 2:
        rollout_classes = policy.get("stage2_allowed_classifications", [])
        if rollout_classes != ["TYPECHECK"]:
            errors.append("Stage 2 must restrict stage2_allowed_classifications to ['TYPECHECK']")

    thresholds = policy.get("thresholds", {})
    if not isinstance(thresholds, dict):
        errors.append("policy.thresholds must be an object")
        return errors

    _require_threshold(
        report=benchmark_report,
        key="classification_match_rate",
        minimum=float(thresholds.get("classification_match_rate_min", 0.0)),
        errors=errors,
    )
    _require_threshold(
        report=benchmark_report,
        key="artifact_hash_reproducibility",
        minimum=float(thresholds.get("artifact_hash_reproducibility_min", 0.0)),
        errors=errors,
    )
    _require_threshold(
        report=benchmark_report,
        key="confidence_reproducibility",
        minimum=float(thresholds.get("confidence_reproducibility_min", 0.0)),
        errors=errors,
    )
    _require_threshold(
        report=benchmark_report,
        key="completion_rate",
        minimum=float(thresholds.get("completion_rate_min", 0.0)),
        errors=errors,
    )

    if agentic_enabled:
        validation_min = float(thresholds.get("agentic_validation_pass_rate_min", 1.0))
        validation_rate = 1.0 if validation_passed else 0.0
        if validation_rate < validation_min:
            errors.append(
                "agentic_validation_pass_rate=0.0000 is below required minimum "
                f"{validation_min:.4f}"
            )

    return errors


def run_release_gates(
    *,
    benchmark_path: Path,
    policy_path: Path,
    validation_passed: bool,
) -> None:
    benchmark_report = _load_json(benchmark_path)
    policy = _load_json(policy_path)
    errors = evaluate_release_gates(
        benchmark_report=benchmark_report,
        policy=policy,
        validation_passed=validation_passed,
    )
    if errors:
        raise ReleaseGateError("Release quality gate failed:\n- " + "\n- ".join(errors))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate ci-rootcause release quality gates")
    parser.add_argument(
        "--benchmark",
        default="docs/reports/mvp-benchmark-report.json",
        help="Path to benchmark report JSON.",
    )
    parser.add_argument(
        "--policy",
        default="config/agentic-release-policy.json",
        help="Path to release gate policy JSON.",
    )
    parser.add_argument(
        "--validation-passed",
        action="store_true",
        help="Set when release validation commands already passed in CI.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        run_release_gates(
            benchmark_path=Path(args.benchmark),
            policy_path=Path(args.policy),
            validation_passed=bool(args.validation_passed),
        )
    except ReleaseGateError as exc:
        print(exc)
        return 2
    print("Release quality gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
