# Release Checklist v0.1.1

Date: 2026-02-23

## Scope

- GitHub PR creation hardening (`push` before PR API create)
- GitHub API retry/backoff with typed rate-limit/transient errors
- Contract schema compatibility matrix tests
- Expanded GitHub Actions log fixture coverage
- Observability artifact export (`ci-rca-observability.json`)
- Safe rollout profile (`safe-github-rollout`)

## Pre-Release Validation

- [x] `ruff check .`
- [x] `pytest`
- [x] Benchmark report regenerated (`docs/reports/mvp-benchmark-report.json`, `.md`)
- [x] Action input contract updated (`rollout_profile`)
- [x] README and scope docs updated for new behavior

## GitHub Rollout Guidance

- Start with `create_fix_pr=false`
- Set `rollout_profile=safe-github-rollout`
- Enable `create_fix_pr=true` only after dry-run confidence review
- Keep `offline_only=true` for initial shadow runs if desired

## Live Validation (Optional)

- Run `tests/integration/test_pr_creation_live_github.py` against a disposable repository
- Verify:
  - first run creates PR
  - second run reuses the same PR (idempotency)
