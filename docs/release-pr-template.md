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
- [ ] Source GitHub Release created/updated for the same tag

## Smoke Validation
- [ ] `smoke-agentic-dry-run` passed
- [ ] Artifacts verified (`ci-rca.json`, `ci-rca.md`, `ci-rca-observability.json`)

## Product Signals For Announcement
- [ ] README top metrics still accurate:
  - [ ] classification accuracy
  - [ ] baseline lift
  - [ ] reproducibility stats
- [ ] One short demo clip/GIF prepared
- [ ] Announcement copy prepared (X/GitHub/Discord)

## Rollback Plan
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
- Release workflow (`prepare-release`) + source release: ✅
- Smoke workflow (`smoke-agentic-dry-run`): ✅

Top metrics (README):
- Classification accuracy: XX%
- Baseline lift: +YY pp
- Artifact reproducibility: ZZ%

Decision: **GO**
```
