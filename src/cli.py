from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.core.input_parsing import (
    InputParsingError,
    load_historical_runs,
    load_simple_config,
    load_validated_changes,
    parse_agentic_provider_config,
    parse_bool,
    parse_confidence_threshold,
    parse_execution_mode,
    parse_positive_int,
    read_text_file,
)
from src.core.orchestration import PipelineRequest, run_pipeline


class CLIError(RuntimeError):
    """Raised when CLI input validation fails."""


SAFE_ROLLOUT_PROFILE = "safe-github-rollout"
DEFAULT_EXECUTION_MODE = "deterministic"


def _coalesce(primary: str | None, fallback: str | None = None) -> str:
    if primary is not None and str(primary).strip():
        return str(primary).strip()
    if fallback is not None and str(fallback).strip():
        return str(fallback).strip()
    return ""


def _read_input_text(path_value: str, *, input_name: str) -> str:
    if path_value == "-":
        data = sys.stdin.read()
        if not data.strip():
            raise CLIError(f"stdin for {input_name} is empty")
        return data
    return read_text_file(Path(path_value))


def _parse_validation_commands(value: str) -> list[str]:
    if not value.strip():
        return []
    normalized = value.replace("\r\n", "\n").replace(";", "\n")
    return [line.strip() for line in normalized.splitlines() if line.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ci-rootcause",
        description="Deterministic CI root-cause analysis runner.",
    )
    parser.add_argument(
        "--config-path",
        default=None,
        help="Optional simple config file (key: value) for local CLI execution.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help=(f"Optional rollout profile. Supported values: '{SAFE_ROLLOUT_PROFILE}'."),
    )
    parser.add_argument(
        "--mode",
        default=None,
        help="Execution mode: deterministic | agentic_assist | agentic_full.",
    )
    parser.add_argument(
        "--enable-agentic-full",
        action="store_true",
        help="Explicitly allow agentic_full mode.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Agentic provider: openai | gemini | anthropic | local. Default: local.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional provider model id override.",
    )
    parser.add_argument(
        "--provider-api-key",
        default=None,
        help="Optional API key for hosted agentic providers (required in agentic modes).",
    )
    parser.add_argument(
        "--log-path",
        required=False,
        default=None,
        help="Path to CI log text input. Use '-' to read from stdin.",
    )
    parser.add_argument(
        "--diff-path",
        required=False,
        default=None,
        help="Path to git diff text input. Use '-' to read from stdin.",
    )
    parser.add_argument(
        "--output-dir",
        required=False,
        default=None,
        help="Directory for RCA artifacts.",
    )

    parser.add_argument(
        "--timestamp",
        required=False,
        default=None,
        help="Run timestamp (ISO-8601).",
    )
    parser.add_argument(
        "--commit",
        required=False,
        default=None,
        help="Head commit SHA for analyzed run.",
    )
    parser.add_argument("--run-id", required=False, default=None, help="CI run identifier.")
    parser.add_argument(
        "--base-commit",
        required=False,
        default=None,
        help="Diff base commit SHA/ref.",
    )
    parser.add_argument(
        "--head-commit",
        required=False,
        default=None,
        help="Diff head commit SHA/ref.",
    )

    parser.add_argument("--repository", default=None, help="Repository in owner/repo format.")
    parser.add_argument("--target-branch", default=None, help="Target base branch.")
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
        default=None,
        help=(
            "Minimum confidence (0.0-1.0) required to allow guarded fix PR creation. Default: 0.75."
        ),
    )
    parser.add_argument(
        "--max-fix-files",
        default=None,
        help="Maximum number of files allowed in a guarded fix PR. Default: 5.",
    )
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="Enable offline-only mode (skip any remote PR creation/network calls).",
    )
    parser.add_argument(
        "--validation-commands",
        default=None,
        help=("Optional validation commands for agentic PR gating. Use ';' or newline separators."),
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
        config = (
            load_simple_config(Path(args.config_path), missing_ok=False) if args.config_path else {}
        )

        log_path = _coalesce(args.log_path, config.get("log_path"))
        diff_path = _coalesce(args.diff_path, config.get("diff_path"))
        output_dir = _coalesce(args.output_dir, config.get("output_dir"))
        timestamp = _coalesce(args.timestamp, config.get("timestamp"))
        commit = _coalesce(args.commit, config.get("commit"))
        run_id = _coalesce(args.run_id, config.get("run_id"))
        base_commit = _coalesce(args.base_commit, config.get("base_commit"))
        head_commit = _coalesce(args.head_commit, config.get("head_commit"))
        repository = _coalesce(args.repository, config.get("repository"))
        target_branch = _coalesce(args.target_branch, config.get("target_branch")) or "main"
        profile = _coalesce(args.profile, config.get("profile"))
        if profile and profile != SAFE_ROLLOUT_PROFILE:
            raise CLIError(f"Unsupported profile '{profile}'. Expected '{SAFE_ROLLOUT_PROFILE}'.")
        execution_mode = parse_execution_mode(
            _coalesce(args.mode, config.get("mode")) or DEFAULT_EXECUTION_MODE,
            name="mode",
        )
        enable_agentic_full = bool(args.enable_agentic_full)
        if not enable_agentic_full and "enable_agentic_full" in config:
            enable_agentic_full = parse_bool(
                str(config.get("enable_agentic_full", "")),
                name="enable_agentic_full",
            )
        if execution_mode.value == "agentic_full" and not enable_agentic_full:
            raise CLIError(
                "agentic_full requires explicit opt-in via --enable-agentic-full "
                "or config enable_agentic_full=true"
            )
        provider_config = parse_agentic_provider_config(
            execution_mode=execution_mode,
            provider_value=_coalesce(args.provider, config.get("provider")),
            model_value=_coalesce(args.model, config.get("model")),
            api_key_value=_coalesce(args.provider_api_key, config.get("provider_api_key")),
        )
        validation_commands = _parse_validation_commands(
            _coalesce(args.validation_commands, config.get("validation_commands"))
        )

        create_fix_pr = bool(args.create_fix_pr)
        if not create_fix_pr and "create_fix_pr" in config:
            create_fix_pr = parse_bool(str(config.get("create_fix_pr", "")), name="create_fix_pr")

        min_pr_confidence_raw = (
            _coalesce(
                args.min_pr_confidence,
                config.get("min_pr_confidence"),
            )
            or "0.75"
        )
        min_pr_confidence = parse_confidence_threshold(
            min_pr_confidence_raw,
            name="min_pr_confidence",
        )
        max_fix_files_raw = _coalesce(args.max_fix_files, config.get("max_fix_files")) or "5"
        max_fix_files = parse_positive_int(
            max_fix_files_raw,
            name="max_fix_files",
        )
        if profile == SAFE_ROLLOUT_PROFILE and min_pr_confidence < 0.9:
            min_pr_confidence = 0.9
        if profile == SAFE_ROLLOUT_PROFILE and execution_mode.value == "agentic_full":
            raise CLIError("safe-github-rollout does not allow mode=agentic_full")

        offline_only = bool(args.offline_only)
        if not offline_only and "offline_only" in config:
            offline_only = parse_bool(str(config.get("offline_only", "")), name="offline_only")

        required_fields = {
            "log_path": log_path,
            "diff_path": diff_path,
            "output_dir": output_dir,
            "timestamp": timestamp,
            "commit": commit,
            "run_id": run_id,
            "base_commit": base_commit,
            "head_commit": head_commit,
        }
        missing = [name for name, value in required_fields.items() if not value]
        if missing:
            raise CLIError(
                "Missing required CLI inputs (provide flags or config_path values): "
                + ", ".join(sorted(missing))
            )
        if log_path == "-" and diff_path == "-":
            raise CLIError("Only one of --log-path/--diff-path may use '-' stdin input")

        raw_log = _read_input_text(log_path, input_name="log_path")
        raw_diff = _read_input_text(diff_path, input_name="diff_path")
        validated_changes = load_validated_changes(
            Path(args.validated_changes_path) if args.validated_changes_path else None,
            expected_list_message="Validated changes payload must be a JSON list",
        )
        historical_runs = load_historical_runs(
            Path(args.historical_runs_path) if args.historical_runs_path else None,
            expected_list_message="Historical runs payload must be a JSON list",
        )

        request = PipelineRequest(
            raw_log=raw_log,
            raw_diff=raw_diff,
            timestamp=timestamp,
            commit=commit,
            run_id=run_id,
            base_commit=base_commit,
            head_commit=head_commit,
            output_dir=output_dir,
            create_fix_pr=create_fix_pr,
            dry_run=bool(args.dry_run),
            github_token=str(args.github_token) if args.github_token else None,
            repository=repository or None,
            target_branch=target_branch or None,
            validated_changes=validated_changes,
            fail_fast=bool(args.fail_fast),
            historical_runs=historical_runs,
            min_pr_confidence=min_pr_confidence,
            max_fix_files=max_fix_files,
            offline_only=offline_only,
            execution_mode=execution_mode.value,
            llm_provider=provider_config.provider.value,
            llm_model=provider_config.model,
            llm_api_key=provider_config.api_key,
            validation_commands=validation_commands,
            ci_provider=str(args.ci_provider).strip() or None,
            provider_adapter=str(args.provider_adapter).strip() or None,
        )
        state = run_pipeline(request=request)
    except InputParsingError as exc:
        print(f"ci-rootcause CLI error: {exc}")
        return 2
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
