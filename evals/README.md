# ci-rootcause Evaluation Harness

## Purpose
Evaluation checks whether `ci-rootcause` behavior is useful, grounded, and reliable across known CI failure scenarios.

Validation answers: does the code run?
Evaluation answers: does the product diagnose failures correctly and safely?

## Target Behavior
- Identify the correct failure class for common CI failures.
- Rank the most likely root cause at the top.
- Ground evidence in observed logs, diffs, and GitHub App event context.
- Produce comments that are actionable in PR review.
- Keep auto-fix PR creation guarded by confidence, scope, and validation.
- Keep agentic/Ollama proposals schema-valid and evidence-scoped.
- Document contradictions explicitly when docs disagree with code or tests.
- Keep `task.md` and `progress.md` aligned with completed work, and reject stale history when code/tests disagree.

## Failure Definition
An eval case fails when any required expectation is missed:
- wrong classification,
- wrong or missing primary root-cause file/line,
- unsupported or ungrounded claim,
- malformed app comment,
- invalid agentic proposal schema,
- proposed fix outside allowed evidence scope,
- missing or unclear guardrail failure reason.

## Scoring Method
Use deterministic binary checks for gating:
- classification match,
- top-1 root-cause match,
- evidence-grounding pass,
- comment-actionability pass,
- agentic proposal schema pass,
- guardrail explanation pass.

Scalar scores may be recorded for analysis, but pass/fail gates should remain binary.

## Pass/Fail Thresholds
Initial local thresholds:
- classification accuracy: >= 0.90
- top-1 root-cause accuracy: >= 0.80
- evidence-grounding pass rate: >= 0.90
- comment-actionability pass rate: >= 0.80
- agentic proposal schema pass rate: >= 0.80

Thresholds should rise as the dataset grows.

## Directory Layout
- `datasets/`: eval cases and expected behavior.
- `rubrics/`: deterministic and optional judge rubrics.
- `results/`: generated eval outputs; keep only intentional snapshots.

## Running Evals
Run the current RCA quality suite:

```bash
python scripts/run_evals.py
```

The command writes the latest summary to `evals/results/rca-quality.latest.json`.

Run the harness compression suite:

```bash
python scripts/run_evals.py \
  --dataset evals/datasets/harness-quality.json \
  --output evals/results/harness-quality.latest.json
```

The command writes the latest summary to `evals/results/harness-quality.latest.json`.

## Operating Rules
- Every real behavior failure becomes an eval case.
- Prefer small high-signal datasets over broad noisy data.
- Store expected behavior, not only expected raw output text.
- Keep validation tests and behavior evals separate.
- Do not use LLM-as-judge until deterministic checks are insufficient.
- Add dedicated suites when harness behavior and product behavior need different metrics.
