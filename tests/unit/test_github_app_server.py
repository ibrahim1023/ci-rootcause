from __future__ import annotations

import hashlib
import hmac
import json

from src.github_app_runtime import GitHubAppRepoConfig
from src.github_app_server import (
    GitHubAppServerConfig,
    load_repo_config_from_env,
    load_server_config_from_env,
    prepare_async_webhook_acceptance,
    process_webhook_request,
)


def _server_config() -> GitHubAppServerConfig:
    return GitHubAppServerConfig(
        app_id="123",
        private_key_pem="-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
        webhook_secret="secret",
    )


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _workflow_run_body(*, conclusion: str = "failure") -> bytes:
    return json.dumps(
        {
            "installation": {"id": 456},
            "repository": {"full_name": "acme/project"},
            "workflow_run": {
                "id": 101,
                "run_attempt": 1,
                "name": "CI",
                "head_sha": "abc123",
                "head_branch": "main",
                "status": "completed",
                "conclusion": conclusion,
                "html_url": "https://github.com/acme/project/actions/runs/101",
                "pull_requests": [{"base": {"sha": "def456"}}],
            },
        }
    ).encode("utf-8")


def test_process_webhook_request_unsupported_event_skips_without_token_mint(monkeypatch) -> None:
    called: dict[str, object] = {}

    def _fake_process(**kwargs):  # noqa: ANN003
        called["github_token"] = kwargs["github_token"]
        return {
            "status": "skipped",
            "reason_code": "UNSUPPORTED_EVENT",
            "reason": "ignored",
        }

    monkeypatch.setattr("src.github_app_server.process_github_app_webhook", _fake_process)

    result = process_webhook_request(
        headers={"X-GitHub-Event": "ping"},
        body=b"{}",
        server_config=_server_config(),
        repo_config=GitHubAppRepoConfig(),
    )

    assert result.status_code == 200
    assert result.payload["status"] == "skipped"
    assert called["github_token"] == "unused"


def test_process_webhook_request_workflow_run_mints_installation_token(monkeypatch) -> None:
    def _fake_mint(**kwargs):  # noqa: ANN003
        assert kwargs["installation_id"] == 456

        class _Token:
            token = "ghs_test_token"

        return _Token()

    def _fake_process(**kwargs):  # noqa: ANN003
        assert kwargs["github_token"] == "ghs_test_token"
        return {"status": "ok", "reason_code": "", "reason": ""}

    monkeypatch.setattr("src.github_app_server.mint_github_app_installation_token", _fake_mint)
    monkeypatch.setattr("src.github_app_server.process_github_app_webhook", _fake_process)

    body = b'{"installation":{"id":456},"workflow_run":{"id":1},"repository":{"full_name":"o/r"}}'
    result = process_webhook_request(
        headers={"X-GitHub-Event": "workflow_run"},
        body=body,
        server_config=_server_config(),
        repo_config=GitHubAppRepoConfig(),
    )

    assert result.status_code == 200
    assert result.payload["status"] == "ok"


def test_process_webhook_request_missing_installation_returns_auth_error() -> None:
    result = process_webhook_request(
        headers={"X-GitHub-Event": "workflow_run"},
        body=b'{"workflow_run":{"id":1}}',
        server_config=_server_config(),
        repo_config=GitHubAppRepoConfig(),
    )

    assert result.status_code == 400
    assert result.payload["status"] == "error"
    assert result.payload["reason_code"] == "APP_AUTH_ERROR"
    assert "installation" in result.payload["reason"].lower()


