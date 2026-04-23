from __future__ import annotations

import hashlib
import hmac
import io
import json
import zipfile
from dataclasses import dataclass

from src.github_app_runtime import GitHubAppRepoConfig, process_github_app_webhook


@dataclass
class _FakeState:
    agent_outputs: dict[str, dict[str, object]]
    pipeline_status: str = "completed"


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _zip_payload(entries: dict[str, str]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, mode="w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return stream.getvalue()


def test_app_runtime_integration_synthetic_workflow_failure(monkeypatch) -> None:
    body = json.dumps(
        {
            "repository": {"full_name": "acme/project"},
            "workflow_run": {
                "id": 401,
                "run_attempt": 1,
                "name": "CI",
                "head_sha": "head401",
                "head_branch": "main",
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://github.com/acme/project/actions/runs/401",
                "pull_requests": [{"number": 77, "base": {"sha": "base401"}}],
            },
        }
    ).encode("utf-8")
    secret = "webhook-secret"
    headers = {
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": "delivery-401",
        "X-Hub-Signature-256": _sign(body, secret),
    }

    log_zip = _zip_payload({"step.log": "pytest failed"})
    compare_payload = {
        "files": [
            {
                "filename": "src/app.py",
                "status": "modified",
                "patch": "@@ -1 +1 @@\n-print('old')\n+print('new')",
            }
        ]
    }

    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del timeout
        url = req.full_url
        method = req.method
        if url.endswith("/actions/runs/401/logs"):
            return _FakeResponse(log_zip)
        if "/compare/base401...head401" in url:
            return _FakeResponse(json.dumps(compare_payload).encode("utf-8"))
        if url.endswith("/issues/77/comments?per_page=100") and method == "GET":
            return _FakeResponse(b"[]")
        if url.endswith("/issues/77/comments") and method == "POST":
            return _FakeResponse(
                json.dumps(
                    {
                        "id": 901,
                        "html_url": "https://github.com/acme/project/issues/77#issuecomment-901",
                    }
                ).encode("utf-8")
            )
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setattr("src.github_app_ingestion.urllib_request.urlopen", fake_urlopen)
    monkeypatch.setattr("src.github_app_comments.urllib_request.urlopen", fake_urlopen)

    def fake_run_pipeline(request):  # noqa: ANN001
        assert request.raw_log
        assert request.raw_diff
        return _FakeState(
            agent_outputs={
                "failure_classification": {"classification": "TEST"},
                "root_cause_ranker": {
                    "confidence": 0.91,
                    "primary_root_cause": {"title": "assertion failed"},
                },
                "reporter": {
                    "ci_rca_json_path": "artifacts/app/ci-rca.json",
                    "ci_rca_md_path": "artifacts/app/ci-rca.md",
                },
                "pr_creation": {"pr_created": False},
            }
        )

    monkeypatch.setattr("src.github_app_runtime.run_pipeline", fake_run_pipeline)

    result = process_github_app_webhook(
        headers=headers,
        body=body,
        webhook_secret=secret,
        github_token="ghs_token",
        repo_config=GitHubAppRepoConfig(),
    )

    assert result["status"] == "ok"
    assert result["reason_code"] == ""
    assert result["classification"] == "TEST"
    assert result["comment_posted"] is True
    assert result["comment_target"] == "pull_request"
