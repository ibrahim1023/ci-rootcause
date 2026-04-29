from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.orchestration import PipelineRequest, run_pipeline
from src.github_app_comments import (
    GitHubAppCommentClient,
    GitHubAppCommentError,
    build_app_comment_body,
)
from src.github_app_ingestion import GitHubAppIngestionError, collect_workflow_run_inputs
from src.github_app_outcomes import (
    STATUS_ERROR,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_SKIPPED,
    build_outcome,
)
from src.github_app_webhook import (
    GitHubWebhookError,
    handle_github_app_webhook,
)


@dataclass(frozen=True)
class GitHubAppRepoConfig:
    enabled: bool = True
    allow_repositories: tuple[str, ...] = ()
    deny_repositories: tuple[str, ...] = ()
    enable_pr_mode: bool = False
    create_fix_pr: bool = False
    min_pr_confidence: float = 0.75
    execution_mode: str = "deterministic"
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    output_dir: str = "artifacts/app"
    post_comment: bool = True


def _resolve_pr_creation_controls(config: GitHubAppRepoConfig) -> tuple[bool, str | None]:
    if not config.create_fix_pr:
        return False, None
    if not config.enable_pr_mode:
        return False, "app_pr_mode_not_enabled"
    return True, None


def _normalize_repository_set(items: tuple[str, ...]) -> set[str]:
    return {value.strip().lower() for value in items if value.strip()}


def _evaluate_repository_policy(
    *,
    repository: str,
    config: GitHubAppRepoConfig,
) -> tuple[bool, str, str]:
    if not config.enabled:
        return False, "REPOSITORY_DISABLED", "repository processing is disabled"

    normalized_repo = repository.strip().lower()
    deny_set = _normalize_repository_set(config.deny_repositories)
    if normalized_repo in deny_set:
        return False, "REPOSITORY_DENYLISTED", "repository is explicitly denylisted"

    allow_set = _normalize_repository_set(config.allow_repositories)
    if allow_set and normalized_repo not in allow_set:
        return False, "REPOSITORY_NOT_ALLOWLISTED", "repository is not in allowlist"

    return True, "", ""


