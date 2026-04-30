from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from src.agents.pr_creation import ProviderAdapterError
from src.core.orchestration import PipelineRequest, run_pipeline


class BenchmarkSuiteError(RuntimeError):
    """Raised when benchmark suite loading or execution fails."""


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    description: str
    log_path: str
    diff_path: str
    timestamp: str
    commit: str
    run_id: str
    base_commit: str
    head_commit: str
    expected_classification: str | None = None
    expected_primary_root_cause_contains: str | None = None
    expected_primary_root_cause_file: str | None = None
    expected_primary_root_cause_line: int | None = None
    create_fix_pr: bool = False
    dry_run: bool = False
    execution_mode: str = "deterministic"
    llm_provider: str | None = None
    llm_model: str | None = None
    min_pr_confidence: float = 0.75
    validation_commands: tuple[str, ...] = ()
    typecheck_validation_commands: tuple[str, ...] = ()
    lint_validation_commands: tuple[str, ...] = ()
    test_validation_commands: tuple[str, ...] = ()
    validated_changes: tuple[dict[str, str], ...] = ()
    repo_fixture_files: tuple[dict[str, str], ...] = ()
    mocked_agentic_proposal_path: str | None = None


class _BenchmarkGitRunner:
    def run(self, args: list[str], cwd: Path) -> None:
        del cwd
        joined = " ".join(args)
        if "show-ref" in joined:
            raise ProviderAdapterError("Git command failed (show-ref): 1")


