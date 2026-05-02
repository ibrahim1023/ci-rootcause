# Eval Rubrics

Rubrics define how behavior is scored.

First-version rubrics should be deterministic:
- exact classification match,
- primary file/line match or allowed substring match,
- evidence references observed logs or diffs,
- comment includes likely cause, evidence, confidence, suggested fix, and app outcome,
- agentic proposal contains only allowed operations and repo-relative paths.
- compression preserves diagnosis-critical signals while dropping irrelevant repeated noise.
- contradictions are documented explicitly and resolved in favor of code/tests over docs.
- state continuity updates task/progress records after completed work and does not treat stale history as source of truth.

LLM-as-judge may be added later only with strict structured output and calibrated good/bad examples.