def _pipeline_summary(state: Any) -> dict[str, Any]:
    classification = "UNKNOWN"
    confidence = 0.0
    title = ""
    json_path = ""
    md_path = ""
    pr_created = False
    pr_failure_reason_code = ""
    pr_failure_reason = ""
    confidence_reasons: list[str] = []
    evidence: list[dict[str, object]] = []
    suggested_fix = ""

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
            confidence_reasons = [str(item) for item in primary.get("confidence_reasons", [])]
            raw_evidence = primary.get("evidence", [])
            if isinstance(raw_evidence, list):
                evidence = [item for item in raw_evidence if isinstance(item, dict)]
    fix_output = state.agent_outputs.get("fix_planner", {})
    if isinstance(fix_output, dict):
        fix_steps = fix_output.get("fix_steps", [])
        if isinstance(fix_steps, list) and fix_steps:
            first_step = fix_steps[0]
            if isinstance(first_step, dict):
                suggested_fix = str(first_step.get("instruction", suggested_fix))
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
        "confidence_reasons": confidence_reasons,
        "evidence": evidence,
        "suggested_fix": suggested_fix,
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
        outcome = build_outcome(
            status=STATUS_ERROR,
            reason_code="WEBHOOK_VALIDATION_FAILED",
            reason=str(exc),
        )
        return {
            "status": outcome.status,
            "reason_code": outcome.reason_code,
            "reason": outcome.reason,
            "event": "",
            "delivery": "",
        }

    if webhook_result.get("ignored", False):
        outcome = build_outcome(
            status=STATUS_SKIPPED,
            reason_code=str(webhook_result.get("reason_code", "UNSUPPORTED_EVENT")),
            reason=str(webhook_result.get("reason", "")),
        )
        return {
            "status": outcome.status,
            "reason_code": outcome.reason_code,
            "reason": outcome.reason,
            "event": str(webhook_result.get("event", "")),
            "delivery": str(webhook_result.get("delivery", "")),
            "repository": str(webhook_result.get("repository", "")),
            "workflow_run_id": int(webhook_result.get("workflow_run_id", 0) or 0),
        }

    if not webhook_result.get("handled", False):
        outcome = build_outcome(
            status=STATUS_ERROR,
            reason_code=str(webhook_result.get("reason_code", "WEBHOOK_UNHANDLED")),
            reason=str(webhook_result.get("reason", "webhook event was not handled")),
        )
        return {
            "status": outcome.status,
            "reason_code": outcome.reason_code,
            "reason": outcome.reason,
            "event": str(webhook_result.get("event", "")),
            "delivery": str(webhook_result.get("delivery", "")),
        }

    repository = str(webhook_result.get("repository", "")).strip()
    workflow_run_id = int(webhook_result.get("workflow_run_id", 0) or 0)
    head_sha = str(webhook_result.get("head_sha", "")).strip()
    base_sha = str(webhook_result.get("base_sha", "")).strip()

    policy_allowed, policy_reason_code, policy_reason = _evaluate_repository_policy(
        repository=repository,
        config=config,
    )
    if not policy_allowed:
        outcome = build_outcome(
            status=STATUS_SKIPPED,
            reason_code=policy_reason_code,
            reason=policy_reason,
        )
        return {
            "status": outcome.status,
            "reason_code": outcome.reason_code,
            "reason": outcome.reason,
            "event": str(webhook_result.get("event", "")),
            "delivery": str(webhook_result.get("delivery", "")),
            "repository": repository,
            "workflow_run_id": workflow_run_id,
        }

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
        if exc.reason_code == "MISSING_BASE_SHA":
            outcome = build_outcome(
                status=STATUS_SKIPPED,
                reason_code=exc.reason_code,
                reason=str(exc),
            )
            return {
                "status": outcome.status,
                "reason_code": outcome.reason_code,
                "reason": outcome.reason,
                "event": str(webhook_result.get("event", "")),
                "delivery": str(webhook_result.get("delivery", "")),
                "repository": repository,
                "workflow_run_id": workflow_run_id,
            }
        outcome = build_outcome(
            status=STATUS_ERROR,
            reason_code=exc.reason_code,
            reason=str(exc),
        )
        return {
            "status": outcome.status,
            "reason_code": outcome.reason_code,
            "reason": outcome.reason,
            "event": str(webhook_result.get("event", "")),
            "delivery": str(webhook_result.get("delivery", "")),
            "repository": repository,
            "workflow_run_id": workflow_run_id,
        }

    resolved_create_fix_pr, disabled_reason = _resolve_pr_creation_controls(config)

    request = PipelineRequest(
        raw_log=ingestion.raw_log,
        raw_diff=ingestion.raw_diff,
        timestamp="1970-01-01T00:00:00Z",
        commit=ingestion.head_sha,
        run_id=run_id,
        base_commit=ingestion.base_sha,
        head_commit=ingestion.head_sha,
        output_dir=output_dir,
        create_fix_pr=resolved_create_fix_pr,
        dry_run=False,
        github_token=github_token,
        repository=ingestion.repository,
        target_branch=str(webhook_result.get("head_branch", "")).strip() or "main",
        fail_fast=False,
        min_pr_confidence=config.min_pr_confidence,
        execution_mode=config.execution_mode,
        llm_provider=config.llm_provider,
        llm_model=config.llm_model,
        llm_api_key=config.llm_api_key,
        llm_base_url=config.llm_base_url,
        create_fix_pr_disabled_reason=disabled_reason,
    )

    state = run_pipeline(request=request)
    summary = _pipeline_summary(state=state)
    artifact_reason_code = ""
    artifact_reason = ""
    if not str(summary["rca_json_path"]).strip() or not str(summary["rca_md_path"]).strip():
        artifact_reason_code = "ARTIFACT_OUTPUT_MISSING"
        artifact_reason = "reporter did not return ci-rca artifact paths"

    comment_posted = False
    comment_target = ""
    comment_id = 0
    comment_action = ""
    comment_url = ""
    comment_reason_code = ""
    comment_reason = ""

    if config.post_comment:
        comment_body = build_app_comment_body(
            classification=str(summary["classification"]),
            confidence=float(summary["confidence"]),
            primary_root_cause_title=str(summary["primary_root_cause_title"]),
            run_id=run_id,
            rca_json_path=str(summary["rca_json_path"]),
            rca_md_path=str(summary["rca_md_path"]),
            confidence_reason=", ".join(str(item) for item in summary["confidence_reasons"]),
            evidence=summary["evidence"],
            suggested_fix=str(summary["suggested_fix"]),
            app_outcome=(
                "Fix PR created." if bool(summary["pr_created"]) else "Comment-only RCA generated."
            ),
            pr_created=bool(summary["pr_created"]),
            pr_failure_reason=str(summary["pr_failure_reason"]),
            pr_failure_reason_code=str(summary["pr_failure_reason_code"]),
        )
        client = GitHubAppCommentClient(token=github_token, api_base=api_base)
        pull_request_number_raw = webhook_result.get("pull_request_number")
        pull_request_number = (
            int(pull_request_number_raw)
            if isinstance(pull_request_number_raw, int) and pull_request_number_raw > 0
            else 0
        )
        try:
            if pull_request_number > 0:
                comment_result = client.upsert_pr_comment(
                    repository=repository,
                    pull_request_number=pull_request_number,
                    body=comment_body,
                )
            else:
                comment_result = client.upsert_commit_comment(
                    repository=repository,
                    commit_sha=ingestion.head_sha,
                    body=comment_body,
                )
            comment_posted = True
            comment_target = comment_result.target
            comment_id = comment_result.comment_id
            comment_action = comment_result.action
            comment_url = comment_result.html_url
        except GitHubAppCommentError as exc:
            comment_reason_code = exc.reason_code
            comment_reason = str(exc)

    status = STATUS_OK
    reason_code = ""
    reason = ""
    if artifact_reason_code:
        status = STATUS_PARTIAL
        reason_code = artifact_reason_code
        reason = artifact_reason
    if comment_reason_code:
        status = STATUS_PARTIAL
        reason_code = comment_reason_code
        reason = comment_reason

    outcome = build_outcome(
        status=status,
        reason_code=reason_code,
        reason=reason,
    )

    return {
        "status": outcome.status,
        "reason_code": outcome.reason_code,
        "reason": outcome.reason,
        "event": str(webhook_result.get("event", "")),
        "delivery": str(webhook_result.get("delivery", "")),
        "repository": repository,
        "workflow_run_id": workflow_run_id,
        "pipeline_status": str(getattr(state, "pipeline_status", "unknown")),
        "artifact_output_ok": artifact_reason_code == "",
        "artifact_output_reason_code": artifact_reason_code,
        "artifact_output_reason": artifact_reason,
        "comment_posted": comment_posted,
        "comment_target": comment_target,
        "comment_id": comment_id,
        "comment_action": comment_action,
        "comment_url": comment_url,
        **summary,
    }
