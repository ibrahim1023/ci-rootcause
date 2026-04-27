# Release Readiness Checklist (Paste Into PR/Issue)

## Release
- [ ] Target version/tag: `vX.Y.Z`
- [ ] Scope summary written (what changed and why)
- [ ] Breaking changes section (or `None`)

## Quality Gates
- [ ] Local validation passed:
  - `ruff check .`
  - `ruff format --check .`
  - `pytest`
- [ ] CI `lint-and-test` passed
- [ ] CI `packaging-smoke` passed (includes agentic CLI parity checks)
- [ ] Release gate policy passed (`src.release_gate`)

## Release Workflows
- [ ] `prepare-release` completed and created new tag
- [ ] `publish-wrapper` completed for the same tag
- [ ] Wrapper repo updated:
  - [ ] `main` synced
  - [ ] tag `vX.Y.Z` exists
  - [ ] major alias `v0` points to same commit as `vX.Y.Z`
  - [ ] wrapper release exists/updated

## Smoke Validation
- [ ] `smoke-agentic-dry-run` passed
- [ ] `smoke-marketplace` passed
- [ ] Artifacts verified (`ci-rca.json`, `ci-rca.md`, `ci-rca-observability.json`)

## Product Signals For Announcement
- [ ] README top metrics still accurate:
  - [ ] classification accuracy
  - [ ] baseline lift
  - [ ] reproducibility stats
- [ ] One short demo clip/GIF prepared
- [ ] Announcement copy prepared (X/GitHub/Discord)

## Rollback Plan
- [ ] If wrapper publish fails: rerun `publish-wrapper` with explicit tag input
- [ ] If release gate fails: do not retag; fix thresholds/regression first
- [ ] If smoke fails: hold announcement, patch, and rerun workflows

## Ready-To-Ship Decision
- [ ] GO
- [ ] NO-GO (reason):

---

## Short Release Comment Template

```md
Release `vX.Y.Z` readiness update:

- Local checks: ✅
- CI (`lint-and-test`, `packaging-smoke`): ✅
- Release workflows (`prepare-release`, `publish-wrapper`): ✅
- Wrapper sync (`vX.Y.Z` + `v0`): ✅
- Smoke workflows (`smoke-agentic-dry-run`, `smoke-marketplace`): ✅

Top metrics (README):
- Classification accuracy: XX%
- Baseline lift: +YY pp
- Artifact reproducibility: ZZ%

Decision: **GO**
```
