from __future__ import annotations

import io
import json
import zipfile
from urllib import error

import pytest

from src.github_app_ingestion import (
    GitHubAppIngestionClient,
    GitHubAppIngestionError,
    collect_workflow_run_inputs,
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


def _zip_payload(entries: dict[str, str]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, mode="w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return stream.getvalue()


def test_fetch_workflow_run_logs_from_zip_is_deterministic(monkeypatch) -> None:
    payload = _zip_payload(
        {
            "z-step.txt": "z-line",
            "a-step.txt": "a-line",
        }
    )

    monkeypatch.setattr(
        "src.github_app_ingestion.urllib_request.urlopen",
        lambda req, timeout: _FakeResponse(payload),  # noqa: ARG005, ANN001
    )

    client = GitHubAppIngestionClient(token="token")
    raw_log = client.fetch_workflow_run_logs(repository="acme/project", workflow_run_id=100)

    assert raw_log.startswith("# a-step.txt")
    assert "# z-step.txt" in raw_log


def test_fetch_workflow_run_logs_rejects_empty_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_ingestion.urllib_request.urlopen",
        lambda req, timeout: _FakeResponse(b""),  # noqa: ARG005, ANN001
    )
    client = GitHubAppIngestionClient(token="token")

    with pytest.raises(GitHubAppIngestionError) as exc:
        client.fetch_workflow_run_logs(repository="acme/project", workflow_run_id=100)
    assert exc.value.reason_code == "WORKFLOW_LOGS_EMPTY"


def test_fetch_compare_diff_builds_unified_patch(monkeypatch) -> None:
    compare_payload = {
        "files": [
            {
                "filename": "src/a.py",
                "status": "modified",
                "patch": "@@ -1 +1 @@\n-print('old')\n+print('new')",
            },
            {
                "filename": "src/new.py",
                "status": "added",
                "patch": "@@ -0,0 +1 @@\n+print('added')",
            },
        ]
    }
    monkeypatch.setattr(
        "src.github_app_ingestion.urllib_request.urlopen",
        lambda req, timeout: _FakeResponse(json.dumps(compare_payload).encode("utf-8")),  # noqa: ARG005, ANN001
    )

    client = GitHubAppIngestionClient(token="token")
    diff = client.fetch_compare_diff(
        repository="acme/project",
        base_sha="base123",
        head_sha="head123",
    )

    assert "diff --git a/src/a.py b/src/a.py" in diff
    assert "diff --git a/src/new.py b/src/new.py" in diff
    assert "@@ -1 +1 @@" in diff


def test_collect_workflow_run_inputs_requires_base_sha() -> None:
    with pytest.raises(GitHubAppIngestionError) as exc:
        collect_workflow_run_inputs(
            token="token",
            repository="acme/project",
            workflow_run_id=100,
            head_sha="head123",
            base_sha="",
        )
    assert exc.value.reason_code == "MISSING_BASE_SHA"


def test_collect_workflow_run_inputs_chains_log_and_diff_fetch(monkeypatch) -> None:
    zip_payload = _zip_payload({"step.txt": "pytest failed"})
    compare_payload = {
        "files": [
            {
                "filename": "src/a.py",
                "status": "modified",
                "patch": "@@ -1 +1 @@\n-a\n+b",
            }
        ]
    }

    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del timeout
        url = req.full_url
        if url.endswith("/actions/runs/200/logs"):
            return _FakeResponse(zip_payload)
        if "/compare/" in url:
            return _FakeResponse(json.dumps(compare_payload).encode("utf-8"))
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("src.github_app_ingestion.urllib_request.urlopen", fake_urlopen)

    payload = collect_workflow_run_inputs(
        token="token",
        repository="acme/project",
        workflow_run_id=200,
        head_sha="head123",
        base_sha="base123",
    )

    assert payload.repository == "acme/project"
    assert payload.workflow_run_id == 200
    assert "pytest failed" in payload.raw_log
    assert "diff --git a/src/a.py b/src/a.py" in payload.raw_diff


def test_fetch_workflow_run_logs_raises_typed_http_error(monkeypatch) -> None:
    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del req, timeout
        raise error.HTTPError(
            url="https://api.github.com/repos/acme/project/actions/runs/100/logs",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"not found"}'),
        )

    monkeypatch.setattr("src.github_app_ingestion.urllib_request.urlopen", fake_urlopen)

    client = GitHubAppIngestionClient(token="token")
    with pytest.raises(GitHubAppIngestionError) as exc:
        client.fetch_workflow_run_logs(repository="acme/project", workflow_run_id=100)
    assert exc.value.reason_code == "GITHUB_API_HTTP_ERROR"
