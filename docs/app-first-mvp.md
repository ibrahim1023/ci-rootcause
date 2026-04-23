# App-First MVP Scope

## Objective
Enable a no-YAML onboarding path where users install a GitHub App and automatically receive RCA on failed CI runs.

## In Scope (MVP)
- Event: `workflow_run` with failed conclusion.
- Provider: GitHub Actions only for app mode MVP.
- Output: RCA summary comment plus links to generated artifacts.
- Safety default: comment-only behavior (`create_fix_pr=false`).
- Deterministic pipeline reuse (`run_pipeline`) as the analysis engine.

## Out Of Scope (MVP)
- Org-wide policy engine and centralized admin UI.
- Broad autonomous fix PR creation by default.
- Multi-provider app event ingestion (GitLab, Azure, CircleCI).
- Historical analytics dashboarding.
- Agentic full autonomy as default.

## Default Behavior
- Ignore non-failed workflow runs.
- Ignore unsupported events with structured logs.
- Return machine-readable reason codes for skipped/error states.
