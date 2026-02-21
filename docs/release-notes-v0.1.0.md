# Release Notes: v0.1.0 (MVP)

Date: 2026-02-21

## Highlights

- Deterministic first-failure extraction and failure graph output.
- Diff-aware root cause ranking with computed confidence.
- Guardrailed fix planning and optional guarded PR creation flow.
- Stable machine-readable and markdown RCA artifacts.
- ADK runtime orchestration path with deterministic local fallback.
- Structured trace logs and per-agent/pipeline timing metrics.
- Curated benchmark suite with measured MVP metrics.

## Measured MVP Metrics

See:

- `docs/reports/mvp-benchmark-report.json`
- `docs/reports/mvp-benchmark-report.md`

Current measured summary:

- `primary_root_cause_accuracy`: `1.0000`
- `confidence_reproducibility`: `1.0000`
- `mean_time_to_diagnosis_ms`: `0.389`

## Notes

- Timing metrics are runtime-dependent and intentionally treated as nondeterministic metadata.
- Guardrails enforce no auto-merge and no branch-protection bypass.
