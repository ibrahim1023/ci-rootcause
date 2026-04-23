from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any, Callable


class GitHubWebhookError(RuntimeError):
    """Base class for GitHub App webhook handling errors."""


class GitHubWebhookSignatureError(GitHubWebhookError):
    """Raised when webhook signature verification fails."""


class GitHubWebhookPayloadError(GitHubWebhookError):
    """Raised when webhook headers/payload are invalid."""


WebhookHandler = Callable[[dict[str, Any]], dict[str, Any]]


def _get_header(headers: Mapping[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return str(value)
    return ""


def verify_github_webhook_signature(
    headers: Mapping[str, str],
    body: bytes,
    webhook_secret: str,
) -> None:
    signature = _get_header(headers, "X-Hub-Signature-256").strip()
    if not signature:
        raise GitHubWebhookSignatureError("Missing X-Hub-Signature-256 header")
    if not signature.startswith("sha256="):
        raise GitHubWebhookSignatureError("Invalid X-Hub-Signature-256 header format")
    if not webhook_secret.strip():
        raise GitHubWebhookSignatureError("Webhook secret must not be empty")

    expected_digest = hmac.new(
        webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    provided_digest = signature.split("=", maxsplit=1)[1].strip()
    if not hmac.compare_digest(expected_digest, provided_digest):
        raise GitHubWebhookSignatureError("Webhook signature verification failed")


def parse_github_webhook_event(
    headers: Mapping[str, str],
    body: bytes,
) -> tuple[str, str, dict[str, Any]]:
    event_name = _get_header(headers, "X-GitHub-Event").strip()
    if not event_name:
        raise GitHubWebhookPayloadError("Missing X-GitHub-Event header")

    delivery = _get_header(headers, "X-GitHub-Delivery").strip()

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubWebhookPayloadError(f"Invalid webhook JSON payload: {exc}") from exc

    if not isinstance(payload, dict):
        raise GitHubWebhookPayloadError("Webhook payload must be a JSON object")

    return event_name, delivery, payload


def _handle_workflow_run(payload: dict[str, Any]) -> dict[str, Any]:
    workflow_run = payload.get("workflow_run")
    if not isinstance(workflow_run, dict):
        return {
            "handled": False,
            "ignored": False,
            "reason_code": "INVALID_WORKFLOW_RUN_PAYLOAD",
            "reason": "workflow_run object missing in webhook payload",
            "should_process_failure": False,
        }

    conclusion = str(workflow_run.get("conclusion", "")).strip().lower()
    status = str(workflow_run.get("status", "")).strip().lower()
    should_process_failure = conclusion == "failure"

    return {
        "handled": True,
        "ignored": not should_process_failure,
        "reason_code": "" if should_process_failure else "WORKFLOW_NOT_FAILED",
        "reason": "" if should_process_failure else "workflow_run conclusion is not failure",
        "workflow_run_id": workflow_run.get("id"),
        "status": status,
        "conclusion": conclusion,
        "should_process_failure": should_process_failure,
    }


def _handlers() -> dict[str, WebhookHandler]:
    return {
        "workflow_run": _handle_workflow_run,
    }


def handle_github_app_webhook(
    headers: Mapping[str, str],
    body: bytes,
    webhook_secret: str,
) -> dict[str, Any]:
    verify_github_webhook_signature(
        headers=headers,
        body=body,
        webhook_secret=webhook_secret,
    )
    event_name, delivery, payload = parse_github_webhook_event(headers=headers, body=body)

    handler = _handlers().get(event_name)
    if handler is None:
        return {
            "handled": False,
            "ignored": True,
            "event": event_name,
            "delivery": delivery,
            "reason_code": "UNSUPPORTED_EVENT",
            "reason": f"event '{event_name}' is not supported",
        }

    result = handler(payload)
    return {
        **result,
        "event": event_name,
        "delivery": delivery,
    }
