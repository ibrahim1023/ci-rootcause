from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from src.github_app_webhook import (
    GitHubWebhookPayloadError,
    GitHubWebhookSignatureError,
    handle_github_app_webhook,
)


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_handle_webhook_accepts_valid_workflow_run_failure_event() -> None:
    body = json.dumps({"workflow_run": {"id": 101, "status": "completed", "conclusion": "failure"}})
    raw = body.encode("utf-8")
    secret = "top-secret"
    headers = {
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": "delivery-1",
        "X-Hub-Signature-256": _sign(raw, secret),
    }

    result = handle_github_app_webhook(headers=headers, body=raw, webhook_secret=secret)

    assert result["handled"] is True
    assert result["ignored"] is False
    assert result["event"] == "workflow_run"
    assert result["delivery"] == "delivery-1"
    assert result["workflow_run_id"] == 101
    assert result["should_process_failure"] is True
    assert result["reason_code"] == ""


def test_handle_webhook_ignores_workflow_run_when_not_failed() -> None:
    body = json.dumps({"workflow_run": {"id": 102, "status": "completed", "conclusion": "success"}})
    raw = body.encode("utf-8")
    secret = "top-secret"
    headers = {
        "x-github-event": "workflow_run",
        "x-hub-signature-256": _sign(raw, secret),
    }

    result = handle_github_app_webhook(headers=headers, body=raw, webhook_secret=secret)

    assert result["handled"] is True
    assert result["ignored"] is True
    assert result["reason_code"] == "WORKFLOW_NOT_FAILED"
    assert result["should_process_failure"] is False


def test_handle_webhook_ignores_unsupported_event() -> None:
    body = json.dumps({"action": "opened"})
    raw = body.encode("utf-8")
    secret = "top-secret"
    headers = {
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": _sign(raw, secret),
    }

    result = handle_github_app_webhook(headers=headers, body=raw, webhook_secret=secret)

    assert result["handled"] is False
    assert result["ignored"] is True
    assert result["reason_code"] == "UNSUPPORTED_EVENT"


def test_handle_webhook_rejects_missing_signature() -> None:
    raw = b"{}"
    with pytest.raises(GitHubWebhookSignatureError, match="Missing X-Hub-Signature-256 header"):
        handle_github_app_webhook(
            headers={"X-GitHub-Event": "workflow_run"},
            body=raw,
            webhook_secret="secret",
        )


def test_handle_webhook_rejects_invalid_signature() -> None:
    raw = b"{}"
    with pytest.raises(GitHubWebhookSignatureError, match="Webhook signature verification failed"):
        handle_github_app_webhook(
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-Hub-Signature-256": "sha256=deadbeef",
            },
            body=raw,
            webhook_secret="secret",
        )


def test_handle_webhook_rejects_invalid_json_payload() -> None:
    raw = b"{not-json"
    secret = "secret"
    with pytest.raises(GitHubWebhookPayloadError, match="Invalid webhook JSON payload"):
        handle_github_app_webhook(
            headers={
                "X-GitHub-Event": "workflow_run",
                "X-Hub-Signature-256": _sign(raw, secret),
            },
            body=raw,
            webhook_secret=secret,
        )
