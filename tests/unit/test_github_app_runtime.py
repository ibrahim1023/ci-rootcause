from __future__ import annotations

from dataclasses import dataclass

from src.github_app_ingestion import GitHubAppIngestionError, WorkflowRunIngestionPayload
from src.github_app_runtime import GitHubAppRepoConfig, process_github_app_webhook


@dataclass
class _FakeState:
    agent_outputs: dict[str, dict[str, object]]
    pipeline_status: str = "completed"
    failures: list[dict[str, object]] | None = None


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


def test_process_github_app_webhook_check_only_publishes_status_without_comment(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 130,
            "head_sha": "head130",
            "base_sha": "base130",
            "head_branch": "main",
            "pull_request_number": 77,
        },
    )
    monkeypatch.setattr(
        "src.github_app_runtime.collect_workflow_run_inputs",
        lambda **kwargs: WorkflowRunIngestionPayload(  # noqa: ANN003
            repository="acme/project",
            workflow_run_id=130,
            base_sha="base130",
            head_sha="head130",
            raw_log="mypy failed\n",
            raw_diff="diff --git a/src/app.py b/src/app.py\n",
        ),
    )
    monkeypatch.setattr(
        "src.github_app_runtime.run_pipeline",
        lambda request: _FakeState(  # noqa: ARG005
            agent_outputs={
                "failure_classification": {"classification": "TYPECHECK"},
                "root_cause_ranker": {
                    "confidence": 0.9,
                    "primary_root_cause": {"title": "bad argument type"},
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

    class _FakeStatusResult:
        context = "ci-rootcause/rca"
        state = "success"
        target_url = ""
        api_url = "https://api.example.com/status/1"

    class _FakeCommentClient:
        def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
            del token, api_base

        def upsert_pr_comment(self, *, repository: str, pull_request_number: int, body: str):  # noqa: ANN201
            del repository, pull_request_number, body
            raise AssertionError("summary comment should be disabled")

        def upsert_commit_comment(self, *, repository: str, commit_sha: str, body: str):  # noqa: ANN201
            del repository, commit_sha, body
            raise AssertionError("summary comment should be disabled")

        def publish_commit_status(self, **kwargs):  # noqa: ANN003, ANN201
            captured["status_kwargs"] = kwargs
            return _FakeStatusResult()

    monkeypatch.setattr("src.github_app_runtime.GitHubAppCommentClient", _FakeCommentClient)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
        repo_config=GitHubAppRepoConfig(output_mode="check-only"),
    )

    assert result["status"] == "ok"
    assert result["comment_posted"] is False
    assert result["status_posted"] is True
    assert result["status_url"] == "https://api.example.com/status/1"
    assert captured["status_kwargs"]["commit_sha"] == "head130"


def test_process_github_app_webhook_inline_only_posts_mapped_diff_comment(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 131,
            "head_sha": "head131",
            "base_sha": "base131",
            "head_branch": "feature",
            "pull_request_number": 88,
        },
    )
    raw_diff = "\n".join(
        [
            "diff --git a/src/app.py b/src/app.py",
            "--- a/src/app.py",
            "+++ b/src/app.py",
            "@@ -1,3 +1,3 @@",
            " def needs_int(value: int) -> int:",
            "     return value",
            '+needs_int("7")',
        ]
    )
    monkeypatch.setattr(
        "src.github_app_runtime.collect_workflow_run_inputs",
        lambda **kwargs: WorkflowRunIngestionPayload(  # noqa: ANN003
            repository="acme/project",
            workflow_run_id=131,
            base_sha="base131",
            head_sha="head131",
            raw_log="src/app.py:3: error: incompatible type\n",
            raw_diff=raw_diff,
        ),
    )
    monkeypatch.setattr(
        "src.github_app_runtime.run_pipeline",
        lambda request: _FakeState(  # noqa: ARG005
            agent_outputs={
                "failure_classification": {"classification": "TYPECHECK"},
                "root_cause_ranker": {
                    "confidence": 0.82,
                    "primary_root_cause": {
                        "title": "src/app.py:3 incompatible type",
                        "evidence": [{"file": "src/app.py", "line": 3}],
                    },
                },
                "fix_planner": {
                    "fix_steps": [{"instruction": "Pass an integer instead of a string."}]
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

    class _FakeInlineResult:
        target = "pull_request_inline"
        comment_id = 9090
        action = "updated"
        html_url = "https://example.com/inline/9090"

    class _FakeCommentClient:
        def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
            del token, api_base

        def upsert_pr_comment(self, *, repository: str, pull_request_number: int, body: str):  # noqa: ANN201
            del repository, pull_request_number, body
            raise AssertionError("summary comment should be disabled")

        def upsert_inline_pr_comment(self, **kwargs):  # noqa: ANN003, ANN201
            captured["inline_kwargs"] = kwargs
            return _FakeInlineResult()

    monkeypatch.setattr("src.github_app_runtime.GitHubAppCommentClient", _FakeCommentClient)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
        repo_config=GitHubAppRepoConfig(output_mode="inline-only"),
    )

    assert result["status"] == "ok"
    assert result["comment_posted"] is False
    assert result["inline_comment_posted"] is True
    assert result["inline_comment_action"] == "updated"
    assert captured["inline_kwargs"]["path"] == "src/app.py"
    assert captured["inline_kwargs"]["line"] == 3


def test_process_github_app_webhook_suppresses_low_signal_test_comment(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 223,
            "head_sha": "head223",
            "base_sha": "base223",
            "head_branch": "main",
            "pull_request_number": 88,
        },
    )
    monkeypatch.setattr(
        "src.github_app_runtime.collect_workflow_run_inputs",
        lambda **kwargs: WorkflowRunIngestionPayload(  # noqa: ANN003
            repository="acme/project",
            workflow_run_id=223,
            base_sha="base223",
            head_sha="head223",
            raw_log="Optional JSON file containing historical failed run\n",
            raw_diff="diff --git a/a.py b/a.py\n",
        ),
    )
    monkeypatch.setattr(
        "src.github_app_runtime.run_pipeline",
        lambda request: _FakeState(  # noqa: ARG005
            agent_outputs={
                "failure_classification": {"classification": "TEST"},
                "root_cause_ranker": {
                    "confidence": 0.4225,
                    "primary_root_cause": {
                        "title": "Optional JSON file containing historical failed run",
                        "confidence_reasons": ["unknown_file", "first_failure"],
                        "evidence": [{"file": "unknown", "line": None}],
                    },
                },
                "reporter": {
                    "ci_rca_json_path": "artifacts/app/ci-rca.json",
                    "ci_rca_md_path": "artifacts/app/ci-rca.md",
                },
                "pr_creation": {"pr_created": False},
            }
        ),
    )

    class _FakeCommentClient:
        def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
            del token, api_base

        def upsert_pr_comment(self, *, repository: str, pull_request_number: int, body: str):  # noqa: ANN201
            del repository, pull_request_number, body
            raise AssertionError("low-signal comment should be suppressed")

        def upsert_commit_comment(self, *, repository: str, commit_sha: str, body: str):  # noqa: ANN201
            del repository, commit_sha, body
            raise AssertionError("low-signal comment should be suppressed")

    monkeypatch.setattr("src.github_app_runtime.GitHubAppCommentClient", _FakeCommentClient)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
    )

    assert result["status"] == "ok"
    assert result["comment_posted"] is False
    assert result["comment_skipped_reason"] == (
        "confidence 0.4225 is below comment threshold 0.5000 and no file evidence was found"
    )


def test_process_github_app_webhook_keeps_low_confidence_dependency_comment(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 224,
            "head_sha": "head224",
            "base_sha": "base224",
            "head_branch": "main",
            "pull_request_number": 89,
        },
    )
    monkeypatch.setattr(
        "src.github_app_runtime.collect_workflow_run_inputs",
        lambda **kwargs: WorkflowRunIngestionPayload(  # noqa: ANN003
            repository="acme/project",
            workflow_run_id=224,
            base_sha="base224",
            head_sha="head224",
            raw_log="No matching distribution found for missing-package\n",
            raw_diff="diff --git a/requirements.txt b/requirements.txt\n",
        ),
    )
    monkeypatch.setattr(
        "src.github_app_runtime.run_pipeline",
        lambda request: _FakeState(  # noqa: ARG005
            agent_outputs={
                "failure_classification": {"classification": "DEPENDENCY"},
                "root_cause_ranker": {
                    "confidence": 0.3425,
                    "primary_root_cause": {
                        "title": "No matching distribution found",
                        "confidence_reasons": ["unknown_file", "first_failure"],
                        "evidence": [{"file": "unknown", "line": None}],
                    },
                },
                "reporter": {
                    "ci_rca_json_path": "artifacts/app/ci-rca.json",
                    "ci_rca_md_path": "artifacts/app/ci-rca.md",
                },
                "pr_creation": {"pr_created": False},
            }
        ),
    )

    class _FakeCommentResult:
        target = "pull_request"
        comment_id = 224
        action = "created"
        html_url = "https://example.com/comment/224"

    class _FakeCommentClient:
        def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
            del token, api_base

        def upsert_pr_comment(self, *, repository: str, pull_request_number: int, body: str):  # noqa: ANN201
            del repository, pull_request_number, body
            return _FakeCommentResult()

        def upsert_commit_comment(self, *, repository: str, commit_sha: str, body: str):  # noqa: ANN201
            del repository, commit_sha, body
            raise AssertionError("pr comment path should be used")

    monkeypatch.setattr("src.github_app_runtime.GitHubAppCommentClient", _FakeCommentClient)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
    )

    assert result["status"] == "ok"
    assert result["comment_posted"] is True
    assert result["comment_target"] == "pull_request"


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


def test_process_github_app_webhook_prefers_missing_key_reason_over_artifact_symptom(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.github_app_runtime.handle_github_app_webhook",
        lambda headers, body, webhook_secret: {  # noqa: ARG005
            "handled": True,
            "ignored": False,
            "event": "workflow_run",
            "delivery": "d1",
            "repository": "acme/project",
            "workflow_run_id": 205,
            "head_sha": "head205",
            "base_sha": "base205",
            "head_branch": "main",
            "pull_request_number": 12,
        },
    )
    monkeypatch.setattr(
        "src.github_app_runtime.collect_workflow_run_inputs",
        lambda **kwargs: WorkflowRunIngestionPayload(  # noqa: ANN003
            repository="acme/project",
            workflow_run_id=205,
            base_sha="base205",
            head_sha="head205",
            raw_log="pytest failed\n",
            raw_diff="diff --git a/a.py b/a.py\n",
        ),
    )
    monkeypatch.setattr(
        "src.github_app_runtime.run_pipeline",
        lambda request: _FakeState(  # noqa: ARG005
            agent_outputs={
                "failure_classification": {"classification": "TYPECHECK"},
                "root_cause_ranker": {
                    "confidence": 0.54,
                    "primary_root_cause": {"title": "typecheck failed"},
                },
                "reporter": {
                    "ci_rca_json_path": "",
                    "ci_rca_md_path": "",
                },
                "pr_creation": {"pr_created": False},
            },
            pipeline_status="partial",
            failures=[
                {
                    "agent": "fix_planner",
                    "error_type": "AgenticProposalProviderError",
                    "message": "provider api key is required for hosted proposer",
                }
            ],
        ),
    )

    class _FakeCommentResult:
        target = "pull_request"
        comment_id = 12
        action = "updated"
        html_url = "https://example.com/comment/12"

    class _FakeCommentClient:
        def __init__(self, *, token: str, api_base: str = "https://api.github.com") -> None:
            del token, api_base

        def upsert_pr_comment(self, *, repository: str, pull_request_number: int, body: str):  # noqa: ANN201
            del repository, pull_request_number, body
            return _FakeCommentResult()

        def upsert_commit_comment(self, *, repository: str, commit_sha: str, body: str):  # noqa: ANN201
            del repository, commit_sha, body
            raise AssertionError("commit comment path should not be used")

    monkeypatch.setattr("src.github_app_runtime.GitHubAppCommentClient", _FakeCommentClient)

    result = process_github_app_webhook(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b"{}",
        webhook_secret="secret",
        github_token="token",
    )

    assert result["status"] == "partial"
    assert result["reason_code"] == "AGENTIC_MISSING_KEY"
    assert result["reason"] == "provider api key is required for hosted proposer"
    assert result["artifact_output_ok"] is False
    assert result["artifact_output_reason_code"] == "ARTIFACT_OUTPUT_MISSING"
