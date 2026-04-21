# Progress

## Completed
- Added repository context harness files:
  - `AGENTS.md`
  - `scope.md`
  - `task.md`
  - `docs/decisions/0001-agent-context-harness.md`
- Completed baseline validation snapshot (`T0.2`):
  - `ruff check .` passed
  - `ruff format --check .` passed
  - `pytest` passed (`142 passed, 1 skipped`)
- Completed `T2.1` shared parser extraction:
  - Added shared parsing module: `src/core/input_parsing.py`.
  - Migrated `src/cli.py` and `src/action_entrypoint.py` to shared parsing utilities.
  - Added dedicated parser tests: `tests/unit/core/test_input_parsing.py`.
- Completed `T1.1` onboarding rewrite:
  - Added 60-second safe-mode GitHub Actions quickstart at top of `README.md`.
  - Added explicit expected action outputs and reference artifact links.

## Current Focus
- Continue Phase 1-2 precision and adoption:
  - `T1.2` differentiation section in README
  - `T2.2` deterministic output regression tests
  - `T2.3` expanded classification fixture precision coverage

## Known Issues / Risks
- CLI and action entrypoint currently duplicate parsing/config logic, creating drift risk.
- README value proposition and quickstart are not yet optimized for first-time conversion.
- Smoke workflow currently pins a static marketplace action tag, creating stale validation risk.

## Next Steps
1. Implement `T1.2` differentiation section and comparison table in README.
2. Implement `T2.2` deterministic hash regression tests for `ci-rca.json` and `ci-rca.md`.
3. Start `T2.3` by adding at least 10 new classification fixtures.
