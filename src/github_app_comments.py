from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error
from urllib import request as urllib_request

APP_COMMENT_MARKER = "<!-- ci-rootcause:app-comment:v1 -->"


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


def build_app_comment_body(
    *,
    classification: str,
    confidence: float,
    primary_root_cause_title: str,
    run_id: str,
    rca_json_path: str,
    rca_md_path: str,
) -> str:
    return "\n".join(
        [
            APP_COMMENT_MARKER,
            "## ci-rootcause RCA",
            f"- Classification: `{classification}`",
            f"- Confidence: `{confidence:.4f}`",
            f"- Primary Root Cause: {primary_root_cause_title or 'unknown'}",
            f"- Run ID: `{run_id}`",
            "",
            "Artifacts:",
            f"- JSON: `{rca_json_path or 'unavailable'}`",
            f"- Markdown: `{rca_md_path or 'unavailable'}`",
        ]
    )


class GitHubAppCommentClient:
    def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
        self._token = token.strip()
        if not self._token:
            raise GitHubAppCommentError(
                "github token is required",
                reason_code="MISSING_GITHUB_TOKEN",
            )
        self._api_base = api_base.rstrip("/")

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
        try:
            with urllib_request.urlopen(req, timeout=30) as response:
                raw = response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GitHubAppCommentError(
                f"GitHub API HTTP error for {method} {path}: {exc.code}: {detail}",
                reason_code="COMMENT_API_HTTP_ERROR",
            ) from exc
        except error.URLError as exc:
            raise GitHubAppCommentError(
                f"GitHub API network error for {method} {path}: {exc}",
                reason_code="COMMENT_API_NETWORK_ERROR",
            ) from exc

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

    def create_commit_comment(
        self,
        *,
        repository: str,
        commit_sha: str,
        body: str,
    ) -> CommentPublishResult:
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
