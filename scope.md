# Scope

## System Purpose
`ci-rootcause` is a deterministic CI failure analysis engine that:
- parses CI logs and diffs,
- classifies failure type,
- ranks root causes with confidence,
- produces evidence-backed fix plans,
- optionally creates a guarded fix PR.

## Primary Users
- Repository maintainers debugging failed CI runs.
- Teams wanting safe automation for triage and limited fix PR creation.

## Architecture Intent
- Deterministic agent pipeline with fixed execution order.
- Contract-first outputs (`ci-rca.json`, `ci-rca.md`, observability artifact).
- Strong guardrails for PR creation (confidence threshold, allowed files, validated changes).
- Runtime portability with local deterministic orchestration and optional ADK runtime path.

## Constraints
- Determinism and reproducibility are first-class requirements.
- No auto-merge behavior.
- PR changes must remain within evidence-backed scope.
- Action/CLI interfaces must remain stable and testable.

## Non-Goals
- Fully autonomous large-scale refactoring.
- Broad speculative code generation without evidence.
- Replacing repository-specific test/lint tooling.

## Quality Bar
- High-signal RCA artifacts with traceable evidence.
- Safe-by-default rollout behavior.
- Clear failure reasons when PR creation is blocked.
