from __future__ import annotations

import pytest

from src.github_app_events import GitHubAppEventPayloadError, parse_workflow_run_event


def _payload(*, conclusion: str = "failure") -> dict[str, object]:
    return {
        "repository": {"full_name": "acme/project"},
        "workflow_run": {
            "id": 123,
            "name": "CI",
            "head_sha": "abc123",
            "head_branch": "main",
            "status": "completed",
            "conclusion": conclusion,
            "html_url": "https://github.com/acme/project/actions/runs/123",
            "pull_requests": [{"base": {"sha": "def456"}}],
        },
    }


def test_parse_workflow_run_event_success_failure() -> None:
    parsed = parse_workflow_run_event(_payload(conclusion="failure"))
    assert parsed.repository == "acme/project"
    assert parsed.workflow_run_id == 123
    assert parsed.base_sha == "def456"
    assert parsed.is_failure is True


def test_parse_workflow_run_event_success_non_failure() -> None:
    parsed = parse_workflow_run_event(_payload(conclusion="success"))
    assert parsed.base_sha == "def456"
    assert parsed.conclusion == "success"
    assert parsed.is_failure is False


def test_parse_workflow_run_event_missing_repository_name_reason_code() -> None:
    payload = _payload()
    payload["repository"] = {}

    with pytest.raises(GitHubAppEventPayloadError) as exc:
        parse_workflow_run_event(payload)
    assert exc.value.reason_code == "MISSING_REPOSITORY_FULL_NAME"


def test_parse_workflow_run_event_invalid_run_id_reason_code() -> None:
    payload = _payload()
    payload["workflow_run"]["id"] = 0

    with pytest.raises(GitHubAppEventPayloadError) as exc:
        parse_workflow_run_event(payload)
    assert exc.value.reason_code == "INVALID_WORKFLOW_RUN_ID"
