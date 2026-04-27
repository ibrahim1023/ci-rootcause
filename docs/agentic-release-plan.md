# Agentic Release Plan And Go/No-Go Gates

This plan defines how agentic capability is released safely in stages.

## Stage Plan

| Stage | Policy | Scope | Notes |
| --- | --- | --- | --- |
| 1 | `stage=1`, `agentic_enabled=false` | Deterministic-only release baseline | Ship scaffolding safely with no agentic exposure. |
| 2 | `stage=2`, `agentic_enabled=true` | `agentic_assist` rollout limited to `TYPECHECK` | Opt-in only; deterministic fallback remains active. |
| 3 | `stage=3`, `agentic_enabled=true` | Broader class rollout after thresholds pass | Expand only after benchmark and validation gates remain healthy. |

Policy source of truth:
- `config/agentic-release-policy.json`

## Go/No-Go Thresholds

Release gate enforces these thresholds against `docs/reports/mvp-benchmark-report.json`:

- `classification_match_rate >= 0.95`
- `artifact_hash_reproducibility >= 1.0`
- `confidence_reproducibility >= 1.0`
- `completion_rate >= 1.0`
- For `agentic_enabled=true`: `agentic_validation_pass_rate >= 1.0`

Validation pass rate is modeled as a required precondition that CI release validation already passed.

## Enforcement

Gate command:

```bash
python -m src.release_gate \
  --benchmark docs/reports/mvp-benchmark-report.json \
  --policy config/agentic-release-policy.json \
  --validation-passed
```

Enforced in:
- `.github/workflows/prepare-release.yml`
- `.github/workflows/publish-wrapper.yml`
