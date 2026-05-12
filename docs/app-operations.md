# App Operations Guide

## Required Setup

For app-mode webhook processing:
- GitHub App ID.
- GitHub App private key (PEM).
- GitHub App webhook secret.
- Installed GitHub App on the target repository.
- Hosted app server with public HTTPS URL.

The server mints installation tokens at runtime from the App ID, private key,
and `installation.id` in each webhook payload. You do not need to manually
create or paste an installation token.

Deployment and first-run setup:
- [`docs/app-deployment.md`](app-deployment.md)

## Minimum Permissions

GitHub App permissions should include:
- Actions: `read` (to fetch run logs).
- Contents: `read` for comment-only mode; `write` when guarded fix PR creation is enabled.
- Pull requests: `write` (for PR-context comments).
- Issues: `write` (for PR issue comments through the GitHub issues comments API).
- Commit comments: `write` (for commit-context comments when no PR is attached).

## Safe Defaults

Recommended initial repo config:

```json
{
  "enabled": true,
  "mode": "deterministic",
  "allow_repositories": [],
  "deny_repositories": [],
  "post_comment": true,
  "enable_pr_mode": false,
  "create_fix_pr": false,
  "min_pr_confidence": 0.75
}
```

## Delivery Mode

Set `CI_ROOTCAUSE_APP_ASYNC_WEBHOOK=true` for local LLM or slow agentic runs. The server
validates the webhook signature and event shape, returns `202` to GitHub immediately, and
continues RCA/comment/PR processing in a background thread.

In async mode, GitHub's delivery response only confirms acceptance. The final result is
visible in server logs and the posted GitHub comment.

## Health And Webhook Endpoints

- Health check: `GET /healthz`
- GitHub webhook: `POST /webhooks/github`

For hosted deployments, configure the GitHub App webhook URL as:

```text
https://<your-host>/webhooks/github
```

Use `/healthz` as the platform health check path when supported.

## Local Ollama App Run

Use this shape for local app testing with an Ollama-compatible endpoint:

```bash
export GITHUB_APP_ID=<app-id>
export GITHUB_APP_PRIVATE_KEY_PEM="$(cat /path/to/private-key.pem)"
export GITHUB_WEBHOOK_SECRET=<webhook-secret>
export CI_ROOTCAUSE_APP_ASYNC_WEBHOOK=true
export CI_ROOTCAUSE_APP_ENABLED=true
export CI_ROOTCAUSE_APP_POST_COMMENT=true
export CI_ROOTCAUSE_APP_MODE=agentic_assist
export CI_ROOTCAUSE_APP_LLM_PROVIDER=local
export CI_ROOTCAUSE_APP_LLM_MODEL=qwen2.5-coder:3b
export CI_ROOTCAUSE_APP_LLM_BASE_URL=http://localhost:11434
```

For guarded fix PR creation, add:

```bash
export CI_ROOTCAUSE_APP_ENABLE_PR_MODE=true
export CI_ROOTCAUSE_APP_CREATE_FIX_PR=true
export CI_ROOTCAUSE_APP_MIN_PR_CONFIDENCE=0.75
export CI_ROOTCAUSE_APP_MAX_FIX_FILES=5
```

Keep PR mode disabled until comment-only behavior is verified in the target repository.

## Proven Live Smoke Path

The current app flow has been validated with live `workflow_run` deliveries:

- failed PR run produces an RCA comment,
- repeated delivery updates the same comment,
- low-signal regular-CI noise can be suppressed,
- local/Ollama suggestions are accepted when schema-valid,
- validation failures block PR creation,
- passing scoped typecheck fixes can create a reviewable PR that passes repository CI.

## Troubleshooting

- `WEBHOOK_VALIDATION_FAILED`:
  - Check `X-Hub-Signature-256` generation and webhook secret parity.
- GitHub shows `We couldn't deliver this payload` while local LLM processing is enabled:
  - Enable async webhook mode with `CI_ROOTCAUSE_APP_ASYNC_WEBHOOK=true`.
  - Keep synchronous mode only when you need the final RCA JSON directly in the delivery response.
- `WORKFLOW_NOT_COMPLETED` / `WORKFLOW_NOT_FAILED`:
  - Expected skip for non-failed or non-completed workflow runs.
- `REPOSITORY_DISABLED` / `REPOSITORY_NOT_ALLOWLISTED` / `REPOSITORY_DENYLISTED`:
  - Verify repository policy config.
- `WORKFLOW_LOGS_*` or `GITHUB_API_*`:
  - Validate installation token scope and API availability.
- `COMMENT_API_*`:
  - Check `pull-requests`/commit comment permissions and rate limits.

Full reason-code taxonomy:
- [`docs/app-outcome-codes.md`](app-outcome-codes.md)