def test_load_repo_config_from_env_reads_llm_settings(monkeypatch) -> None:
    monkeypatch.setenv("CI_ROOTCAUSE_APP_LLM_PROVIDER", "local")
    monkeypatch.setenv("CI_ROOTCAUSE_APP_LLM_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("CI_ROOTCAUSE_APP_LLM_BASE_URL", "http://localhost:11434")

    config = load_repo_config_from_env()

    assert config.llm_provider == "local"
    assert config.llm_model == "qwen2.5-coder:7b"
    assert config.llm_base_url == "http://localhost:11434"


def test_load_repo_config_from_env_reads_comment_confidence_threshold(monkeypatch) -> None:
    monkeypatch.setenv("CI_ROOTCAUSE_APP_MIN_COMMENT_CONFIDENCE", "0.65")

    config = load_repo_config_from_env()

    assert config.min_comment_confidence == 0.65


def test_load_repo_config_from_env_reads_validation_commands(monkeypatch) -> None:
    monkeypatch.setenv("CI_ROOTCAUSE_APP_VALIDATION_COMMANDS", "pytest;ruff check .")
    monkeypatch.setenv(
        "CI_ROOTCAUSE_APP_TYPECHECK_VALIDATION_COMMANDS",
        "python -m mypy src\npython -m pyright src",
    )
    monkeypatch.setenv("CI_ROOTCAUSE_APP_LINT_VALIDATION_COMMANDS", "ruff check src")
    monkeypatch.setenv("CI_ROOTCAUSE_APP_TEST_VALIDATION_COMMANDS", "pytest tests/unit")

    config = load_repo_config_from_env()

    assert config.validation_commands == ("pytest", "ruff check .")
    assert config.typecheck_validation_commands == (
        "python -m mypy src",
        "python -m pyright src",
    )
    assert config.lint_validation_commands == ("ruff check src",)
    assert config.test_validation_commands == ("pytest tests/unit",)


def test_load_server_config_from_env_reads_async_flag(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv(
        "GITHUB_APP_PRIVATE_KEY_PEM",
        "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
    )
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("CI_ROOTCAUSE_APP_ASYNC_WEBHOOK", "true")

    config = load_server_config_from_env()

    assert config.async_webhook is True


def test_prepare_async_webhook_acceptance_returns_202_for_failed_workflow_run() -> None:
    secret = "secret"
    body = _workflow_run_body()
    result = prepare_async_webhook_acceptance(
        headers={
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "delivery-1",
            "X-Hub-Signature-256": _sign(body, secret),
        },
        body=body,
        server_config=GitHubAppServerConfig(
            app_id="123",
            private_key_pem="pem",
            webhook_secret=secret,
            async_webhook=True,
        ),
    )

    assert result is not None
    assert result.status_code == 202
    assert result.payload["status"] == "ok"
    assert result.payload["reason"] == "workflow_run accepted for background processing"
    assert result.payload["repository"] == "acme/project"
    assert result.payload["workflow_run_id"] == 101


def test_prepare_async_webhook_acceptance_keeps_skips_synchronous() -> None:
    secret = "secret"
    body = _workflow_run_body(conclusion="success")
    result = prepare_async_webhook_acceptance(
        headers={
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": "delivery-1",
            "X-Hub-Signature-256": _sign(body, secret),
        },
        body=body,
        server_config=GitHubAppServerConfig(
            app_id="123",
            private_key_pem="pem",
            webhook_secret=secret,
            async_webhook=True,
        ),
    )

    assert result is not None
    assert result.status_code == 200
    assert result.payload["status"] == "skipped"
    assert result.payload["reason_code"] == "WORKFLOW_NOT_FAILED"


def test_prepare_async_webhook_acceptance_rejects_bad_signature() -> None:
    body = _workflow_run_body()
    result = prepare_async_webhook_acceptance(
        headers={
            "X-GitHub-Event": "workflow_run",
            "X-Hub-Signature-256": "sha256=bad",
        },
        body=body,
        server_config=GitHubAppServerConfig(
            app_id="123",
            private_key_pem="pem",
            webhook_secret="secret",
            async_webhook=True,
        ),
    )

    assert result is not None
    assert result.status_code == 401
    assert result.payload["reason_code"] == "WEBHOOK_VALIDATION_FAILED"
