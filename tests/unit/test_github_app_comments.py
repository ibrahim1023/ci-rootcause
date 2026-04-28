from __future__ import annotations

import io
import json
from urllib import error

from src.github_app_comments import (
    APP_COMMENT_MARKER,
    GitHubAppCommentClient,
    build_app_comment_body,
)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def test_build_app_comment_body_contains_marker_and_summary_fields() -> None:
    body = build_app_comment_body(
        classification="TEST",
        confidence=0.875,
        primary_root_cause_title="assertion failed",
        run_id="gha_123",
        rca_json_path="artifacts/app/ci-rca.json",
        rca_md_path="artifacts/app/ci-rca.md",
        confidence_reason="file_and_line_evidence, classification_alignment",
    )

    assert APP_COMMENT_MARKER in body
    assert "Classification: `TEST`" in body
    assert "Confidence: `0.8750`" in body
    assert "Confidence reason: file_and_line_evidence, classification_alignment" in body
    assert "Run ID: `gha_123`" in body


def test_upsert_pr_comment_updates_existing_app_comment(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del timeout
        calls.append((req.method, req.full_url))
        if req.method == "GET":
            payload = [
                {
                    "id": 1001,
                    "body": f"{APP_COMMENT_MARKER}\nprevious",
                }
            ]
            return _FakeResponse(json.dumps(payload).encode("utf-8"))
        if req.method == "PATCH":
            payload = {"id": 1001, "html_url": "https://example.com/comment/1001"}
            return _FakeResponse(json.dumps(payload).encode("utf-8"))
        raise AssertionError(f"unexpected method: {req.method}")

    monkeypatch.setattr("src.github_app_comments.urllib_request.urlopen", fake_urlopen)

    client = GitHubAppCommentClient(token="token")
    result = client.upsert_pr_comment(
        repository="acme/project",
        pull_request_number=12,
        body="new body",
    )

    assert result.action == "updated"
    assert result.comment_id == 1001
    assert calls[0][0] == "GET"
    assert calls[1][0] == "PATCH"


def test_upsert_pr_comment_creates_when_existing_not_found(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del timeout
        calls.append((req.method, req.full_url))
        if req.method == "GET":
            return _FakeResponse(b"[]")
        if req.method == "POST":
            payload = {"id": 2002, "html_url": "https://example.com/comment/2002"}
            return _FakeResponse(json.dumps(payload).encode("utf-8"))
        raise AssertionError(f"unexpected method: {req.method}")

    monkeypatch.setattr("src.github_app_comments.urllib_request.urlopen", fake_urlopen)

    client = GitHubAppCommentClient(token="token")
    result = client.upsert_pr_comment(
        repository="acme/project",
        pull_request_number=12,
        body="new body",
    )

    assert result.action == "created"
    assert result.comment_id == 2002
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"


def test_upsert_commit_comment_updates_existing_marker_comment(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del timeout
        calls.append((req.method, req.full_url))
        if req.method == "GET":
            payload = [{"id": 3003, "body": f"{APP_COMMENT_MARKER}\nold"}]
            return _FakeResponse(json.dumps(payload).encode("utf-8"))
        if req.method == "PATCH":
            payload = {"id": 3003, "html_url": "https://example.com/comment/3003"}
            return _FakeResponse(json.dumps(payload).encode("utf-8"))
        raise AssertionError(f"unexpected method: {req.method}")

    monkeypatch.setattr("src.github_app_comments.urllib_request.urlopen", fake_urlopen)

    client = GitHubAppCommentClient(token="token")
    result = client.upsert_commit_comment(
        repository="acme/project",
        commit_sha="abc123",
        body="new body",
    )

    assert result.action == "updated"
    assert result.comment_id == 3003
    assert calls[0][0] == "GET"
    assert calls[1][0] == "PATCH"


def test_upsert_pr_comment_retries_transient_http_errors(monkeypatch) -> None:
    attempts = {"count": 0}

    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del timeout
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise error.HTTPError(
                url=req.full_url,
                code=503,
                msg="Service Unavailable",
                hdrs=None,
                fp=io.BytesIO(b'{"message":"temporary"}'),
            )
        if req.method == "GET":
            return _FakeResponse(b"[]")
        if req.method == "POST":
            payload = {"id": 4040, "html_url": "https://example.com/comment/4040"}
            return _FakeResponse(json.dumps(payload).encode("utf-8"))
        raise AssertionError(f"unexpected method: {req.method}")

    monkeypatch.setattr("src.github_app_comments.urllib_request.urlopen", fake_urlopen)
    monkeypatch.setattr("src.github_app_comments.time.sleep", lambda *_args: None)

    client = GitHubAppCommentClient(token="token", max_retries=2, backoff_seconds=0.0)
    result = client.upsert_pr_comment(repository="acme/project", pull_request_number=12, body="new")

    assert result.comment_id == 4040
    assert attempts["count"] >= 2
