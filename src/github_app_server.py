from __future__ import annotations

import argparse
import json
import os
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from src.github_app_auth import (
    GitHubAppAuthError,
    GitHubAppTokenError,
    mint_github_app_installation_token,
)
from src.github_app_runtime import GitHubAppRepoConfig, process_github_app_webhook
from src.github_app_webhook import (
    GitHubWebhookError,
    handle_github_app_webhook,
)


@dataclass(frozen=True)
class GitHubAppServerConfig:
    app_id: str
    private_key_pem: str
    webhook_secret: str
    api_base: str = "https://api.github.com"
    async_webhook: bool = False


@dataclass(frozen=True)
class ProcessResult:
    status_code: int
    payload: dict[str, Any]


def _parse_bool(value: str, *, default: bool) -> bool:
    text = value.strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    return default


def _parse_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_command_list(value: str) -> tuple[str, ...]:
    normalized = value.replace(";", "\n")
    return tuple(item.strip() for item in normalized.splitlines() if item.strip())


def _parse_float(value: str, *, default: float) -> float:
    text = value.strip()
    if not text:
        return default
    try:
        parsed = float(text)
    except ValueError:
        return default
    if not (0.0 <= parsed <= 1.0):
        return default
    return parsed


def _parse_positive_int(value: str, *, default: int) -> int:
    text = value.strip()
    if not text:
        return default
    try:
        parsed = int(text)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return parsed


def _get_header(headers: dict[str, str], name: str) -> str:
    target = name.strip().lower()
    for key, value in headers.items():
        if key.strip().lower() == target:
            return str(value)
    return ""


def load_repo_config_from_env() -> GitHubAppRepoConfig:
    llm_provider = os.getenv("CI_ROOTCAUSE_APP_LLM_PROVIDER", "").strip() or None
    llm_model = os.getenv("CI_ROOTCAUSE_APP_LLM_MODEL", "").strip() or None
    llm_api_key = os.getenv("CI_ROOTCAUSE_APP_LLM_API_KEY", "").strip() or None
    llm_base_url = os.getenv("CI_ROOTCAUSE_APP_LLM_BASE_URL", "").strip() or None
    return GitHubAppRepoConfig(
        enabled=_parse_bool(os.getenv("CI_ROOTCAUSE_APP_ENABLED", "true"), default=True),
        allow_repositories=_parse_csv(os.getenv("CI_ROOTCAUSE_APP_ALLOW_REPOSITORIES", "")),
        deny_repositories=_parse_csv(os.getenv("CI_ROOTCAUSE_APP_DENY_REPOSITORIES", "")),
        enable_pr_mode=_parse_bool(
            os.getenv("CI_ROOTCAUSE_APP_ENABLE_PR_MODE", "false"),
            default=False,
        ),
        create_fix_pr=_parse_bool(
            os.getenv("CI_ROOTCAUSE_APP_CREATE_FIX_PR", "false"),
            default=False,
        ),
        min_pr_confidence=float(os.getenv("CI_ROOTCAUSE_APP_MIN_PR_CONFIDENCE", "0.75")),
        max_fix_files=_parse_positive_int(
            os.getenv("CI_ROOTCAUSE_APP_MAX_FIX_FILES", "5"),
            default=5,
        ),
        validation_commands=_parse_command_list(
            os.getenv("CI_ROOTCAUSE_APP_VALIDATION_COMMANDS", "")
        ),
        typecheck_validation_commands=_parse_command_list(
            os.getenv("CI_ROOTCAUSE_APP_TYPECHECK_VALIDATION_COMMANDS", "")
        ),
        lint_validation_commands=_parse_command_list(
            os.getenv("CI_ROOTCAUSE_APP_LINT_VALIDATION_COMMANDS", "")
        ),
        test_validation_commands=_parse_command_list(
            os.getenv("CI_ROOTCAUSE_APP_TEST_VALIDATION_COMMANDS", "")
        ),
        execution_mode=os.getenv("CI_ROOTCAUSE_APP_MODE", "deterministic").strip()
        or "deterministic",
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        output_dir=os.getenv("CI_ROOTCAUSE_APP_OUTPUT_DIR", "artifacts/app").strip()
        or "artifacts/app",
        post_comment=_parse_bool(os.getenv("CI_ROOTCAUSE_APP_POST_COMMENT", "true"), default=True),
        min_comment_confidence=_parse_float(
            os.getenv("CI_ROOTCAUSE_APP_MIN_COMMENT_CONFIDENCE", "0.5"),
            default=0.5,
        ),
        output_mode=os.getenv("CI_ROOTCAUSE_APP_OUTPUT_MODE", "summary").strip() or "summary",
    )


