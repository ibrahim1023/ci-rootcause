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


def test_process_github_app_webhook_skips_missing_base_sha_ingestion_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 122,
            "head_sha": "head123",
            "base_sha": "",
            "head_branch": "main",
        },
    )

    def _raise_ingestion(**kwargs):  # noqa: ANN003
        del kwargs
        raise GitHubAppIngestionError(
            "base_sha is required for compare diff retrieval",
            reason_code="MISSING_BASE_SHA",
        )

    monkeypatch.setattr("src.github_app_runtime.collect_workflow_run_inputs", _raise_ingestion)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
    )

    assert result["status"] == "skipped"
    assert result["reason_code"] == "MISSING_BASE_SHA"


def test_process_github_app_webhook_skips_when_repository_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 107,
            "head_sha": "head107",
            "base_sha": "base107",
            "head_branch": "main",
        },
    )

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
        repo_config=GitHubAppRepoConfig(enabled=False),
    )

    assert result["status"] == "skipped"
    assert result["reason_code"] == "REPOSITORY_DISABLED"


def test_process_github_app_webhook_skips_when_repository_not_allowlisted(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 108,
            "head_sha": "head108",
            "base_sha": "base108",
            "head_branch": "main",
        },
    )

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
        repo_config=GitHubAppRepoConfig(allow_repositories=("another/repo",)),
    )

    assert result["status"] == "skipped"
    assert result["reason_code"] == "REPOSITORY_NOT_ALLOWLISTED"


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
            "pull_request_number": 77,
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

    class _FakeCommentResult:
        target = "pull_request"
        comment_id = 1234
        action = "updated"
        html_url = "https://example.com/comment/1234"

    class _FakeCommentClient:
        def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
            del token, api_base

        def upsert_pr_comment(self, *, repository: str, pull_request_number: int, body: str):  # noqa: ANN201
            del body
            captured["comment_target_repo"] = repository
            captured["comment_pr_number"] = pull_request_number
            return _FakeCommentResult()

        def upsert_commit_comment(self, *, repository: str, commit_sha: str, body: str):  # noqa: ANN201
            del repository, commit_sha, body
            raise AssertionError("commit comment path should not be used")

    monkeypatch.setattr("src.github_app_runtime.run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr("src.github_app_runtime.GitHubAppCommentClient", _FakeCommentClient)

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
    assert result["comment_posted"] is True
    assert result["comment_target"] == "pull_request"
    assert captured["comment_pr_number"] == 77


def test_process_github_app_webhook_passes_llm_settings_to_pipeline_request(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 203,
            "head_sha": "head203",
            "base_sha": "base203",
            "head_branch": "main",
            "pull_request_number": 99,
        },
    )
    monkeypatch.setattr(
        "src.github_app_runtime.collect_workflow_run_inputs",
        lambda **kwargs: WorkflowRunIngestionPayload(  # noqa: ANN003
            repository="acme/project",
            workflow_run_id=203,
            base_sha="base203",
            head_sha="head203",
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

    class _FakeCommentResult:
        target = "pull_request"
        comment_id = 777
        action = "created"
        html_url = "https://example.com/comment/777"

    class _FakeCommentClient:
        def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
            del token, api_base

        def upsert_pr_comment(self, *, repository: str, pull_request_number: int, body: str):  # noqa: ANN201
            del repository, pull_request_number, body
            return _FakeCommentResult()

        def upsert_commit_comment(self, *, repository: str, commit_sha: str, body: str):  # noqa: ANN201
            del repository, commit_sha, body
            raise AssertionError("commit comment path should not be used")

    monkeypatch.setattr("src.github_app_runtime.run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr("src.github_app_runtime.GitHubAppCommentClient", _FakeCommentClient)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
        repo_config=GitHubAppRepoConfig(
            execution_mode="agentic_assist",
            llm_provider="local",
            llm_model="qwen2.5-coder:7b",
            llm_base_url="http://localhost:11434",
        ),
    )

    request = captured["request"]
    assert request.execution_mode == "agentic_assist"
    assert request.llm_provider == "local"
    assert request.llm_model == "qwen2.5-coder:7b"
    assert request.llm_base_url == "http://localhost:11434"
    assert result["status"] == "ok"


def test_process_github_app_webhook_requires_explicit_pr_mode_opt_in(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 106,
            "head_sha": "head106",
            "base_sha": "base106",
            "head_branch": "main",
            "pull_request_number": 9,
        },
    )
    monkeypatch.setattr(
        "src.github_app_runtime.collect_workflow_run_inputs",
        lambda **kwargs: WorkflowRunIngestionPayload(  # noqa: ANN003
            repository="acme/project",
            workflow_run_id=106,
            base_sha="base106",
            head_sha="head106",
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

    class _FakeCommentResult:
        target = "pull_request"
        comment_id = 1
        action = "updated"
        html_url = "https://example.com/comment/1"

    class _FakeCommentClient:
        def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
            del token, api_base

        def upsert_pr_comment(self, *, repository: str, pull_request_number: int, body: str):  # noqa: ANN201
            del repository, pull_request_number, body
            return _FakeCommentResult()

        def upsert_commit_comment(self, *, repository: str, commit_sha: str, body: str):  # noqa: ANN201
            del repository, commit_sha, body
            raise AssertionError("commit comment path should not be used")

    monkeypatch.setattr("src.github_app_runtime.run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr("src.github_app_runtime.GitHubAppCommentClient", _FakeCommentClient)

    process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
        repo_config=GitHubAppRepoConfig(create_fix_pr=True, enable_pr_mode=False),
    )

    request = captured["request"]
    assert request.create_fix_pr is False
    assert request.create_fix_pr_disabled_reason == "app_pr_mode_not_enabled"


def test_process_github_app_webhook_falls_back_to_commit_comment(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 104,
            "head_sha": "head456",
            "base_sha": "base456",
            "head_branch": "main",
            "pull_request_number": None,
        },
    )
    monkeypatch.setattr(
        "src.github_app_runtime.collect_workflow_run_inputs",
        lambda **kwargs: WorkflowRunIngestionPayload(  # noqa: ANN003
            repository="acme/project",
            workflow_run_id=104,
            base_sha="base456",
            head_sha="head456",
            raw_log="pytest failed\n",
            raw_diff="diff --git a/a.py b/a.py\n",
        ),
    )
    monkeypatch.setattr(
        "src.github_app_runtime.run_pipeline",
        lambda request: _FakeState(  # noqa: ARG005
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
        ),
    )

    captured = {}

    class _FakeCommentResult:
        target = "commit"
        comment_id = 5678
        action = "created"
        html_url = "https://example.com/comment/5678"

    class _FakeCommentClient:
        def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
            del token, api_base

        def upsert_pr_comment(self, *, repository: str, pull_request_number: int, body: str):  # noqa: ANN201
            del repository, pull_request_number, body
            raise AssertionError("pr comment path should not be used")

        def upsert_commit_comment(self, *, repository: str, commit_sha: str, body: str):  # noqa: ANN201
            del repository, body
            captured["commit_sha"] = commit_sha
            return _FakeCommentResult()

    monkeypatch.setattr("src.github_app_runtime.GitHubAppCommentClient", _FakeCommentClient)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
    )

    assert result["status"] == "ok"
    assert result["comment_posted"] is True
    assert result["comment_target"] == "commit"
    assert captured["commit_sha"] == "head456"


def test_process_github_app_webhook_marks_partial_when_artifact_paths_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 105,
            "head_sha": "head789",
            "base_sha": "base789",
            "head_branch": "main",
            "pull_request_number": None,
        },
    )
    monkeypatch.setattr(
        "src.github_app_runtime.collect_workflow_run_inputs",
        lambda **kwargs: WorkflowRunIngestionPayload(  # noqa: ANN003
            repository="acme/project",
            workflow_run_id=105,
            base_sha="base789",
            head_sha="head789",
            raw_log="pytest failed\n",
            raw_diff="diff --git a/a.py b/a.py\n",
        ),
    )
    monkeypatch.setattr(
        "src.github_app_runtime.run_pipeline",
        lambda request: _FakeState(  # noqa: ARG005
            agent_outputs={
                "failure_classification": {"classification": "TEST"},
                "root_cause_ranker": {
                    "confidence": 0.5,
                    "primary_root_cause": {"title": "missing artifacts"},
                },
                "reporter": {
                    "ci_rca_json_path": "",
                    "ci_rca_md_path": "",
                },
                "pr_creation": {"pr_created": False},
            }
        ),
    )

    class _FakeCommentResult:
        target = "commit"
        comment_id = 1
        action = "created"
        html_url = "https://example.com/comment/1"

    class _FakeCommentClient:
        def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
            del token, api_base

        def upsert_pr_comment(self, *, repository: str, pull_request_number: int, body: str):  # noqa: ANN201
            del repository, pull_request_number, body
            raise AssertionError("pr comment path should not be used")

        def upsert_commit_comment(self, *, repository: str, commit_sha: str, body: str):  # noqa: ANN201
            del repository, commit_sha, body
            return _FakeCommentResult()

    monkeypatch.setattr("src.github_app_runtime.GitHubAppCommentClient", _FakeCommentClient)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
    )

    assert result["status"] == "partial"
    assert result["reason_code"] == "ARTIFACT_OUTPUT_MISSING"
    assert result["artifact_output_ok"] is False