def _coerce_string_tuple(raw: Any, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        values = [line.strip() for line in raw.replace("\r\n", "\n").splitlines() if line.strip()]
        return tuple(values)
    if not isinstance(raw, list):
        raise BenchmarkSuiteError(f"Benchmark case field '{field_name}' must be a list of strings")
    return tuple(str(item).strip() for item in raw if str(item).strip())


def _coerce_file_records(raw: Any, field_name: str) -> tuple[dict[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise BenchmarkSuiteError(f"Benchmark case field '{field_name}' must be a list")
    records: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise BenchmarkSuiteError(f"Benchmark case field '{field_name}' items must be objects")
        file_path = _require_text(item.get("file", ""), f"{field_name}.file")
        content = str(item.get("content", ""))
        records.append({"file": file_path, "content": content})
    return tuple(records)


@contextmanager
def _patched_agentic_proposer(case: BenchmarkCase):
    if not case.mocked_agentic_proposal_path:
        yield
        return

    proposal_path = Path(case.mocked_agentic_proposal_path)
    try:
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BenchmarkSuiteError(
            f"Unable to read mocked agentic proposal '{proposal_path}': {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkSuiteError(
            f"Invalid JSON in mocked agentic proposal '{proposal_path}': {exc}"
        ) from exc
    if not isinstance(proposal, dict):
        raise BenchmarkSuiteError("Mocked agentic proposal must be a JSON object")

    def _propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        del self, payload
        return dict(proposal)

    with patch("src.core.orchestration.LocalLlmPatchProposer.propose", _propose):
        yield


@contextmanager
def _repo_fixture_dir(case: BenchmarkCase):
    if not case.repo_fixture_files:
        yield None
        return
    with TemporaryDirectory(prefix=f"ci-rootcause-bench-{case.case_id}-") as repo_dir:
        repo_root = Path(repo_dir)
        for item in case.repo_fixture_files:
            target = repo_root / item["file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item["content"], encoding="utf-8")
        yield str(repo_root)


def _require_text(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise BenchmarkSuiteError(f"Benchmark case field '{field_name}' is required")
    return text


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, int((len(ordered) - 1) * 0.95))
    return ordered[index]


def _rate_or_none(matches: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(matches / total, 4)


def _build_classification_confusion_matrix(
    case_results: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {}
    for item in case_results:
        expected = str(item.get("expected_classification") or "UNSPECIFIED")
        actual = str(item.get("classification") or "UNKNOWN")
        row = matrix.setdefault(expected, {})
        row[actual] = row.get(actual, 0) + 1
    return {
        expected: {actual: matrix[expected][actual] for actual in sorted(matrix[expected])}
        for expected in sorted(matrix)
    }


def _basic_log_baseline_classification(first_failure_event: dict[str, Any]) -> str:
    text = " ".join(
        [
            str(first_failure_event.get("error_signature", "")),
            str(first_failure_event.get("log_excerpt", "")),
            str(first_failure_event.get("stage", "")),
        ]
    ).lower()

    if any(
        token in text
        for token in (
            "timed out",
            "timeout",
            "connection reset",
            "network is unreachable",
            "runner lost",
        )
    ):
        return "INFRA"
    if re.search(r"\bts\d{4}\b", text) or "typescript" in text or "type error" in text:
        return "TYPECHECK"
    if any(token in text for token in ("ruff", "flake8", "eslint", "lint")):
        return "LINT"
    if any(token in text for token in ("build failed", "cannot compile", "compilation failed")):
        return "BUILD"
    if any(
        token in text for token in ("assertionerror", "test failed", "pytest", "jest", "failed:")
    ):
        return "TEST"
    return "UNKNOWN"


def _basic_log_baseline_root_cause(first_failure_event: dict[str, Any]) -> str:
    signature = str(first_failure_event.get("error_signature", "")).strip()
    excerpt = str(first_failure_event.get("log_excerpt", "")).strip()
    if signature:
        return signature
    if excerpt:
        return excerpt
    return "unknown failure"


def load_benchmark_suite(suite_path: str) -> tuple[str, list[BenchmarkCase]]:
    path = Path(suite_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BenchmarkSuiteError(f"Unable to read benchmark suite '{suite_path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkSuiteError(f"Invalid JSON in benchmark suite '{suite_path}': {exc}") from exc

    suite_name = _require_text(payload.get("suite_name", ""), "suite_name")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise BenchmarkSuiteError("Benchmark suite must include a non-empty 'cases' list")

    cases: list[BenchmarkCase] = []
    seen_ids: set[str] = set()
    for item in raw_cases:
        if not isinstance(item, dict):
            raise BenchmarkSuiteError("Each benchmark case must be a JSON object")

        case = BenchmarkCase(
            case_id=_require_text(item.get("case_id", ""), "case_id"),
            description=_require_text(item.get("description", ""), "description"),
            log_path=_require_text(item.get("log_path", ""), "log_path"),
            diff_path=_require_text(item.get("diff_path", ""), "diff_path"),
            timestamp=_require_text(item.get("timestamp", ""), "timestamp"),
            commit=_require_text(item.get("commit", ""), "commit"),
            run_id=_require_text(item.get("run_id", ""), "run_id"),
            base_commit=_require_text(item.get("base_commit", ""), "base_commit"),
            head_commit=_require_text(item.get("head_commit", ""), "head_commit"),
            expected_classification=(
                str(item.get("expected_classification")).strip()
                if item.get("expected_classification") is not None
                else None
            ),
            expected_primary_root_cause_contains=(
                str(item.get("expected_primary_root_cause_contains")).strip()
                if item.get("expected_primary_root_cause_contains") is not None
                else None
            ),
            expected_primary_root_cause_file=(
                str(item.get("expected_primary_root_cause_file")).strip()
                if item.get("expected_primary_root_cause_file") is not None
                else None
            ),
            expected_primary_root_cause_line=(
                int(item["expected_primary_root_cause_line"])
                if item.get("expected_primary_root_cause_line") is not None
                else None
            ),
            create_fix_pr=bool(item.get("create_fix_pr", False)),
            dry_run=bool(item.get("dry_run", False)),
            execution_mode=str(item.get("execution_mode", "deterministic")).strip()
            or "deterministic",
            llm_provider=(
                str(item.get("llm_provider")).strip()
                if item.get("llm_provider") is not None
                else None
            ),
            llm_model=(
                str(item.get("llm_model")).strip() if item.get("llm_model") is not None else None
            ),
            min_pr_confidence=(
                float(item.get("min_pr_confidence", 0.75))
                if item.get("min_pr_confidence") is not None
                else 0.75
            ),
            validation_commands=_coerce_string_tuple(
                item.get("validation_commands"), "validation_commands"
            ),
            typecheck_validation_commands=_coerce_string_tuple(
                item.get("typecheck_validation_commands"),
                "typecheck_validation_commands",
            ),
            lint_validation_commands=_coerce_string_tuple(
                item.get("lint_validation_commands"),
                "lint_validation_commands",
            ),
            test_validation_commands=_coerce_string_tuple(
                item.get("test_validation_commands"),
                "test_validation_commands",
            ),
            validated_changes=_coerce_file_records(
                item.get("validated_changes"),
                "validated_changes",
            ),
            repo_fixture_files=_coerce_file_records(
                item.get("repo_fixture_files"),
                "repo_fixture_files",
            ),
            mocked_agentic_proposal_path=(
                str(item.get("mocked_agentic_proposal_path")).strip()
                if item.get("mocked_agentic_proposal_path") is not None
                else None
            ),
        )

        if case.case_id in seen_ids:
            raise BenchmarkSuiteError(f"Duplicate benchmark case_id: {case.case_id}")
        seen_ids.add(case.case_id)
        cases.append(case)

    cases.sort(key=lambda case: case.case_id)
    return suite_name, cases


def run_benchmark_suite(
    suite_path: str,
    output_root: str,
    *,
    use_adk_runtime: bool | None = None,
    repeat_runs: int = 2,
) -> dict[str, Any]:
    if repeat_runs <= 0:
        raise BenchmarkSuiteError("repeat_runs must be > 0")

    suite_name, cases = load_benchmark_suite(suite_path)
    output_root_path = Path(output_root)
    output_root_path.mkdir(parents=True, exist_ok=True)

    case_results: list[dict[str, Any]] = []
    confidence_reproducible_count = 0
    artifact_hash_reproducible_count = 0
    for case in cases:
        log_path = Path(case.log_path)
        diff_path = Path(case.diff_path)

        if not log_path.exists():
            raise BenchmarkSuiteError(f"Benchmark case '{case.case_id}' log_path does not exist")
        if not diff_path.exists():
            raise BenchmarkSuiteError(f"Benchmark case '{case.case_id}' diff_path does not exist")

        case_output_dir = output_root_path / case.case_id
        confidence_values: list[float] = []
        timing_values: list[float] = []
        status_values: list[str] = []
        json_hash_values: list[str] = []
        md_hash_values: list[str] = []
        first_state: Any = None
        with _patched_agentic_proposer(case), _repo_fixture_dir(case) as repo_path:
            for _ in range(repeat_runs):
                request = PipelineRequest(
                    raw_log=log_path.read_text(encoding="utf-8"),
                    raw_diff=diff_path.read_text(encoding="utf-8"),
                    timestamp=case.timestamp,
                    commit=case.commit,
                    run_id=case.run_id,
                    base_commit=case.base_commit,
                    head_commit=case.head_commit,
                    output_dir=str(case_output_dir),
                    create_fix_pr=case.create_fix_pr,
                    dry_run=case.dry_run,
                    execution_mode=case.execution_mode,
                    llm_provider=case.llm_provider,
                    llm_model=case.llm_model,
                    min_pr_confidence=case.min_pr_confidence,
                    validation_commands=list(case.validation_commands),
                    typecheck_validation_commands=list(case.typecheck_validation_commands),
                    lint_validation_commands=list(case.lint_validation_commands),
                    test_validation_commands=list(case.test_validation_commands),
                    validated_changes=[dict(item) for item in case.validated_changes],
                    use_adk_runtime=use_adk_runtime,
                    pr_repo_path=repo_path,
                    pr_git_runner=_BenchmarkGitRunner() if case.create_fix_pr else None,
                )
                state = run_pipeline(request=request)
                reporter_output = state.agent_outputs.get("reporter", {})
                ranker_output = state.agent_outputs.get("root_cause_ranker", {})
                json_path = Path(str(reporter_output.get("ci_rca_json_path", "")))
                md_path = Path(str(reporter_output.get("ci_rca_md_path", "")))
                confidence_values.append(float(ranker_output.get("confidence", 0.0)))
                timing_values.append(float(state.pipeline_timing_ms))
                status_values.append(str(state.pipeline_status))
                json_hash_values.append(_sha256_file(json_path) if json_path.exists() else "")
                md_hash_values.append(_sha256_file(md_path) if md_path.exists() else "")
                if first_state is None:
                    first_state = state

        state = first_state
        log_output = state.agent_outputs.get("log_ingest", {})
        classification_output = state.agent_outputs.get("failure_classification", {})
        ranker_output = state.agent_outputs.get("root_cause_ranker", {})
        reporter_output = state.agent_outputs.get("reporter", {})
        fix_output = state.agent_outputs.get("fix_planner", {})
        pr_output = state.agent_outputs.get("pr_creation", {})
        first_failure_event = log_output.get("first_failure_event", {})
        if not isinstance(first_failure_event, dict):
            first_failure_event = {}

        actual_classification = str(classification_output.get("classification", "UNKNOWN"))
        primary_root_cause_title = str(
            (ranker_output.get("primary_root_cause") or {}).get("title", "")
        )
        primary_root_cause = ranker_output.get("primary_root_cause") or {}
        primary_evidence = primary_root_cause.get("evidence", [])
        actual_primary_file = None
        actual_primary_line = None
        if isinstance(primary_evidence, list) and primary_evidence:
            first_evidence = primary_evidence[0]
            if isinstance(first_evidence, dict):
                candidate_file = str(first_evidence.get("file", "")).strip()
                if candidate_file and candidate_file != "unknown":
                    actual_primary_file = candidate_file
                line_value = first_evidence.get("line")
                if isinstance(line_value, int) and line_value > 0:
                    actual_primary_line = line_value
        baseline_classification = _basic_log_baseline_classification(first_failure_event)
        baseline_root_cause_title = _basic_log_baseline_root_cause(first_failure_event)
        expected = case.expected_classification
        classification_match = expected is None or expected == actual_classification
        baseline_classification_match = expected is None or expected == baseline_classification
        expected_primary_contains = case.expected_primary_root_cause_contains
        primary_root_cause_match = (
            expected_primary_contains is None
            or expected_primary_contains.lower() in primary_root_cause_title.lower()
        )
        baseline_primary_root_cause_match = (
            expected_primary_contains is None
            or expected_primary_contains.lower() in baseline_root_cause_title.lower()
        )
        expected_primary_file = case.expected_primary_root_cause_file
        expected_primary_line = case.expected_primary_root_cause_line
        top1_root_cause_applicable = (
            expected_primary_file is not None or expected_primary_line is not None
        )
        top1_root_cause_match = (
            (actual_primary_file == expected_primary_file)
            and (actual_primary_line == expected_primary_line)
            if top1_root_cause_applicable
            else None
        )

        json_path = Path(str(reporter_output.get("ci_rca_json_path", "")))
        md_path = Path(str(reporter_output.get("ci_rca_md_path", "")))
        confidence_is_reproducible = len(set(confidence_values)) == 1
        if confidence_is_reproducible:
            confidence_reproducible_count += 1
        artifact_hash_is_reproducible = (
            len(set(json_hash_values)) == 1
            and len(set(md_hash_values)) == 1
            and bool(json_hash_values[0])
            and bool(md_hash_values[0])
        )
        if artifact_hash_is_reproducible:
            artifact_hash_reproducible_count += 1

        agentic_proposal = (
            fix_output.get("agentic_proposal", {}) if isinstance(fix_output, dict) else {}
        )
        agentic_proposal_applicable = isinstance(agentic_proposal, dict) and bool(agentic_proposal)
        agentic_proposal_valid = (
            bool(agentic_proposal.get("proposal_created", False))
            if agentic_proposal_applicable
            else None
        )
        validation_pass_applicable = False
        validation_passed = None
        validation_commands_used: list[str] = []
        if isinstance(pr_output, dict):
            validation_pass_applicable = bool(pr_output.get("validation_attempted", False))
            if validation_pass_applicable:
                validation_passed = bool(pr_output.get("validation_passed", False))
            validation_commands_used = [
                str(item).strip()
                for item in pr_output.get("validation_commands", [])
                if str(item).strip()
            ]

        case_results.append(
            {
                "case_id": case.case_id,
                "description": case.description,
                "pipeline_status": state.pipeline_status,
                "classification": actual_classification,
                "expected_classification": expected,
                "classification_match": classification_match,
                "baseline_classification": baseline_classification,
                "baseline_classification_match": baseline_classification_match,
                "expected_primary_root_cause_contains": expected_primary_contains,
                "primary_root_cause_match": primary_root_cause_match,
                "baseline_primary_root_cause_title": baseline_root_cause_title,
                "baseline_primary_root_cause_match": baseline_primary_root_cause_match,
                "expected_primary_root_cause_file": expected_primary_file,
                "expected_primary_root_cause_line": expected_primary_line,
                "actual_primary_root_cause_file": actual_primary_file,
                "actual_primary_root_cause_line": actual_primary_line,
                "top1_root_cause_applicable": top1_root_cause_applicable,
                "top1_root_cause_match": top1_root_cause_match,
                "confidence": float(ranker_output.get("confidence", 0.0)),
                "confidence_values": confidence_values,
                "confidence_is_reproducible": confidence_is_reproducible,
                "timing_values_ms": timing_values,
                "timing_spread_ms": (
                    round(max(timing_values) - min(timing_values), 3) if timing_values else 0.0
                ),
                "status_values": status_values,
                "artifact_json_hash_values": json_hash_values,
                "artifact_md_hash_values": md_hash_values,
                "artifact_hash_is_reproducible": artifact_hash_is_reproducible,
                "primary_root_cause_title": primary_root_cause_title,
                "trace_id": state.trace_id,
                "pipeline_timing_ms": state.pipeline_timing_ms,
                "ci_rca_json_sha256": _sha256_file(json_path) if json_path.exists() else "",
                "ci_rca_md_sha256": _sha256_file(md_path) if md_path.exists() else "",
                "agentic_proposal_applicable": agentic_proposal_applicable,
                "agentic_proposal_valid": agentic_proposal_valid,
                "validation_pass_applicable": validation_pass_applicable,
                "validation_passed": validation_passed,
                "validation_commands_used": validation_commands_used,
            }
        )

    completed = sum(1 for item in case_results if item["pipeline_status"] == "completed")
    matched = sum(1 for item in case_results if item["classification_match"])
    baseline_matched = sum(1 for item in case_results if item["baseline_classification_match"])
    root_cause_matched = sum(1 for item in case_results if item["primary_root_cause_match"])
    top1_root_cause_cases = sum(1 for item in case_results if item["top1_root_cause_applicable"])
    top1_root_cause_matches = sum(
        1 for item in case_results if item["top1_root_cause_match"] is True
    )
    agentic_proposal_cases = sum(1 for item in case_results if item["agentic_proposal_applicable"])
    agentic_proposal_valid_matches = sum(
        1 for item in case_results if item["agentic_proposal_valid"] is True
    )
    validation_pass_cases = sum(1 for item in case_results if item["validation_pass_applicable"])
    validation_pass_matches = sum(1 for item in case_results if item["validation_passed"] is True)
    baseline_root_cause_matched = sum(
        1 for item in case_results if item["baseline_primary_root_cause_match"]
    )
    total_cases = len(case_results)
    total_timing = sum(float(item["pipeline_timing_ms"]) for item in case_results)
    timing_samples = [float(item["pipeline_timing_ms"]) for item in case_results]
    mean_time_to_diagnosis_ms = round(total_timing / total_cases, 3) if total_cases else 0.0
    return {
        "suite_name": suite_name,
        "total_cases": total_cases,
        "completed_cases": completed,
        "completion_rate": round(completed / total_cases, 4) if total_cases else 0.0,
        "classification_matches": matched,
        "classification_match_rate": round(matched / total_cases, 4) if total_cases else 0.0,
        "baseline_classification_matches": baseline_matched,
        "baseline_classification_match_rate": (
            round(baseline_matched / total_cases, 4) if total_cases else 0.0
        ),
        "classification_match_lift": (
            round((matched - baseline_matched) / total_cases, 4) if total_cases else 0.0
        ),
        "classification_confusion_matrix": _build_classification_confusion_matrix(case_results),
        "primary_root_cause_matches": root_cause_matched,
        "primary_root_cause_accuracy": (
            round(root_cause_matched / total_cases, 4) if total_cases else 0.0
        ),
        "baseline_primary_root_cause_matches": baseline_root_cause_matched,
        "baseline_primary_root_cause_accuracy": (
            round(baseline_root_cause_matched / total_cases, 4) if total_cases else 0.0
        ),
        "primary_root_cause_accuracy_lift": (
            round((root_cause_matched - baseline_root_cause_matched) / total_cases, 4)
            if total_cases
            else 0.0
        ),
        "top1_root_cause_cases": top1_root_cause_cases,
        "top1_root_cause_matches": top1_root_cause_matches,
        "top1_root_cause_accuracy": (
            round(top1_root_cause_matches / top1_root_cause_cases, 4)
            if top1_root_cause_cases
            else 0.0
        ),
        "agentic_proposal_valid_cases": agentic_proposal_cases,
        "agentic_proposal_valid_matches": agentic_proposal_valid_matches,
        "agentic_proposal_valid_rate": _rate_or_none(
            agentic_proposal_valid_matches,
            agentic_proposal_cases,
        ),
        "validation_pass_cases": validation_pass_cases,
        "validation_pass_matches": validation_pass_matches,
        "validation_pass_rate": _rate_or_none(validation_pass_matches, validation_pass_cases),
        "confidence_reproducible_cases": confidence_reproducible_count,
        "confidence_reproducibility": (
            round(confidence_reproducible_count / total_cases, 4) if total_cases else 0.0
        ),
        "artifact_hash_reproducible_cases": artifact_hash_reproducible_count,
        "artifact_hash_reproducibility": (
            round(artifact_hash_reproducible_count / total_cases, 4) if total_cases else 0.0
        ),
        "mean_time_to_diagnosis_ms": mean_time_to_diagnosis_ms,
        "median_time_to_diagnosis_ms": round(_median(timing_samples), 3),
        "p95_time_to_diagnosis_ms": round(_p95(timing_samples), 3),
        "cases": case_results,
    }