def load_server_config_from_env() -> GitHubAppServerConfig:
    app_id = os.getenv("GITHUB_APP_ID", "").strip()
    private_key_pem = os.getenv("GITHUB_APP_PRIVATE_KEY_PEM", "").strip()
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").strip()
    if not app_id:
        raise RuntimeError("GITHUB_APP_ID is required")
    if not private_key_pem:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY_PEM is required")
    if not webhook_secret:
        raise RuntimeError("GITHUB_WEBHOOK_SECRET is required")
    api_base = os.getenv("GITHUB_API_BASE", "https://api.github.com").strip()
    return GitHubAppServerConfig(
        app_id=app_id,
        private_key_pem=private_key_pem,
        webhook_secret=webhook_secret,
        api_base=api_base,
        async_webhook=_parse_bool(
            os.getenv("CI_ROOTCAUSE_APP_ASYNC_WEBHOOK", "false"),
            default=False,
        ),
    )


def _extract_installation_id(body: bytes) -> int:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid webhook payload JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Webhook payload must be a JSON object")

    installation = payload.get("installation")
    if not isinstance(installation, dict):
        raise RuntimeError("Webhook payload is missing installation object")
    installation_id = installation.get("id")
    if not isinstance(installation_id, int) or installation_id <= 0:
        raise RuntimeError("Webhook payload installation.id must be a positive integer")
    return installation_id


def _status_code_for_result(result: dict[str, Any]) -> int:
    status = str(result.get("status", "")).strip().lower()
    if status in {"ok", "partial", "skipped"}:
        return 200

    reason_code = str(result.get("reason_code", "")).strip().upper()
    if reason_code == "WEBHOOK_VALIDATION_FAILED":
        return 401
    if reason_code.startswith("APP_"):
        return 400
    return 500


def process_webhook_request(
    *,
    headers: dict[str, str],
    body: bytes,
    server_config: GitHubAppServerConfig,
    repo_config: GitHubAppRepoConfig,
) -> ProcessResult:
    event_name = _get_header(headers, "X-GitHub-Event").strip().lower()

    if event_name != "workflow_run":
        result = process_github_app_webhook(
            headers=headers,
            body=body,
            webhook_secret=server_config.webhook_secret,
            github_token="unused",
            repo_config=repo_config,
            api_base=server_config.api_base,
        )
        return ProcessResult(status_code=_status_code_for_result(result), payload=result)

    try:
        installation_id = _extract_installation_id(body)
        token = mint_github_app_installation_token(
            app_id=server_config.app_id,
            private_key_pem=server_config.private_key_pem,
            installation_id=installation_id,
            api_base=server_config.api_base,
        )
    except (RuntimeError, GitHubAppAuthError, GitHubAppTokenError) as exc:
        payload = {
            "status": "error",
            "reason_code": "APP_AUTH_ERROR",
            "reason": str(exc),
        }
        return ProcessResult(status_code=400, payload=payload)

    result = process_github_app_webhook(
        headers=headers,
        body=body,
        webhook_secret=server_config.webhook_secret,
        github_token=token.token,
        repo_config=repo_config,
        api_base=server_config.api_base,
    )
    return ProcessResult(status_code=_status_code_for_result(result), payload=result)


