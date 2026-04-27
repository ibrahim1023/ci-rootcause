from __future__ import annotations

from src.github_app_runtime import GitHubAppRepoConfig
from src.github_app_server import GitHubAppServerConfig, process_webhook_request


def _server_config() -> GitHubAppServerConfig:
    return GitHubAppServerConfig(
        app_id="123",
        private_key_pem="-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
        webhook_secret="secret",
    )


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
