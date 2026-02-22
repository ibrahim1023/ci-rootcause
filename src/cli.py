from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.core.orchestration import PipelineRequest, run_pipeline


class CLIError(RuntimeError):
    """Raised when CLI input validation fails."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CLIError(f"Unable to read file '{path}': {exc}") from exc


def _load_validated_changes(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CLIError(f"Unable to read validated changes file '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CLIError(f"Invalid JSON in validated changes file '{path}': {exc}") from exc

    if not isinstance(raw, list):
        raise CLIError("Validated changes payload must be a JSON list")

    normalized: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise CLIError("Each validated change must be a JSON object")
        file_path = str(item.get("file", "")).strip()
        content = item.get("content")
        if not file_path or not isinstance(content, str):
            raise CLIError("Each validated change must include string fields: file, content")
        normalized.append({"file": file_path, "content": content})

    return normalized


def _load_historical_runs(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CLIError(f"Unable to read historical runs file '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CLIError(f"Invalid JSON in historical runs file '{path}': {exc}") from exc

    if not isinstance(raw, list):
        raise CLIError("Historical runs payload must be a JSON list")

    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise CLIError("Each historical run must be a JSON object")
        failure_events = item.get("failure_events", [])
        if failure_events is not None and not isinstance(failure_events, list):
            raise CLIError("Each historical run field 'failure_events' must be a JSON list")
        normalized.append(dict(item))
    return normalized


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ci-rootcause",
        description="Deterministic CI root-cause analysis runner.",
    )
    parser.add_argument("--log-path", required=True, help="Path to CI log text input.")
    parser.add_argument("--diff-path", required=True, help="Path to git diff text input.")
    parser.add_argument("--output-dir", required=True, help="Directory for RCA artifacts.")

    parser.add_argument("--timestamp", required=True, help="Run timestamp (ISO-8601).")
    parser.add_argument("--commit", required=True, help="Head commit SHA for analyzed run.")
    parser.add_argument("--run-id", required=True, help="CI run identifier.")
    parser.add_argument("--base-commit", required=True, help="Diff base commit SHA/ref.")
    parser.add_argument("--head-commit", required=True, help="Diff head commit SHA/ref.")

    parser.add_argument("--repository", default="", help="Repository in owner/repo format.")
    parser.add_argument("--target-branch", default="main", help="Target base branch.")
    parser.add_argument(
        "--ci-provider",
        default=None,
        help="Optional CI provider override (for example: github-actions, gitlab-ci).",
    )
    parser.add_argument(
        "--provider-adapter",
        default=None,
        help="Optional provider adapter override (for example: github, gitlab).",
    )
    parser.add_argument(
        "--validated-changes-path",
        default=None,
        help="Optional JSON file containing validated changes for guarded PR creation.",
    )
    parser.add_argument(
        "--historical-runs-path",
        default=None,
        help=(
            "Optional JSON file containing historical failed run events for deterministic flaky "
            "test detection."
        ),
    )

    parser.add_argument(
        "--create-fix-pr",
        action="store_true",
        help="Enable guarded fix PR creation flow.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute PR flow without creating a remote PR.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop pipeline immediately on first agent failure.",
    )
    parser.add_argument(
        "--github-token",
        default=None,
        help="GitHub token for remote PR operations when create-fix-pr is enabled.",
    )
    parser.add_argument(
        "--min-pr-confidence",
        default="0.75",
        help=(
            "Minimum confidence (0.0-1.0) required to allow guarded fix PR creation. "
            "Default: 0.75."
        ),
    )

    return parser


def _build_summary(state: Any) -> dict[str, Any]:
    classification = "UNKNOWN"
    confidence = 0.0
    title = ""
    json_path = ""
    md_path = ""
    pr_created = False
    pr_url = None
    pr_number = None

    classification_output = state.agent_outputs.get("failure_classification", {})
    ranker_output = state.agent_outputs.get("root_cause_ranker", {})
    reporter_output = state.agent_outputs.get("reporter", {})
    pr_output = state.agent_outputs.get("pr_creation", {})

    if isinstance(classification_output, dict):
        classification = str(classification_output.get("classification", classification))
    if isinstance(ranker_output, dict):
        confidence = float(ranker_output.get("confidence", confidence))
        primary = ranker_output.get("primary_root_cause")
        if isinstance(primary, dict):
            title = str(primary.get("title", title))
    if isinstance(reporter_output, dict):
        json_path = str(reporter_output.get("ci_rca_json_path", json_path))
        md_path = str(reporter_output.get("ci_rca_md_path", md_path))
    if isinstance(pr_output, dict):
        pr_created = bool(pr_output.get("pr_created", pr_created))
        pr_url = pr_output.get("pr_url")
        pr_number = pr_output.get("pr_number")

    return {
        "pipeline_status": state.pipeline_status,
        "classification": classification,
        "confidence": confidence,
        "primary_root_cause_title": title,
        "rca_json_path": json_path,
        "rca_md_path": md_path,
        "pr_created": pr_created,
        "pr_url": pr_url,
        "pr_number": pr_number,
        "failures": state.failures,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        raw_log = _read_text(Path(args.log_path))
        raw_diff = _read_text(Path(args.diff_path))
        validated_changes = _load_validated_changes(
            Path(args.validated_changes_path) if args.validated_changes_path else None
        )
        historical_runs = _load_historical_runs(
            Path(args.historical_runs_path) if args.historical_runs_path else None
        )

        request = PipelineRequest(
            raw_log=raw_log,
            raw_diff=raw_diff,
            timestamp=str(args.timestamp),
            commit=str(args.commit),
            run_id=str(args.run_id),
            base_commit=str(args.base_commit),
            head_commit=str(args.head_commit),
            output_dir=str(args.output_dir),
            create_fix_pr=bool(args.create_fix_pr),
            dry_run=bool(args.dry_run),
            github_token=str(args.github_token) if args.github_token else None,
            repository=str(args.repository) or None,
            target_branch=str(args.target_branch) or None,
            validated_changes=validated_changes,
            fail_fast=bool(args.fail_fast),
            historical_runs=historical_runs,
            min_pr_confidence=float(args.min_pr_confidence),
            ci_provider=str(args.ci_provider).strip() or None,
            provider_adapter=str(args.provider_adapter).strip() or None,
        )
        state = run_pipeline(request=request)
    except Exception as exc:
        print(f"ci-rootcause CLI error: {exc}")
        return 2

    summary = _build_summary(state=state)
    print(json.dumps(summary, sort_keys=True))

    if state.pipeline_status in {"completed", "partial"}:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
