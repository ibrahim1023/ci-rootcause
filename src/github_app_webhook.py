from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any, Callable

from src.github_app_events import GitHubAppEventPayloadError, parse_workflow_run_event


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
    try:
        event = parse_workflow_run_event(payload)
    except GitHubAppEventPayloadError as exc:
        return {
            "handled": False,
            "ignored": False,
            "reason_code": exc.reason_code,
            "reason": str(exc),
            "should_process_failure": False,
        }
    if event.status != "completed":
        return {
            "handled": True,
            "ignored": True,
            "reason_code": "WORKFLOW_NOT_COMPLETED",
            "reason": "workflow_run status is not completed",
            "workflow_run_id": event.workflow_run_id,
            "workflow_run_attempt": event.workflow_run_attempt,
            "status": event.status,
            "conclusion": event.conclusion,
            "repository": event.repository,
            "head_sha": event.head_sha,
            "base_sha": event.base_sha,
            "pull_request_number": event.pull_request_number,
            "head_branch": event.head_branch,
            "workflow_run_name": event.workflow_run_name,
            "workflow_run_url": event.html_url,
            "should_process_failure": False,
        }

    should_process_failure = event.is_failure

    return {
        "handled": True,
        "ignored": not should_process_failure,
        "reason_code": "" if should_process_failure else "WORKFLOW_NOT_FAILED",
        "reason": "" if should_process_failure else "workflow_run conclusion is not failure",
        "workflow_run_id": event.workflow_run_id,
        "workflow_run_attempt": event.workflow_run_attempt,
        "status": event.status,
        "conclusion": event.conclusion,
        "repository": event.repository,
        "head_sha": event.head_sha,
        "base_sha": event.base_sha,
        "pull_request_number": event.pull_request_number,
        "head_branch": event.head_branch,
        "workflow_run_name": event.workflow_run_name,
        "workflow_run_url": event.html_url,
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
