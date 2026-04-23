# App Operations Guide

## Required Setup

For app-mode webhook processing:
- GitHub App webhook secret.
- GitHub installation access token for the target repository installation.

Optional (if minting installation tokens in runtime):
- GitHub App ID.
- GitHub App private key (PEM).
- Installation ID from webhook/install context.

## Minimum Permissions

GitHub App permissions should include:
- Actions: `read` (to fetch run logs).
- Contents: `read` (to retrieve compare context).
- Pull requests: `write` (for PR-context comments).
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

## Troubleshooting

- `WEBHOOK_VALIDATION_FAILED`:
  - Check `X-Hub-Signature-256` generation and webhook secret parity.
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
