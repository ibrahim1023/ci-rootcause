from __future__ import annotations

from dataclasses import dataclass

from src.github_app_ingestion import GitHubAppIngestionError, WorkflowRunIngestionPayload
from src.github_app_runtime import GitHubAppRepoConfig, process_github_app_webhook


@dataclass
class _FakeState:
    agent_outputs: dict[str, dict[str, object]]
    pipeline_status: str = "completed"


def test_process_github_app_webhook_skips_ignored_events(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": True,
            "reason_code": "WORKFLOW_NOT_FAILED",
            "reason": "workflow_run conclusion is not failure",
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 101,
        },
    )

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
    )

    assert result["status"] == "skipped"
    assert result["reason_code"] == "WORKFLOW_NOT_FAILED"


def test_process_github_app_webhook_maps_ingestion_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 102,
            "head_sha": "head123",
            "base_sha": "base123",
            "head_branch": "main",
        },
    )

    def _raise_ingestion(**kwargs):  # noqa: ANN003
        del kwargs
        raise GitHubAppIngestionError(
            "unable to fetch logs",
            reason_code="WORKFLOW_LOGS_EMPTY",
        )

    monkeypatch.setattr("src.github_app_runtime.collect_workflow_run_inputs", _raise_ingestion)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
    )

    assert result["status"] == "error"
    assert result["reason_code"] == "WORKFLOW_LOGS_EMPTY"


def test_process_github_app_webhook_runs_pipeline_with_safe_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 103,
            "head_sha": "head123",
            "base_sha": "base123",
            "head_branch": "main",
        },
    )
    monkeypatch.setattr(
        "src.github_app_runtime.collect_workflow_run_inputs",
        lambda **kwargs: WorkflowRunIngestionPayload(  # noqa: ANN003
            repository="acme/project",
            workflow_run_id=103,
            base_sha="base123",
            head_sha="head123",
            raw_log="pytest failed\n",
            raw_diff="diff --git a/a.py b/a.py\n",
        ),
    )

    captured = {}

    def _fake_run_pipeline(request):  # noqa: ANN001
        captured["request"] = request
        return _FakeState(
            agent_outputs={
                "failure_classification": {"classification": "TEST"},
                "root_cause_ranker": {
                    "confidence": 0.9,
                    "primary_root_cause": {"title": "assertion failed"},
                },
                "reporter": {
                    "ci_rca_json_path": "artifacts/app/ci-rca.json",
                    "ci_rca_md_path": "artifacts/app/ci-rca.md",
                },
                "pr_creation": {"pr_created": False},
            }
        )

    monkeypatch.setattr("src.github_app_runtime.run_pipeline", _fake_run_pipeline)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
        repo_config=GitHubAppRepoConfig(),
    )

    request = captured["request"]
    assert request.create_fix_pr is False
    assert request.execution_mode == "deterministic"
    assert result["status"] == "ok"
    assert result["classification"] == "TEST"
    assert result["rca_json_path"] == "artifacts/app/ci-rca.json"
