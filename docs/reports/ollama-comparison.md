# Live Ollama Comparison

Live local-provider benchmark results for `agentic_assist` mode against the agentic subset of the MVP suite.

Command shape:

```bash
python scripts/run_ollama_comparison.py \
  --suite fixtures/benchmarks/mvp-suite.json \
  --llm-model <model> \
  --report-json artifacts/ollama-comparison/<model>.json
```

## Summary

| Model | Cases | Classification | Top-1 RCA | Proposal Validity | Validation Gate | Median TTD | P95 TTD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `qwen2.5-coder:3b` | 6 | 100% | 100% | 100% | 50% | 3.76s | 4.98s |
| `qwen2.5-coder:7b` | 6 | 100% | 100% | 100% | 50% | 6.19s | 6.58s |

## Recommendation

Use `qwen2.5-coder:3b` as the default local/Ollama model for app testing. It matched the `7b` model on classification, RCA accuracy, proposal validity, and guardrail behavior while running faster on this benchmark.

Use `qwen2.5-coder:7b` when local hardware can tolerate slower responses and you want a larger model for more complex repositories.

## Notes

- `Validation Gate` is expected to be `50%` in this suite because it contains three intentionally valid fixes and three intentionally invalid fixes.
- The live suite exercises lint, test, and typecheck agentic proposal scenarios.
- Generated JSON outputs are local benchmark artifacts and are not required in the repository.
