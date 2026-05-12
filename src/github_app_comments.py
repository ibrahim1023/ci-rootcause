from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib import error
from urllib import request as urllib_request

APP_COMMENT_MARKER = "<!-- ci-rootcause:app-comment:v1 -->"
APP_INLINE_COMMENT_MARKER = "<!-- ci-rootcause:app-inline-comment:v1 -->"
APP_STATUS_CONTEXT = "ci-rootcause/rca"


class GitHubAppCommentError(RuntimeError):
    """Raised when GitHub App comment publishing fails."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class CommentPublishResult:
    target: str
    comment_id: int
    action: str
    html_url: str


@dataclass(frozen=True)
class StatusPublishResult:
    context: str
    state: str
    target_url: str
    api_url: str


def build_inline_comment_body(
    *,
    classification: str,
    confidence: float,
    primary_root_cause_title: str,
    suggested_fix: str = "",
) -> str:
    fix_text = suggested_fix.strip() or "Review the RCA summary before changing code."
    return "\n".join(
        [
            APP_INLINE_COMMENT_MARKER,
            "**ci-rootcause RCA**",
            "",
            f"- Likely cause: {primary_root_cause_title or 'unknown'}",
            f"- Classification: `{classification}`",
            f"- Confidence: `{confidence:.4f}`",
            f"- Suggested fix: {fix_text}",
        ]
    )


def build_app_comment_body(
    *,
    classification: str,
    confidence: float,
    primary_root_cause_title: str,
    run_id: str,
    rca_json_path: str,
    rca_md_path: str,
    confidence_reason: str = "",
    evidence: list[dict[str, object]] | None = None,
    suggested_fix: str = "",
    app_outcome: str = "",
    pr_created: bool = False,
    pr_failure_reason: str = "",
    pr_failure_reason_code: str = "",
    ci_monitoring_attempted: bool = False,
    ci_monitoring_status: str = "",
    ci_monitoring_conclusion: str = "",
    ci_monitoring_url: str = "",
) -> str:
    reason = confidence_reason.strip() or "No confidence explanation recorded."
    evidence_items = list(evidence or [])
    evidence_lines: list[str] = []
    for item in evidence_items[:3]:
        file_path = str(item.get("file", "unknown")).strip() or "unknown"
        line = item.get("line")
        location = f"{file_path}:{line}" if isinstance(line, int) and line > 0 else file_path
        excerpt = " ".join(str(item.get("excerpt", "")).strip().split())
        if excerpt:
            evidence_lines.append(f"- `{location}`: {excerpt[:240]}")
        else:
            evidence_lines.append(f"- `{location}`")
    if not evidence_lines:
        evidence_lines.append("- No concrete file evidence was captured.")

    fix_text = suggested_fix.strip() or "No safe fix suggestion was generated."
    outcome = app_outcome.strip()
    if not outcome:
        outcome = "Fix PR created." if pr_created else "Comment-only RCA generated."
    if not pr_created and (pr_failure_reason_code or pr_failure_reason):
        outcome = (
            f"{outcome} PR gate: `{pr_failure_reason_code or 'not_created'}`"
            f" - {pr_failure_reason or 'not specified'}"
        )
    ci_lines: list[str] = []
    if ci_monitoring_attempted:
        ci_lines.append(
            "- Remote CI: "
            f"`{ci_monitoring_status or 'unknown'}`"
            f" / `{ci_monitoring_conclusion or 'unknown'}`"
        )
        if ci_monitoring_url:
            ci_lines.append(f"- Remote CI URL: {ci_monitoring_url}")

    return "\n".join(
        [
            APP_COMMENT_MARKER,
            "## ci-rootcause RCA",
            "",
            "## Likely cause",
            f"{primary_root_cause_title or 'unknown'}",
            "",
            "## Evidence",
            *evidence_lines,
            "",
            "## Suggested fix",
            f"- {fix_text}",
            "",
            "## Confidence",
            f"- Score: `{confidence:.4f}`",
            f"- Classification: `{classification}`",
            f"- Reason: {reason}",
            "",
            "## App outcome",
            f"- {outcome}",
            *ci_lines,
            f"- Run ID: `{run_id}`",
            "",
            "Artifacts:",
            f"- JSON: `{rca_json_path or 'unavailable'}`",
            f"- Markdown: `{rca_md_path or 'unavailable'}`",
        ]
    )


class GitHubAppCommentClient:
    def __init__(
        self,
        *,
        token: str,
        api_base: str = "https://api.github.com",
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        max_retry_delay_seconds: float = 30.0,
    ) -> None:
        self._token = token.strip()
        if not self._token:
            raise GitHubAppCommentError(
                "github token is required",
                reason_code="MISSING_GITHUB_TOKEN",
            )
        self._api_base = api_base.rstrip("/")
        if max_retries < 0:
            raise GitHubAppCommentError(
                "max_retries must be >= 0",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        if backoff_seconds < 0.0:
            raise GitHubAppCommentError(
                "backoff_seconds must be >= 0.0",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        if max_retry_delay_seconds < 0.0:
            raise GitHubAppCommentError(
                "max_retry_delay_seconds must be >= 0.0",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._max_retry_delay_seconds = max_retry_delay_seconds

    def _is_rate_limited(self, exc: error.HTTPError, detail: str) -> bool:
        if exc.code == 429:
            return True
        return exc.code == 403 and "rate limit" in detail.lower()

    def _compute_retry_delay(self, attempt: int, retry_after: float | None = None) -> float:
        if retry_after is not None and retry_after >= 0.0:
            return min(retry_after, self._max_retry_delay_seconds)
        return min(
            self._backoff_seconds * float(2**attempt),
            self._max_retry_delay_seconds,
        )

    def _rate_limit_retry_after(self, exc: error.HTTPError) -> float | None:
        retry_after_header = exc.headers.get("Retry-After")
        if retry_after_header:
            try:
                return max(0.0, float(retry_after_header))
            except ValueError:
                return 0.0
        reset_epoch = exc.headers.get("X-RateLimit-Reset")
        if not reset_epoch:
            return None
        try:
            reset_ts = float(reset_epoch)
        except ValueError:
            return 0.0
        return max(0.0, reset_ts - time.time())

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> object:
        body = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib_request.Request(
            url=f"{self._api_base}{path}",
            method=method,
            headers=headers,
            data=body,
        )
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            try:
                with urllib_request.urlopen(req, timeout=30) as response:
                    raw = response.read()
                    break
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                is_last = attempt >= self._max_retries
                if self._is_rate_limited(exc, detail):
                    if is_last:
                        raise GitHubAppCommentError(
                            f"GitHub API HTTP error for {method} {path}: {exc.code}: {detail}",
                            reason_code="COMMENT_API_HTTP_ERROR",
                        ) from exc
                    retry_after = self._rate_limit_retry_after(exc)
                    time.sleep(self._compute_retry_delay(attempt, retry_after))
                    continue
                if exc.code in {500, 502, 503, 504}:
                    if is_last:
                        raise GitHubAppCommentError(
                            f"GitHub API HTTP error for {method} {path}: {exc.code}: {detail}",
                            reason_code="COMMENT_API_HTTP_ERROR",
                        ) from exc
                    time.sleep(self._compute_retry_delay(attempt))
                    continue
                raise GitHubAppCommentError(
                    f"GitHub API HTTP error for {method} {path}: {exc.code}: {detail}",
                    reason_code="COMMENT_API_HTTP_ERROR",
                ) from exc
            except error.URLError as exc:
                is_last = attempt >= self._max_retries
                if is_last:
                    raise GitHubAppCommentError(
                        f"GitHub API network error for {method} {path}: {exc}",
                        reason_code="COMMENT_API_NETWORK_ERROR",
                    ) from exc
                time.sleep(self._compute_retry_delay(attempt))
        else:
            raise GitHubAppCommentError(
                f"GitHub API retries exhausted for {method} {path}",
                reason_code="COMMENT_API_NETWORK_ERROR",
            )

        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubAppCommentError(
                f"GitHub API JSON parsing failed for {method} {path}: {exc}",
                reason_code="COMMENT_API_INVALID_JSON",
            ) from exc

    def upsert_pr_comment(
        self,
        *,
        repository: str,
        pull_request_number: int,
        body: str,
    ) -> CommentPublishResult:
        comments = self._request_json(
            method="GET",
            path=f"/repos/{repository}/issues/{pull_request_number}/comments?per_page=100",
        )
        if not isinstance(comments, list):
            raise GitHubAppCommentError(
                "issues comments response must be a JSON list",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )

        existing: dict[str, object] | None = None
        for item in comments:
            if not isinstance(item, dict):
                continue
            comment_body = str(item.get("body", ""))
            if APP_COMMENT_MARKER in comment_body:
                existing = item
                break

        if existing is not None:
            comment_id = int(existing.get("id", 0) or 0)
            if comment_id <= 0:
                raise GitHubAppCommentError(
                    "existing app comment missing id",
                    reason_code="COMMENT_API_INVALID_RESPONSE",
                )
            payload = self._request_json(
                method="PATCH",
                path=f"/repos/{repository}/issues/comments/{comment_id}",
                payload={"body": body},
            )
            if not isinstance(payload, dict):
                raise GitHubAppCommentError(
                    "updated comment response must be a JSON object",
                    reason_code="COMMENT_API_INVALID_RESPONSE",
                )
            return CommentPublishResult(
                target="pull_request",
                comment_id=int(payload.get("id", comment_id) or comment_id),
                action="updated",
                html_url=str(payload.get("html_url", "")),
            )

        payload = self._request_json(
            method="POST",
            path=f"/repos/{repository}/issues/{pull_request_number}/comments",
            payload={"body": body},
        )
        if not isinstance(payload, dict):
            raise GitHubAppCommentError(
                "created comment response must be a JSON object",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        comment_id = int(payload.get("id", 0) or 0)
        if comment_id <= 0:
            raise GitHubAppCommentError(
                "created comment missing id",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        return CommentPublishResult(
            target="pull_request",
            comment_id=comment_id,
            action="created",
            html_url=str(payload.get("html_url", "")),
        )

    def upsert_commit_comment(
        self,
        *,
        repository: str,
        commit_sha: str,
        body: str,
    ) -> CommentPublishResult:
        comments = self._request_json(
            method="GET",
            path=f"/repos/{repository}/commits/{commit_sha}/comments?per_page=100",
        )
        if not isinstance(comments, list):
            raise GitHubAppCommentError(
                "commit comments response must be a JSON list",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        existing: dict[str, object] | None = None
        for item in comments:
            if not isinstance(item, dict):
                continue
            comment_body = str(item.get("body", ""))
            if APP_COMMENT_MARKER in comment_body:
                existing = item
                break
        if existing is not None:
            comment_id = int(existing.get("id", 0) or 0)
            if comment_id <= 0:
                raise GitHubAppCommentError(
                    "existing commit comment missing id",
                    reason_code="COMMENT_API_INVALID_RESPONSE",
                )
            payload = self._request_json(
                method="PATCH",
                path=f"/repos/{repository}/comments/{comment_id}",
                payload={"body": body},
            )
            if not isinstance(payload, dict):
                raise GitHubAppCommentError(
                    "updated commit comment response must be a JSON object",
                    reason_code="COMMENT_API_INVALID_RESPONSE",
                )
            return CommentPublishResult(
                target="commit",
                comment_id=int(payload.get("id", comment_id) or comment_id),
                action="updated",
                html_url=str(payload.get("html_url", "")),
            )

        payload = self._request_json(
            method="POST",
            path=f"/repos/{repository}/commits/{commit_sha}/comments",
            payload={"body": body},
        )
        if not isinstance(payload, dict):
            raise GitHubAppCommentError(
                "commit comment response must be a JSON object",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        comment_id = int(payload.get("id", 0) or 0)
        if comment_id <= 0:
            raise GitHubAppCommentError(
                "commit comment missing id",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        return CommentPublishResult(
            target="commit",
            comment_id=comment_id,
            action="created",
            html_url=str(payload.get("html_url", "")),
        )

    def upsert_inline_pr_comment(
        self,
        *,
        repository: str,
        pull_request_number: int,
        commit_sha: str,
        path: str,
        line: int,
        body: str,
    ) -> CommentPublishResult:
        comments = self._request_json(
            method="GET",
            path=f"/repos/{repository}/pulls/{pull_request_number}/comments?per_page=100",
        )
        if not isinstance(comments, list):
            raise GitHubAppCommentError(
                "pull request review comments response must be a JSON list",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )

        existing: dict[str, object] | None = None
        for item in comments:
            if not isinstance(item, dict):
                continue
            comment_body = str(item.get("body", ""))
            same_location = (
                str(item.get("path", "")) == path and int(item.get("line", 0) or 0) == line
            )
            if APP_INLINE_COMMENT_MARKER in comment_body and same_location:
                existing = item
                break

        if existing is not None:
            comment_id = int(existing.get("id", 0) or 0)
            if comment_id <= 0:
                raise GitHubAppCommentError(
                    "existing inline comment missing id",
                    reason_code="COMMENT_API_INVALID_RESPONSE",
                )
            payload = self._request_json(
                method="PATCH",
                path=f"/repos/{repository}/pulls/comments/{comment_id}",
                payload={"body": body},
            )
            if not isinstance(payload, dict):
                raise GitHubAppCommentError(
                    "updated inline comment response must be a JSON object",
                    reason_code="COMMENT_API_INVALID_RESPONSE",
                )
            return CommentPublishResult(
                target="pull_request_inline",
                comment_id=int(payload.get("id", comment_id) or comment_id),
                action="updated",
                html_url=str(payload.get("html_url", "")),
            )

        payload = self._request_json(
            method="POST",
            path=f"/repos/{repository}/pulls/{pull_request_number}/comments",
            payload={
                "body": body,
                "commit_id": commit_sha,
                "path": path,
                "line": line,
                "side": "RIGHT",
            },
        )
        if not isinstance(payload, dict):
            raise GitHubAppCommentError(
                "created inline comment response must be a JSON object",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        comment_id = int(payload.get("id", 0) or 0)
        if comment_id <= 0:
            raise GitHubAppCommentError(
                "created inline comment missing id",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        return CommentPublishResult(
            target="pull_request_inline",
            comment_id=comment_id,
            action="created",
            html_url=str(payload.get("html_url", "")),
        )

    def publish_commit_status(
        self,
        *,
        repository: str,
        commit_sha: str,
        state: str,
        description: str,
        target_url: str = "",
        context: str = APP_STATUS_CONTEXT,
    ) -> StatusPublishResult:
        payload: dict[str, object] = {
            "state": state,
            "description": description[:140],
            "context": context,
        }
        if target_url:
            payload["target_url"] = target_url

        response = self._request_json(
            method="POST",
            path=f"/repos/{repository}/statuses/{commit_sha}",
            payload=payload,
        )
        if not isinstance(response, dict):
            raise GitHubAppCommentError(
                "commit status response must be a JSON object",
                reason_code="COMMENT_API_INVALID_RESPONSE",
            )
        return StatusPublishResult(
            context=str(response.get("context", context)),
            state=str(response.get("state", state)),
            target_url=str(response.get("target_url", target_url)),
            api_url=str(response.get("url", "")),
        )
