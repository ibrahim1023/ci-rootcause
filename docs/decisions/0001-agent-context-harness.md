# ADR-0001: Repository Context Harness

## Status
Accepted

## Date
2026-04-21

## Context
The repository lacked persistent execution context files, causing inconsistent session startup, weak continuity, and reduced task precision.

## Decision
Adopt a lightweight harness with required files:
- `AGENTS.md`
- `scope.md`
- `task.md`
- `progress.md`
- `docs/decisions/` ADR log

## Consequences
### Positive
- Consistent startup/validation loops.
- Better traceability of decisions and progress.
- Higher precision for multi-session execution.

### Negative
- Small maintenance overhead for updating task/progress state.

## Follow-ups
- Keep `task.md` tied to measurable acceptance criteria.
- Update `progress.md` after each completed milestone.
