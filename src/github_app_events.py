from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class GitHubAppEventPayloadError(ValueError):
    """Raised when GitHub App event payloads are invalid."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class WorkflowRunEvent:
    repository: str
    workflow_run_id: int
    workflow_run_name: str
    head_sha: str
    base_sha: str
    head_branch: str
    conclusion: str
    status: str
    html_url: str
    is_failure: bool


def _require_dict(value: Any, *, field_name: str, reason_code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GitHubAppEventPayloadError(
            f"{field_name} must be a JSON object",
            reason_code=reason_code,
        )
    return value


def _require_non_empty_str(
    value: Any,
    *,
    field_name: str,
    reason_code: str,
) -> str:
    if not isinstance(value, str):
        raise GitHubAppEventPayloadError(
            f"{field_name} is required",
            reason_code=reason_code,
        )
    text = value.strip()
    if not text:
        raise GitHubAppEventPayloadError(
            f"{field_name} is required",
            reason_code=reason_code,
        )
    return text


def _read_base_sha(workflow_run: dict[str, Any]) -> str:
    pull_requests = workflow_run.get("pull_requests")
    if not isinstance(pull_requests, list) or not pull_requests:
        return ""
    first_pr = pull_requests[0]
    if not isinstance(first_pr, dict):
        return ""
    base = first_pr.get("base")
    if not isinstance(base, dict):
        return ""
    return str(base.get("sha", "")).strip()


def parse_workflow_run_event(payload: dict[str, Any]) -> WorkflowRunEvent:
    root = _require_dict(payload, field_name="payload", reason_code="INVALID_PAYLOAD")
    repo = _require_dict(
        root.get("repository"),
        field_name="repository",
        reason_code="MISSING_REPOSITORY",
    )
    workflow_run = _require_dict(
        root.get("workflow_run"),
        field_name="workflow_run",
        reason_code="MISSING_WORKFLOW_RUN",
    )

    repository = _require_non_empty_str(
        repo.get("full_name"),
        field_name="repository.full_name",
        reason_code="MISSING_REPOSITORY_FULL_NAME",
    )
    run_id_raw = workflow_run.get("id")
    if not isinstance(run_id_raw, int) or run_id_raw <= 0:
        raise GitHubAppEventPayloadError(
            "workflow_run.id must be a positive integer",
            reason_code="INVALID_WORKFLOW_RUN_ID",
        )

    head_sha = _require_non_empty_str(
        workflow_run.get("head_sha"),
        field_name="workflow_run.head_sha",
        reason_code="MISSING_HEAD_SHA",
    )
    head_branch = _require_non_empty_str(
        workflow_run.get("head_branch"),
        field_name="workflow_run.head_branch",
        reason_code="MISSING_HEAD_BRANCH",
    )
    status = _require_non_empty_str(
        workflow_run.get("status"),
        field_name="workflow_run.status",
        reason_code="MISSING_WORKFLOW_RUN_STATUS",
    ).lower()
    conclusion = _require_non_empty_str(
        workflow_run.get("conclusion"),
        field_name="workflow_run.conclusion",
        reason_code="MISSING_WORKFLOW_RUN_CONCLUSION",
    ).lower()
    run_name = _require_non_empty_str(
        workflow_run.get("name"),
        field_name="workflow_run.name",
        reason_code="MISSING_WORKFLOW_RUN_NAME",
    )
    html_url = _require_non_empty_str(
        workflow_run.get("html_url"),
        field_name="workflow_run.html_url",
        reason_code="MISSING_WORKFLOW_RUN_URL",
    )
    base_sha = _read_base_sha(workflow_run)

    return WorkflowRunEvent(
        repository=repository,
        workflow_run_id=run_id_raw,
        workflow_run_name=run_name,
        head_sha=head_sha,
        base_sha=base_sha,
        head_branch=head_branch,
        conclusion=conclusion,
        status=status,
        html_url=html_url,
        is_failure=conclusion == "failure",
    )
