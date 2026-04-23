from __future__ import annotations

from dataclasses import dataclass

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_SKIPPED = "skipped"
STATUS_ERROR = "error"

KNOWN_REASON_CODES = {
    "",
    "UNSUPPORTED_EVENT",
    "WORKFLOW_NOT_COMPLETED",
    "WORKFLOW_NOT_FAILED",
    "REPOSITORY_DISABLED",
    "REPOSITORY_DENYLISTED",
    "REPOSITORY_NOT_ALLOWLISTED",
    "WEBHOOK_VALIDATION_FAILED",
    "WEBHOOK_UNHANDLED",
    "MISSING_REPOSITORY",
    "MISSING_REPOSITORY_FULL_NAME",
    "MISSING_WORKFLOW_RUN",
    "INVALID_WORKFLOW_RUN_ID",
    "INVALID_WORKFLOW_RUN_ATTEMPT",
    "INVALID_WORKFLOW_RUN_CONCLUSION",
    "MISSING_HEAD_SHA",
    "MISSING_HEAD_BRANCH",
    "MISSING_WORKFLOW_RUN_STATUS",
    "MISSING_WORKFLOW_RUN_CONCLUSION",
    "MISSING_WORKFLOW_RUN_NAME",
    "MISSING_WORKFLOW_RUN_URL",
    "MISSING_BASE_SHA",
    "MISSING_GITHUB_TOKEN",
    "GITHUB_API_HTTP_ERROR",
    "GITHUB_API_NETWORK_ERROR",
    "GITHUB_API_INVALID_JSON",
    "GITHUB_API_INVALID_RESPONSE",
    "WORKFLOW_LOGS_EMPTY",
    "WORKFLOW_LOGS_UNREADABLE",
    "WORKFLOW_LOGS_INVALID_ARCHIVE",
    "WORKFLOW_LOGS_EMPTY_ARCHIVE",
    "COMPARE_FILES_MISSING",
    "COMPARE_DIFF_EMPTY",
    "COMMENT_API_HTTP_ERROR",
    "COMMENT_API_NETWORK_ERROR",
    "COMMENT_API_INVALID_JSON",
    "COMMENT_API_INVALID_RESPONSE",
    "ARTIFACT_OUTPUT_MISSING",
}


@dataclass(frozen=True)
class AppOutcome:
    status: str
    reason_code: str
    reason: str


def ensure_known_reason_code(reason_code: str) -> str:
    normalized = reason_code.strip().upper()
    if normalized not in KNOWN_REASON_CODES:
        raise ValueError(f"Unknown app outcome reason code: {reason_code}")
    return normalized


def build_outcome(*, status: str, reason_code: str = "", reason: str = "") -> AppOutcome:
    normalized_status = status.strip().lower()
    if normalized_status not in {STATUS_OK, STATUS_PARTIAL, STATUS_SKIPPED, STATUS_ERROR}:
        raise ValueError(f"Unknown app outcome status: {status}")
    normalized_reason_code = ensure_known_reason_code(reason_code)
    return AppOutcome(
        status=normalized_status,
        reason_code=normalized_reason_code,
        reason=reason,
    )
