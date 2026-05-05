# App-First Product Scope

## Objective
Enable a no-YAML onboarding path where users install a GitHub App and automatically
receive root-cause analysis on failed CI runs.

## Current Scope
- Event: `workflow_run` with failed conclusion.
- CI provider: GitHub Actions for app-mode ingestion.
- Output: RCA summary comment plus generated artifact paths.
- Safety default: comment-only behavior (`create_fix_pr=false`).
- Optional guarded fix PR creation when both PR gates are explicitly enabled.
- Deterministic pipeline reuse as the analysis engine.
- Optional `agentic_assist` mode with local/Ollama or hosted providers.
- Async webhook acknowledgement for slower local model runs.

## Validated Live Behavior
- Failed PR-linked runs produce PR comments.
- Repeated deliveries update the existing app comment instead of spamming new comments.
- Low-signal `TEST`/`UNKNOWN` findings can be suppressed below the comment threshold.
- Local/Ollama suggestions can improve suggested-fix wording while deterministic scoring remains unchanged.
- Guarded fix PRs branch from the failing head, apply scoped changes, format Python changes, and remain human-reviewable.

## Out Of Scope
- Org-wide policy engine and centralized admin UI.
- Autonomous fix PR creation by default.
- Multi-provider app event ingestion (GitLab, Azure, CircleCI).
- Historical analytics dashboarding.
- Automatic merge or branch-protection bypass.
- CI rerun orchestration.

## Default Behavior
- Ignore non-failed workflow runs.
- Ignore unsupported events with structured logs.
- Return machine-readable reason codes for skipped/error/partial states.
- Never create fix PRs unless `enable_pr_mode=true` and `create_fix_pr=true`.
