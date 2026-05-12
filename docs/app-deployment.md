# GitHub App Deployment And First Run

This guide covers the first public deployment path for `ci-rootcause` app mode.
The goal is a stable webhook URL that receives GitHub App events and processes
failed GitHub Actions `workflow_run` events.

## Recommended First Deployment

Use a small always-on Python web service for the first hosted deployment. Render,
Railway, Fly.io, a small VPS, or any container/PaaS that can run a long-lived
Python process is enough.

Minimum runtime requirements:

- Python `3.11+`.
- Public HTTPS URL.
- Long-lived process support.
- Environment variable secret storage.
- Writable local filesystem for temporary RCA artifacts, or mounted storage if
  artifacts must persist across restarts.

The app does not require a database for the first deployment. Add persistent run
history later when duplicate delivery tracking and dashboards need to survive
process restarts.

## Runtime Command

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Start the webhook server:

```bash
python -m src.github_app_server --host 0.0.0.0 --port ${PORT:-8000}
```

Health check endpoint:

```text
GET /healthz
```

Webhook endpoint:

```text
POST /webhooks/github
```

## Required Environment Variables

Server credentials:

```bash
GITHUB_APP_ID=<app-id>
GITHUB_APP_PRIVATE_KEY_PEM=<full-private-key-pem>
GITHUB_WEBHOOK_SECRET=<webhook-secret>
```

Recommended safe defaults:

```bash
CI_ROOTCAUSE_APP_ENABLED=true
CI_ROOTCAUSE_APP_POST_COMMENT=true
CI_ROOTCAUSE_APP_ENABLE_PR_MODE=false
CI_ROOTCAUSE_APP_CREATE_FIX_PR=false
CI_ROOTCAUSE_APP_MODE=deterministic
CI_ROOTCAUSE_APP_ASYNC_WEBHOOK=true
CI_ROOTCAUSE_APP_OUTPUT_DIR=artifacts/app
```

Optional PR creation controls:

```bash
CI_ROOTCAUSE_APP_ENABLE_PR_MODE=true
CI_ROOTCAUSE_APP_CREATE_FIX_PR=true
CI_ROOTCAUSE_APP_MIN_PR_CONFIDENCE=0.75
CI_ROOTCAUSE_APP_MAX_FIX_FILES=5
```

Optional local/Ollama-compatible agentic mode:

```bash
CI_ROOTCAUSE_APP_MODE=agentic_assist
CI_ROOTCAUSE_APP_LLM_PROVIDER=local
CI_ROOTCAUSE_APP_LLM_MODEL=qwen2.5-coder:3b
CI_ROOTCAUSE_APP_LLM_BASE_URL=http://localhost:11434
```

Optional hosted agentic mode:

```bash
CI_ROOTCAUSE_APP_MODE=agentic_assist
CI_ROOTCAUSE_APP_LLM_PROVIDER=openai
CI_ROOTCAUSE_APP_LLM_API_KEY=<provider-api-key>
```

Use `gemini` or `anthropic` for `CI_ROOTCAUSE_APP_LLM_PROVIDER` when using those
hosted providers.

## GitHub App Configuration

Set the GitHub App webhook URL to:

```text
https://<your-host>/webhooks/github
```

Subscribe to:

- `workflow_run`

Minimum permissions:

- Actions: `read`
- Contents: `read` for comment-only mode; `write` for guarded fix PR creation
- Pull requests: `write`
- Issues: `write`
- Commit comments: `write`

Install the GitHub App on the repository you want to test.

## One-Click User Flow

The user-facing onboarding should be:

1. Install the GitHub App.
2. Select repositories.
3. Keep safe defaults enabled: comments on, fix PRs off.
4. Push a PR or commit that causes a GitHub Actions workflow to fail.
5. Read the RCA comment on the PR or commit.
6. Enable guarded fix PR creation only after comment-only behavior is trusted.

No workflow YAML is required in the target repository for app mode.

## First-Run Verification Checklist

Before enabling PR creation, verify comment-only mode:

- [ ] `/healthz` returns `{"status":"ok"}`.
- [ ] GitHub webhook delivery to `/webhooks/github` returns `200` or `202`.
- [ ] Failed `workflow_run` events are processed; successful runs are skipped.
- [ ] The app posts or updates an RCA comment on the PR or commit.
- [ ] The comment includes classification, confidence, evidence, suggested fix,
      and app outcome.
- [ ] Server logs include a machine-readable result with `status` and
      `reason_code`.
- [ ] `rca_json_path` and `rca_md_path` are present when artifact output succeeds.
- [ ] Re-delivering the same webhook updates or reuses the existing comment
      instead of creating comment spam.

Then verify PR mode separately:

- [ ] `CI_ROOTCAUSE_APP_ENABLE_PR_MODE=true` is set.
- [ ] `CI_ROOTCAUSE_APP_CREATE_FIX_PR=true` is set.
- [ ] Validation commands are configured for the target failure class.
- [ ] The app blocks low-confidence or validation-failed proposals.
- [ ] Any created fix PR targets the failing branch and does not auto-merge.

## Troubleshooting Links

- Runtime operations: [`docs/app-operations.md`](app-operations.md)
- Config contract: [`docs/app-config-contract.md`](app-config-contract.md)
- Outcome reason codes: [`docs/app-outcome-codes.md`](app-outcome-codes.md)
- App-first scope: [`docs/app-first-mvp.md`](app-first-mvp.md)
