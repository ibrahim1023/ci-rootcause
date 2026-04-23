from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from urllib import error
from urllib import request as urllib_request


class GitHubAppIngestionError(RuntimeError):
    """Raised when GitHub App ingestion cannot gather pipeline inputs."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class WorkflowRunIngestionPayload:
    repository: str
    workflow_run_id: int
    base_sha: str
    head_sha: str
    raw_log: str
    raw_diff: str


class GitHubAppIngestionClient:
    def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
        self._token = token.strip()
        if not self._token:
            raise GitHubAppIngestionError(
                "github token is required",
                reason_code="MISSING_GITHUB_TOKEN",
            )
        self._api_base = api_base.rstrip("/")

    def _request_bytes(
        self,
        *,
        method: str,
        path: str,
        accept: str = "application/vnd.github+json",
    ) -> bytes:
        url = f"{self._api_base}{path}"
        req = urllib_request.Request(
            url=url,
            method=method,
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib_request.urlopen(req, timeout=30) as response:
                return response.read()
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GitHubAppIngestionError(
                f"GitHub API HTTP error for {method} {path}: {exc.code}: {body}",
                reason_code="GITHUB_API_HTTP_ERROR",
            ) from exc
        except error.URLError as exc:
            raise GitHubAppIngestionError(
                f"GitHub API network error for {method} {path}: {exc}",
                reason_code="GITHUB_API_NETWORK_ERROR",
            ) from exc

    def _request_json(self, *, method: str, path: str) -> dict[str, object]:
        raw = self._request_bytes(method=method, path=path)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubAppIngestionError(
                f"GitHub API response is not valid JSON for {method} {path}: {exc}",
                reason_code="GITHUB_API_INVALID_JSON",
            ) from exc
        if not isinstance(payload, dict):
            raise GitHubAppIngestionError(
                f"GitHub API response must be a JSON object for {method} {path}",
                reason_code="GITHUB_API_INVALID_RESPONSE",
            )
        return payload

    def fetch_workflow_run_logs(self, *, repository: str, workflow_run_id: int) -> str:
        raw = self._request_bytes(
            method="GET",
            path=f"/repos/{repository}/actions/runs/{workflow_run_id}/logs",
            accept="application/vnd.github+json",
        )
        if not raw:
            raise GitHubAppIngestionError(
                "workflow run logs response was empty",
                reason_code="WORKFLOW_LOGS_EMPTY",
            )

        if raw[:2] != b"PK":
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                raise GitHubAppIngestionError(
                    "workflow run logs response had no readable text",
                    reason_code="WORKFLOW_LOGS_UNREADABLE",
                )
            return text + "\n"

        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise GitHubAppIngestionError(
                "workflow run logs response was not a valid zip archive",
                reason_code="WORKFLOW_LOGS_INVALID_ARCHIVE",
            ) from exc

        parts: list[str] = []
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            content = archive.read(info.filename).decode("utf-8", errors="replace").strip()
            parts.append(f"# {info.filename}\n{content}\n")
        if not parts:
            raise GitHubAppIngestionError(
                "workflow run log archive contained no files",
                reason_code="WORKFLOW_LOGS_EMPTY_ARCHIVE",
            )
        return "\n".join(parts).strip() + "\n"

    def fetch_compare_diff(self, *, repository: str, base_sha: str, head_sha: str) -> str:
        payload = self._request_json(
            method="GET",
            path=f"/repos/{repository}/compare/{base_sha}...{head_sha}",
        )
        files = payload.get("files")
        if not isinstance(files, list):
            raise GitHubAppIngestionError(
                "compare API response missing files list",
                reason_code="COMPARE_FILES_MISSING",
            )

        diff_parts: list[str] = []
        file_items = [item for item in files if isinstance(item, dict)]
        for item in sorted(file_items, key=lambda row: str(row.get("filename", ""))):
            filename = str(item.get("filename", "")).strip()
            if not filename:
                continue
            status = str(item.get("status", "modified")).strip().lower() or "modified"
            previous_filename = str(item.get("previous_filename", "")).strip()
            patch = item.get("patch")

            before_file = filename
            after_file = filename
            if status == "renamed" and previous_filename:
                before_file = previous_filename

            diff_parts.append(f"diff --git a/{before_file} b/{after_file}")
            if status == "added":
                diff_parts.append("--- /dev/null")
                diff_parts.append(f"+++ b/{after_file}")
            elif status == "removed":
                diff_parts.append(f"--- a/{before_file}")
                diff_parts.append("+++ /dev/null")
            else:
                diff_parts.append(f"--- a/{before_file}")
                diff_parts.append(f"+++ b/{after_file}")

            if isinstance(patch, str) and patch.strip():
                diff_parts.append(patch.rstrip())
            else:
                diff_parts.append("@@ -0,0 +0,0 @@")
                diff_parts.append("# patch unavailable")

        if not diff_parts:
            raise GitHubAppIngestionError(
                "compare API did not return any diffable files",
                reason_code="COMPARE_DIFF_EMPTY",
            )
        return "\n".join(diff_parts).strip() + "\n"


def collect_workflow_run_inputs(
    *,
    token: str,
    repository: str,
    workflow_run_id: int,
    head_sha: str,
    base_sha: str,
    api_base: str = "https://api.github.com",
) -> WorkflowRunIngestionPayload:
    if not repository.strip():
        raise GitHubAppIngestionError(
            "repository is required",
            reason_code="MISSING_REPOSITORY",
        )
    if workflow_run_id <= 0:
        raise GitHubAppIngestionError(
            "workflow_run_id must be > 0",
            reason_code="INVALID_WORKFLOW_RUN_ID",
        )
    normalized_head = head_sha.strip()
    if not normalized_head:
        raise GitHubAppIngestionError("head_sha is required", reason_code="MISSING_HEAD_SHA")
    normalized_base = base_sha.strip()
    if not normalized_base:
        raise GitHubAppIngestionError(
            "base_sha is required for compare diff retrieval",
            reason_code="MISSING_BASE_SHA",
        )

    client = GitHubAppIngestionClient(token=token, api_base=api_base)
    raw_log = client.fetch_workflow_run_logs(repository=repository, workflow_run_id=workflow_run_id)
    raw_diff = client.fetch_compare_diff(
        repository=repository,
        base_sha=normalized_base,
        head_sha=normalized_head,
    )
    return WorkflowRunIngestionPayload(
        repository=repository,
        workflow_run_id=workflow_run_id,
        base_sha=normalized_base,
        head_sha=normalized_head,
        raw_log=raw_log,
        raw_diff=raw_diff,
    )
