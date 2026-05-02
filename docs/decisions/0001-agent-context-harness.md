# ADR-0001: Repository Context Harness

## Status
Accepted

## Date
2026-04-21

## Context
The repository lacked persistent execution context files, causing inconsistent session startup, weak continuity, and reduced task precision.

## Decision
Adopt a lightweight harness with required repository context records plus the `docs/decisions/` ADR log.

## Consequences
### Positive
- Consistent startup/validation loops.
- Better traceability of decisions and progress.
- Higher precision for multi-session execution.

### Negative
- Small maintenance overhead for keeping execution-state records current.

## Follow-ups
- Keep execution planning tied to measurable acceptance criteria.
- Update execution-state records after each completed milestone.
