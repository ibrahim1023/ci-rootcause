from __future__ import annotations

import pytest

from src.github_app_events import GitHubAppEventPayloadError, parse_workflow_run_event


def _payload(*, conclusion: str = "failure") -> dict[str, object]:
    return {
        "repository": {"full_name": "acme/project"},
        "workflow_run": {
            "id": 123,
            "run_attempt": 1,
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
    assert parsed.workflow_run_attempt == 1
    assert parsed.base_sha == "def456"
    assert parsed.pull_request_number is None
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


def test_parse_workflow_run_event_rejects_invalid_run_attempt_reason_code() -> None:
    payload = _payload()
    payload["workflow_run"]["run_attempt"] = 0

    with pytest.raises(GitHubAppEventPayloadError) as exc:
        parse_workflow_run_event(payload)
    assert exc.value.reason_code == "INVALID_WORKFLOW_RUN_ATTEMPT"


def test_parse_workflow_run_event_allows_blank_conclusion_when_not_completed() -> None:
    payload = _payload()
    payload["workflow_run"]["status"] = "in_progress"
    payload["workflow_run"]["conclusion"] = None

    parsed = parse_workflow_run_event(payload)
    assert parsed.status == "in_progress"
    assert parsed.conclusion == ""
    assert parsed.is_failure is False


def test_parse_workflow_run_event_reads_pull_request_number() -> None:
    payload = _payload()
    payload["workflow_run"]["pull_requests"] = [
        {"number": 321, "base": {"sha": "def456"}},
    ]

    parsed = parse_workflow_run_event(payload)
    assert parsed.pull_request_number == 321
