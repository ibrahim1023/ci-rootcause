# AGENTS.md

## Purpose
Operational rules for contributors and agents working on `ci-rootcause`.

## Scope
Applies to all repository changes unless a task explicitly states otherwise.

## Source Of Truth Priority
1. Code implementation
2. Tests
3. `scope.md`
4. This file (`AGENTS.md`)
5. Other docs

If mismatch is found, do not guess. Document it in `progress.md` and resolve explicitly.

## Required Startup Sequence
1. Confirm repository root.
2. Read `task.md`.
3. Read `progress.md`.
4. Inspect recent git history (`git log --oneline -n 10`).
5. Run baseline validation.

## Retrieval And Context Rules
- Search the codebase and tests before making non-trivial changes.
- Prefer targeted reads over loading large files wholesale.
- Do not rely on docs alone when code or tests disagree.

## Output Compression
- Compress noisy command output before reusing it as agent context when the raw output is large or repetitive.
- Prioritize preserving errors, exit codes, file paths, line numbers, failing assertions, and other deterministic diagnosis signals.
- Do not compress small targeted outputs unnecessarily.
- Expand raw output only when debugging requires exact detail.
- Prefer `ztk` when available for large diffs, recursive listings, test logs, build logs, typecheck output, lint output, CI logs, stack traces, and package manager output.

## Required Validation Commands
- Lint: `ruff check .`
- Format check: `ruff format --check .`
- Tests: `pytest`

Run validation after each scoped task.

## Change Discipline
- Make minimal, task-scoped edits.
- Do not refactor unrelated modules.
- Keep behavior deterministic unless task explicitly changes policy.
- Never bypass PR safety guardrails.

## Definition Of Done
A task is complete only when:
- acceptance criteria in `task.md` are met,
- validation commands pass,
- `task.md` and `progress.md` are updated to reflect reality.

## Commit Discipline
- One commit per completed task where practical.
- Use clear commit messages tied to task IDs.
- Do not continue on a broken baseline.
