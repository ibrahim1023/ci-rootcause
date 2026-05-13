# Benchmark Leaderboard

Leaderboard for the curated `ci-rootcause` benchmark suite.

## Deterministic (Default)

| Metric | Value |
| --- | ---: |
| Total cases | 17 |
| Classification accuracy | 100% |
| Baseline classification accuracy | 52.94% |
| Classification lift | +47.06 percentage points |
| Top-1 RCA accuracy | 100% |
| Primary RCA accuracy | 82.35% |
| False-fix blocked rate | 50% |
| Validation pass rate | 50% |
| Mean time to RCA | 61.75 ms |
| Artifact reproducibility | 100% |

## Local/Ollama Comparison

| Model | Cases | Classification | Top-1 RCA | Proposal Validity | False-fix Blocked | Median TTD | P95 TTD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `qwen2.5-coder:3b` | 6 | 100% | 100% | 100% | 50% | 3.76s | 4.98s |
| `qwen2.5-coder:7b` | 6 | 100% | 100% | 100% | 50% | 6.19s | 6.58s |

## Notes

- `False-fix blocked rate` is `1 - validation_pass_rate` on the agentic proposal subset with intentionally mixed valid/invalid fixes.
- Deterministic metrics source: [`mvp-benchmark-report.json`](/Users/ibrahim/Documents/Work/ci-rootcause/docs/reports/mvp-benchmark-report.json)
- Local/Ollama metrics source: [`ollama-comparison.md`](/Users/ibrahim/Documents/Work/ci-rootcause/docs/reports/ollama-comparison.md)
- Machine-readable leaderboard: [`benchmark-leaderboard.json`](/Users/ibrahim/Documents/Work/ci-rootcause/docs/reports/benchmark-leaderboard.json)
