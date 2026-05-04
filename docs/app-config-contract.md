# App Config Contract (MVP)

Repository-level app configuration schema (logical contract):

```json
{
  "enabled": true,
  "allow_repositories": [],
  "deny_repositories": [],
  "mode": "deterministic",
  "enable_pr_mode": false,
  "create_fix_pr": false,
  "min_pr_confidence": 0.75,
  "validation_commands": [],
  "typecheck_validation_commands": [],
  "lint_validation_commands": [],
  "test_validation_commands": [],
  "post_comment": true
}
```

## Field Notes
- `enabled`:
  - Whether app processing is enabled for the repository.
- `allow_repositories`:
  - Optional allowlist of repository full names (`owner/repo`).
  - If non-empty, repositories not in the list are skipped.
- `deny_repositories`:
  - Optional denylist of repository full names (`owner/repo`).
  - Denylist takes precedence over allowlist.
- `mode`:
  - `deterministic` | `agentic_assist` | `agentic_full`.
  - MVP default: `deterministic`.
- `create_fix_pr`:
  - Must default to `false`.
  - Has effect only when `enable_pr_mode=true`.
- `enable_pr_mode`:
  - Explicit opt-in gate for app-driven PR creation.
  - Must default to `false`.
  - When `false`, app mode keeps comment/artifact-only behavior.
- `min_pr_confidence`:
  - Float in `[0.0, 1.0]`.
- `validation_commands`:
  - Optional generic validation commands for guarded PR creation.
- `typecheck_validation_commands`:
  - Optional commands used only for `TYPECHECK` failures.
- `lint_validation_commands`:
  - Optional commands used only for `LINT` failures.
- `test_validation_commands`:
  - Optional commands used only for `TEST` failures.
- `post_comment`:
  - Whether app posts RCA summary comment for failed runs.

## Environment Mapping
Server credentials:
- `GITHUB_APP_ID`
- `GITHUB_APP_PRIVATE_KEY_PEM`
- `GITHUB_WEBHOOK_SECRET`
- `GITHUB_API_BASE` (optional; defaults to `https://api.github.com`)

Processing controls:
- `CI_ROOTCAUSE_APP_ASYNC_WEBHOOK`
- `CI_ROOTCAUSE_APP_ENABLED`
- `CI_ROOTCAUSE_APP_ALLOW_REPOSITORIES`
- `CI_ROOTCAUSE_APP_DENY_REPOSITORIES`
- `CI_ROOTCAUSE_APP_ENABLE_PR_MODE`
- `CI_ROOTCAUSE_APP_CREATE_FIX_PR`
- `CI_ROOTCAUSE_APP_MIN_PR_CONFIDENCE`
- `CI_ROOTCAUSE_APP_MODE`
- `CI_ROOTCAUSE_APP_OUTPUT_DIR`
- `CI_ROOTCAUSE_APP_POST_COMMENT`

Agentic provider controls:
- `CI_ROOTCAUSE_APP_LLM_PROVIDER` (`openai`, `gemini`, `anthropic`, or `local`)
- `CI_ROOTCAUSE_APP_LLM_MODEL`
- `CI_ROOTCAUSE_APP_LLM_API_KEY`
- `CI_ROOTCAUSE_APP_LLM_BASE_URL` (for local/Ollama-compatible endpoints)

Validation command controls:
- `CI_ROOTCAUSE_APP_VALIDATION_COMMANDS`
- `CI_ROOTCAUSE_APP_TYPECHECK_VALIDATION_COMMANDS`
- `CI_ROOTCAUSE_APP_LINT_VALIDATION_COMMANDS`
- `CI_ROOTCAUSE_APP_TEST_VALIDATION_COMMANDS`

Command lists accept semicolon or newline separators.

`CI_ROOTCAUSE_APP_ASYNC_WEBHOOK=true` makes the webhook server acknowledge failed
`workflow_run` deliveries before slower RCA/comment/PR processing starts.

## Deterministic Defaults
- No automatic PR creation.
- Failure-safe handling when logs/diffs are missing.
- Machine-readable reason codes for skip/failure outcomes.
