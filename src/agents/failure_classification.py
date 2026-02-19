from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.contracts.models import FailureClass


@dataclass(frozen=True)
class ClassificationResult:
    classification: FailureClass
    signals: list[str]


RULE_PRIORITY: list[FailureClass] = [
    FailureClass.INFRA,
    FailureClass.DEPENDENCY,
    FailureClass.SECURITY,
    FailureClass.TYPECHECK,
    FailureClass.LINT,
    FailureClass.TEST,
    FailureClass.BUILD,
]

RULE_PATTERNS: dict[FailureClass, tuple[str, ...]] = {
    FailureClass.INFRA: (
        "timed out",
        "timeout",
        "connection reset",
        "temporary failure in name resolution",
        "service unavailable",
        "runner lost",
        "network is unreachable",
    ),
    FailureClass.DEPENDENCY: (
        "modulenotfounderror",
        "cannot find module",
        "no matching distribution found",
        "dependency conflict",
        "version solving failed",
        "lockfile",
    ),
    FailureClass.SECURITY: (
        "vulnerability",
        "security",
        "denied by policy",
        "secret detected",
    ),
    FailureClass.TYPECHECK: (
        "mypy",
        "pyright",
        "type error",
        "incompatible types",
        "typescript error",
        "ts2322",
        "ts2345",
    ),
    FailureClass.LINT: (
        "flake8",
        "ruff",
        "eslint",
        "pylint",
        "lint",
        "style violation",
    ),
    FailureClass.TEST: (
        "assertionerror",
        "failed: ",
        "test failed",
        "expected",
        "pytest",
        "jest",
    ),
    FailureClass.BUILD: (
        "compilation failed",
        "build failed",
        "cannot compile",
        "c compiler",
        "linker error",
    ),
}


def _collect_text(failure_events: Iterable[dict]) -> str:
    chunks: list[str] = []
    for event in failure_events:
        chunks.append(str(event.get("error_signature", "")))
        chunks.append(str(event.get("log_excerpt", "")))
    return "\n".join(chunks).lower()


def run_failure_classification(
    failure_events: list[dict],
    dependency_change_flags: dict | None = None,
) -> dict:
    signals: list[str] = []
    text = _collect_text(failure_events)

    if dependency_change_flags:
        if dependency_change_flags.get("has_lockfile_change"):
            signals.append("dep:lockfile_changed")
        if dependency_change_flags.get("has_manifest_change"):
            signals.append("dep:manifest_changed")

    matched_by_class: dict[FailureClass, list[str]] = {
        failure_class: [] for failure_class in RULE_PRIORITY
    }

    for failure_class in RULE_PRIORITY:
        patterns = RULE_PATTERNS[failure_class]
        for pattern in patterns:
            if pattern in text:
                matched_by_class[failure_class].append(f"pattern:{pattern}")

    if dependency_change_flags and (
        dependency_change_flags.get("has_lockfile_change")
        or dependency_change_flags.get("has_manifest_change")
    ):
        matched_by_class[FailureClass.DEPENDENCY].append("flag:dependency_change")

    for failure_class in RULE_PRIORITY:
        class_signals = matched_by_class[failure_class]
        if class_signals:
            signals.extend(class_signals)
            return {
                "classification": failure_class.value,
                "signals": signals,
            }

    return {
        "classification": FailureClass.UNKNOWN.value,
        "signals": ["fallback:insufficient_classification_signals"],
    }


def evaluate_classification_accuracy(cases: list[dict]) -> dict:
    total = len(cases)
    if total == 0:
        return {"total": 0, "correct": 0, "accuracy": 0.0, "misclassification_rate": 0.0}

    correct = 0
    errors: list[dict] = []

    for case in cases:
        result = run_failure_classification(
            failure_events=case["failure_events"],
            dependency_change_flags=case.get("dependency_change_flags"),
        )
        expected = case["expected_classification"]
        actual = result["classification"]
        if actual == expected:
            correct += 1
        else:
            errors.append(
                {"name": case.get("name", "unknown"), "expected": expected, "actual": actual}
            )

    accuracy = correct / total
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "misclassification_rate": round(1 - accuracy, 4),
        "errors": errors,
    }
