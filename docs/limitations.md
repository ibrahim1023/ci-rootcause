# Known Limitations And Non-Goals

Date: 2026-02-21

## Limitations

- Benchmark coverage is curated and limited to current fixture scenarios.
- Failure classification is deterministic-pattern based and may miss unseen signatures.
- Confidence reproducibility is deterministic for identical inputs; timing metrics are intentionally marked nondeterministic.
- Fix planning remains evidence-constrained and minimal; it does not guarantee a complete code fix.
- ADK runtime fallback to local deterministic orchestration is supported, but not all ADK runtime edge cases are exhaustively benchmarked.

## Non-Goals (MVP)

- Automatic PR merge.
- Branch protection bypass.
- Automatic CI rerun orchestration.
- Full static analysis replacement for repository-specific tooling.
- Universal multi-provider CI support beyond current GitHub Actions target.
