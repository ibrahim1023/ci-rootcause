from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.orchestration import PipelineRequest, run_pipeline
from src.github_app_ingestion import GitHubAppIngestionError, collect_workflow_run_inputs
from src.github_app_webhook import (
    GitHubWebhookError,
    handle_github_app_webhook,
)


@dataclass(frozen=True)
class GitHubAppRepoConfig:
    create_fix_pr: bool = False
    min_pr_confidence: float = 0.75
    execution_mode: str = "deterministic"
    output_dir: str = "artifacts/app"


def _pipeline_summary(state: Any) -> dict[str, Any]:
    classification = "UNKNOWN"
    confidence = 0.0
    title = ""
    json_path = ""
    md_path = ""
    pr_created = False
    pr_failure_reason_code = ""
    pr_failure_reason = ""

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
        if pr_output.get("failure_reason_code"):
            pr_failure_reason_code = str(pr_output["failure_reason_code"])
        if pr_output.get("failure_reason"):
            pr_failure_reason = str(pr_output["failure_reason"])

    return {
        "classification": classification,
        "confidence": confidence,
        "primary_root_cause_title": title,
        "rca_json_path": json_path,
        "rca_md_path": md_path,
        "pr_created": pr_created,
        "pr_failure_reason_code": pr_failure_reason_code,
        "pr_failure_reason": pr_failure_reason,
    }


def process_github_app_webhook(
    *,
    headers: Mapping[str, str],
    body: bytes,
    webhook_secret: str,
    github_token: str,
    repo_config: GitHubAppRepoConfig | None = None,
    api_base: str = "https://api.github.com",
) -> dict[str, Any]:
    config = repo_config or GitHubAppRepoConfig()
    try:
        webhook_result = handle_github_app_webhook(
            headers=headers,
            body=body,
            webhook_secret=webhook_secret,
        )
    except GitHubWebhookError as exc:
        return {
            "status": "error",
            "reason_code": "WEBHOOK_VALIDATION_FAILED",
            "reason": str(exc),
            "event": "",
            "delivery": "",
        }

    if webhook_result.get("ignored", False):
        return {
            "status": "skipped",
            "reason_code": str(webhook_result.get("reason_code", "IGNORED_EVENT")),
            "reason": str(webhook_result.get("reason", "")),
            "event": str(webhook_result.get("event", "")),
            "delivery": str(webhook_result.get("delivery", "")),
            "repository": str(webhook_result.get("repository", "")),
            "workflow_run_id": int(webhook_result.get("workflow_run_id", 0) or 0),
        }

    if not webhook_result.get("handled", False):
        return {
            "status": "error",
            "reason_code": str(webhook_result.get("reason_code", "WEBHOOK_UNHANDLED")),
            "reason": str(webhook_result.get("reason", "webhook event was not handled")),
            "event": str(webhook_result.get("event", "")),
            "delivery": str(webhook_result.get("delivery", "")),
        }

    repository = str(webhook_result.get("repository", "")).strip()
    workflow_run_id = int(webhook_result.get("workflow_run_id", 0) or 0)
    head_sha = str(webhook_result.get("head_sha", "")).strip()
    base_sha = str(webhook_result.get("base_sha", "")).strip()
    run_id = f"gha_{workflow_run_id}"
    output_dir = Path(config.output_dir).as_posix()

    try:
        ingestion = collect_workflow_run_inputs(
            token=github_token,
            repository=repository,
            workflow_run_id=workflow_run_id,
            head_sha=head_sha,
            base_sha=base_sha,
            api_base=api_base,
        )
    except GitHubAppIngestionError as exc:
        return {
            "status": "error",
            "reason_code": exc.reason_code,
            "reason": str(exc),
            "event": str(webhook_result.get("event", "")),
            "delivery": str(webhook_result.get("delivery", "")),
            "repository": repository,
            "workflow_run_id": workflow_run_id,
        }

    request = PipelineRequest(
        raw_log=ingestion.raw_log,
        raw_diff=ingestion.raw_diff,
        timestamp="1970-01-01T00:00:00Z",
        commit=ingestion.head_sha,
        run_id=run_id,
        base_commit=ingestion.base_sha,
        head_commit=ingestion.head_sha,
        output_dir=output_dir,
        create_fix_pr=config.create_fix_pr,
        dry_run=False,
        github_token=github_token,
        repository=ingestion.repository,
        target_branch=str(webhook_result.get("head_branch", "")).strip() or "main",
        fail_fast=False,
        min_pr_confidence=config.min_pr_confidence,
        execution_mode=config.execution_mode,
    )

    state = run_pipeline(request=request)
    summary = _pipeline_summary(state=state)
    return {
        "status": "ok",
        "reason_code": "",
        "reason": "",
        "event": str(webhook_result.get("event", "")),
        "delivery": str(webhook_result.get("delivery", "")),
        "repository": repository,
        "workflow_run_id": workflow_run_id,
        "pipeline_status": str(getattr(state, "pipeline_status", "unknown")),
        **summary,
    }