def prepare_async_webhook_acceptance(
    *,
    headers: dict[str, str],
    body: bytes,
    server_config: GitHubAppServerConfig,
) -> ProcessResult | None:
    event_name = _get_header(headers, "X-GitHub-Event").strip().lower()
    if event_name != "workflow_run":
        return None

    try:
        webhook_result = handle_github_app_webhook(
            headers=headers,
            body=body,
            webhook_secret=server_config.webhook_secret,
        )
    except GitHubWebhookError as exc:
        return ProcessResult(
            status_code=401,
            payload={
                "status": "error",
                "reason_code": "WEBHOOK_VALIDATION_FAILED",
                "reason": str(exc),
            },
        )

    if not webhook_result.get("handled", False) or webhook_result.get("ignored", False):
        payload = {
            "status": "skipped",
            "reason_code": str(webhook_result.get("reason_code", "UNSUPPORTED_EVENT")),
            "reason": str(webhook_result.get("reason", "")),
            "event": str(webhook_result.get("event", "")),
            "delivery": str(webhook_result.get("delivery", "")),
            "repository": str(webhook_result.get("repository", "")),
            "workflow_run_id": int(webhook_result.get("workflow_run_id", 0) or 0),
        }
        return ProcessResult(status_code=_status_code_for_result(payload), payload=payload)

    payload = {
        "status": "ok",
        "reason_code": "",
        "reason": "workflow_run accepted for background processing",
        "event": str(webhook_result.get("event", "")),
        "delivery": str(webhook_result.get("delivery", "")),
        "repository": str(webhook_result.get("repository", "")),
        "workflow_run_id": int(webhook_result.get("workflow_run_id", 0) or 0),
    }
    return ProcessResult(status_code=202, payload=payload)


def _process_webhook_request_background(
    *,
    headers: dict[str, str],
    body: bytes,
    server_config: GitHubAppServerConfig,
    repo_config: GitHubAppRepoConfig,
) -> None:
    try:
        result = process_webhook_request(
            headers=headers,
            body=body,
            server_config=server_config,
            repo_config=repo_config,
        )
        print(
            "github-app-server async result: " + json.dumps(result.payload, sort_keys=True),
        )
    except Exception as exc:  # pragma: no cover - defensive background guardrail
        print(
            "github-app-server async error: "
            + json.dumps(
                {
                    "status": "error",
                    "reason_code": "APP_ASYNC_WORKER_ERROR",
                    "reason": str(exc),
                },
                sort_keys=True,
            ),
        )


class GitHubAppWebhookHandler(BaseHTTPRequestHandler):
    server_version = "ci-rootcause-github-app/1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._write_json(200, {"status": "ok"})
            return
        self._write_json(404, {"status": "error", "reason": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/webhooks/github":
            self._write_json(404, {"status": "error", "reason": "not found"})
            return

        content_length = self.headers.get("Content-Length", "0").strip() or "0"
        try:
            body_len = int(content_length)
        except ValueError:
            self._write_json(
                400,
                {
                    "status": "error",
                    "reason_code": "APP_INVALID_REQUEST",
                    "reason": "invalid Content-Length",
                },
            )
            return

        body = self.rfile.read(max(0, body_len))
        header_map = {str(key): str(value) for key, value in self.headers.items()}
        server_config = self.server.server_config  # type: ignore[attr-defined]
        repo_config = self.server.repo_config  # type: ignore[attr-defined]
        if server_config.async_webhook:
            acceptance = prepare_async_webhook_acceptance(
                headers=header_map,
                body=body,
                server_config=server_config,
            )
            if acceptance is not None:
                if acceptance.status_code == 202:
                    worker = threading.Thread(
                        target=_process_webhook_request_background,
                        kwargs={
                            "headers": header_map,
                            "body": body,
                            "server_config": server_config,
                            "repo_config": repo_config,
                        },
                        daemon=True,
                    )
                    worker.start()
                self._write_json(acceptance.status_code, acceptance.payload)
                return

        result = process_webhook_request(
            headers=header_map,
            body=body,
            server_config=server_config,
            repo_config=repo_config,
        )
        self._write_json(result.status_code, result.payload)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"github-app-server: {fmt % args}")

    def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local GitHub App webhook server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        server_config = load_server_config_from_env()
        repo_config = load_repo_config_from_env()
    except Exception as exc:
        print(f"github-app-server config error: {exc}")
        return 2

    server = ThreadingHTTPServer((args.host, args.port), GitHubAppWebhookHandler)
    server.server_config = server_config  # type: ignore[attr-defined]
    server.repo_config = repo_config  # type: ignore[attr-defined]

    print(f"github-app-server listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
