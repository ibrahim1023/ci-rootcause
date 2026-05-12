from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.orchestration import PipelineRequest, run_pipeline
from src.github_app_comments import (
    GitHubAppCommentClient,
    GitHubAppCommentError,
    build_app_comment_body,
    build_inline_comment_body,
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

PR_REASON_AGENTIC_MISSING_KEY = "AGENTIC_MISSING_KEY"
PR_REASON_AGENTIC_PROVIDER_ERROR = "AGENTIC_PROVIDER_ERROR"
PR_REASON_AGENTIC_MAX_ATTEMPTS_EXCEEDED = "AGENTIC_MAX_ATTEMPTS_EXCEEDED"


@dataclass(frozen=True)
class GitHubAppRepoConfig:
    enabled: bool = True
    allow_repositories: tuple[str, ...] = ()
    deny_repositories: tuple[str, ...] = ()
    enable_pr_mode: bool = False
    create_fix_pr: bool = False
    min_pr_confidence: float = 0.75
    max_fix_files: int = 5
    execution_mode: str = "deterministic"
    validation_commands: tuple[str, ...] = ()
    typecheck_validation_commands: tuple[str, ...] = ()
    lint_validation_commands: tuple[str, ...] = ()
    test_validation_commands: tuple[str, ...] = ()
    monitor_fix_pr_checks: bool = False
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    output_dir: str = "artifacts/app"
    post_comment: bool = True
    min_comment_confidence: float = 0.5
    output_mode: str = "summary"


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
    ci_monitoring_attempted = False
    ci_monitoring_status = ""
    ci_monitoring_conclusion = ""
    ci_monitoring_url = ""
    ci_monitoring_reason = ""
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
        ci_monitoring_attempted = bool(pr_output.get("ci_monitoring_attempted", False))
        ci_monitoring_status = str(pr_output.get("ci_monitoring_status", ""))
        ci_monitoring_conclusion = str(pr_output.get("ci_monitoring_conclusion", "") or "")
        ci_monitoring_url = str(pr_output.get("ci_monitoring_url", "") or "")
        ci_monitoring_reason = str(pr_output.get("ci_monitoring_reason", "") or "")

    return {
        "classification": classification,
        "confidence": confidence,
        "primary_root_cause_title": title,
        "rca_json_path": json_path,
        "rca_md_path": md_path,
        "pr_created": pr_created,
        "pr_failure_reason_code": pr_failure_reason_code,
        "pr_failure_reason": pr_failure_reason,
        "ci_monitoring_attempted": ci_monitoring_attempted,
        "ci_monitoring_status": ci_monitoring_status,
        "ci_monitoring_conclusion": ci_monitoring_conclusion,
        "ci_monitoring_url": ci_monitoring_url,
        "ci_monitoring_reason": ci_monitoring_reason,
        "confidence_reasons": confidence_reasons,
        "evidence": evidence,
        "suggested_fix": suggested_fix,
    }


def _infer_pipeline_failure_reason(state: Any) -> tuple[str, str]:
    failures = getattr(state, "failures", [])
    if not isinstance(failures, list):
        return "", ""

    for failure in failures:
        if not isinstance(failure, dict):
            continue
        message = str(failure.get("message", "")).strip()
        normalized_message = message.lower()
        error_type = str(failure.get("error_type", "")).strip()

        if "provider api key is required" in normalized_message:
            return PR_REASON_AGENTIC_MISSING_KEY, message
        if error_type == "AgenticProposalProviderError":
            return PR_REASON_AGENTIC_PROVIDER_ERROR, message
        if "max attempts exceeded" in normalized_message:
            return PR_REASON_AGENTIC_MAX_ATTEMPTS_EXCEEDED, message
    return "", ""


def _has_file_evidence(summary: dict[str, Any]) -> bool:
    evidence = summary.get("evidence", [])
    if not isinstance(evidence, list):
        return False
    for item in evidence:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file", "")).strip().lower()
        if file_path and file_path != "unknown":
            return True
    return False


def _should_post_comment(summary: dict[str, Any], config: GitHubAppRepoConfig) -> tuple[bool, str]:
    if not config.post_comment:
        return False, "post_comment=false"
    if bool(summary.get("pr_created", False)):
        return True, ""

    confidence = float(summary.get("confidence", 0.0))
    if confidence >= config.min_comment_confidence:
        return True, ""

    classification = str(summary.get("classification", "")).strip().upper()
    if classification not in {"TEST", "UNKNOWN"}:
        return True, ""
    if _has_file_evidence(summary):
        return True, ""

    return (
        False,
        f"confidence {confidence:.4f} is below comment threshold "
        f"{config.min_comment_confidence:.4f} and no file evidence was found",
    )


def _normalize_output_mode(value: str) -> set[str]:
    text = value.strip().lower().replace("-", "_")
    aliases = {
        "": {"summary"},
        "summary": {"summary"},
        "summary_only": {"summary"},
        "comment": {"summary"},
        "comment_only": {"summary"},
        "inline": {"inline"},
        "inline_only": {"inline"},
        "check": {"status"},
        "check_only": {"status"},
        "status": {"status"},
        "status_only": {"status"},
        "combined": {"summary", "inline", "status"},
        "all": {"summary", "inline", "status"},
        "summary_inline": {"summary", "inline"},
        "inline_summary": {"summary", "inline"},
        "summary_check": {"summary", "status"},
        "check_summary": {"summary", "status"},
        "summary_status": {"summary", "status"},
        "status_summary": {"summary", "status"},
        "inline_check": {"inline", "status"},
        "check_inline": {"inline", "status"},
        "inline_status": {"inline", "status"},
        "status_inline": {"inline", "status"},
    }
    if text in aliases:
        return set(aliases[text])
    parts = {part for part in re.split(r"[_+,\\s]+", text) if part}
    normalized: set[str] = set()
    for part in parts:
        if part in {"summary", "comment"}:
            normalized.add("summary")
        elif part == "inline":
            normalized.add("inline")
        elif part in {"check", "status"}:
            normalized.add("status")
    return normalized or {"summary"}


def _enabled_output_modes(config: GitHubAppRepoConfig) -> set[str]:
    modes = _normalize_output_mode(config.output_mode)
    if not config.post_comment:
        modes.discard("summary")
        modes.discard("inline")
    return modes


def _first_diff_mapped_evidence(
    *,
    evidence: list[dict[str, object]],
    raw_diff: str,
) -> dict[str, object] | None:
    for item in evidence:
        file_path = str(item.get("file", "")).strip()
        line = item.get("line")
        if not file_path or file_path == "unknown" or not isinstance(line, int) or line <= 0:
            continue
        if _line_maps_to_diff(raw_diff=raw_diff, file_path=file_path, line=line):
            return {"file": file_path, "line": line}
    return None


def _line_maps_to_diff(*, raw_diff: str, file_path: str, line: int) -> bool:
    current_file = ""
    new_line: int | None = None
    target = file_path.strip().lstrip("./")
    hunk_header = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

    for raw_line in raw_diff.splitlines():
        if raw_line.startswith("diff --git "):
            current_file = ""
            new_line = None
            continue
        if raw_line.startswith("+++ "):
            candidate = raw_line[4:].strip()
            if candidate.startswith("b/"):
                candidate = candidate[2:]
            current_file = "" if candidate == "/dev/null" else candidate.lstrip("./")
            new_line = None
            continue
        match = hunk_header.match(raw_line)
        if match:
            new_line = int(match.group(1))
            continue
        if current_file != target or new_line is None:
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            if new_line == line:
                return True
            new_line += 1
            continue
        if raw_line.startswith(" "):
            if new_line == line:
                return True
            new_line += 1
    return False


def _status_description(summary: dict[str, Any]) -> str:
    classification = str(summary.get("classification", "UNKNOWN")).strip() or "UNKNOWN"
    confidence = float(summary.get("confidence", 0.0))
    title = " ".join(str(summary.get("primary_root_cause_title", "unknown")).split())
    return f"{classification} RCA {confidence:.2f}: {title or 'unknown'}"[:140]


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
        max_fix_files=config.max_fix_files,
        execution_mode=config.execution_mode,
        validation_commands=list(config.validation_commands),
        typecheck_validation_commands=list(config.typecheck_validation_commands),
        lint_validation_commands=list(config.lint_validation_commands),
        test_validation_commands=list(config.test_validation_commands),
        monitor_fix_pr_checks=config.monitor_fix_pr_checks,
        llm_provider=config.llm_provider,
        llm_model=config.llm_model,
        llm_api_key=config.llm_api_key,
        llm_base_url=config.llm_base_url,
        create_fix_pr_disabled_reason=disabled_reason,
    )

    state = run_pipeline(request=request)
    summary = _pipeline_summary(state=state)
    pipeline_failure_reason_code, pipeline_failure_reason = _infer_pipeline_failure_reason(state)
    artifact_reason_code = ""
    artifact_reason = ""
    if not str(summary["rca_json_path"]).strip() or not str(summary["rca_md_path"]).strip():
        artifact_reason_code = "ARTIFACT_OUTPUT_MISSING"
        artifact_reason = "reporter did not return ci-rca artifact paths"

    output_modes = _enabled_output_modes(config)
    comment_posted = False
    comment_target = ""
    comment_id = 0
    comment_action = ""
    comment_url = ""
    comment_reason_code = ""
    comment_reason = ""
    comment_skipped_reason = ""
    inline_comment_posted = False
    inline_comment_id = 0
    inline_comment_action = ""
    inline_comment_url = ""
    inline_comment_skipped_reason = ""
    status_posted = False
    status_url = ""
    status_failure_reason_code = ""
    status_failure_reason = ""

    should_post_comment, comment_skipped_reason = _should_post_comment(
        summary=summary,
        config=config,
    )
    pull_request_number_raw = webhook_result.get("pull_request_number")
    pull_request_number = (
        int(pull_request_number_raw)
        if isinstance(pull_request_number_raw, int) and pull_request_number_raw > 0
        else 0
    )

    client: GitHubAppCommentClient | None = None
    if output_modes & {"summary", "inline", "status"}:
        client = GitHubAppCommentClient(token=github_token, api_base=api_base)

    if "summary" in output_modes and should_post_comment and client is not None:
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
            ci_monitoring_attempted=bool(summary["ci_monitoring_attempted"]),
            ci_monitoring_status=str(summary["ci_monitoring_status"]),
            ci_monitoring_conclusion=str(summary["ci_monitoring_conclusion"]),
            ci_monitoring_url=str(summary["ci_monitoring_url"]),
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
    elif "summary" not in output_modes:
        comment_skipped_reason = "summary output disabled"

    if "inline" in output_modes and client is not None:
        inline_evidence = _first_diff_mapped_evidence(
            evidence=summary["evidence"],
            raw_diff=ingestion.raw_diff,
        )
        confidence = float(summary.get("confidence", 0.0))
        if pull_request_number <= 0:
            inline_comment_skipped_reason = "pull request context is required"
        elif not should_post_comment:
            inline_comment_skipped_reason = comment_skipped_reason
        elif confidence < config.min_comment_confidence:
            inline_comment_skipped_reason = (
                f"confidence {confidence:.4f} is below inline threshold "
                f"{config.min_comment_confidence:.4f}"
            )
        elif inline_evidence is None:
            inline_comment_skipped_reason = "no file/line evidence maps to the PR diff"
        else:
            inline_body = build_inline_comment_body(
                classification=str(summary["classification"]),
                confidence=confidence,
                primary_root_cause_title=str(summary["primary_root_cause_title"]),
                suggested_fix=str(summary["suggested_fix"]),
            )
            try:
                inline_result = client.upsert_inline_pr_comment(
                    repository=repository,
                    pull_request_number=pull_request_number,
                    commit_sha=ingestion.head_sha,
                    path=str(inline_evidence["file"]),
                    line=int(inline_evidence["line"]),
                    body=inline_body,
                )
                inline_comment_posted = True
                inline_comment_id = inline_result.comment_id
                inline_comment_action = inline_result.action
                inline_comment_url = inline_result.html_url
            except GitHubAppCommentError as exc:
                comment_reason_code = comment_reason_code or exc.reason_code
                comment_reason = comment_reason or str(exc)
                inline_comment_skipped_reason = str(exc)

    if "status" in output_modes and client is not None:
        target_url = comment_url
        try:
            status_result = client.publish_commit_status(
                repository=repository,
                commit_sha=ingestion.head_sha,
                state="success",
                description=_status_description(summary),
                target_url=target_url,
            )
            status_posted = True
            status_url = status_result.target_url or status_result.api_url
        except GitHubAppCommentError as exc:
            status_failure_reason_code = exc.reason_code
            status_failure_reason = str(exc)

    status = STATUS_OK
    reason_code = ""
    reason = ""
    if comment_reason_code:
        status = STATUS_PARTIAL
        reason_code = comment_reason_code
        reason = comment_reason
    elif status_failure_reason_code:
        status = STATUS_PARTIAL
        reason_code = status_failure_reason_code
        reason = status_failure_reason
    elif pipeline_failure_reason_code:
        status = STATUS_PARTIAL
        reason_code = pipeline_failure_reason_code
        reason = pipeline_failure_reason
    elif artifact_reason_code:
        status = STATUS_PARTIAL
        reason_code = artifact_reason_code
        reason = artifact_reason

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
        "output_mode": config.output_mode,
        "comment_posted": comment_posted,
        "comment_target": comment_target,
        "comment_id": comment_id,
        "comment_action": comment_action,
        "comment_url": comment_url,
        "comment_skipped_reason": comment_skipped_reason,
        "inline_comment_posted": inline_comment_posted,
        "inline_comment_id": inline_comment_id,
        "inline_comment_action": inline_comment_action,
        "inline_comment_url": inline_comment_url,
        "inline_comment_skipped_reason": inline_comment_skipped_reason,
        "status_posted": status_posted,
        "status_url": status_url,
        "status_failure_reason_code": status_failure_reason_code,
        "status_failure_reason": status_failure_reason,
        **summary,
    }
