# Task Plan

## Objective
Increase `ci-rootcause` adoption and trust by improving onboarding clarity, output precision, safety guarantees, and measurable reliability.

## Phase 0: Baseline And Harness

- [x] T0.1 Create repository context harness files.
  - Acceptance criteria:
    - `AGENTS.md`, `scope.md`, `task.md`, `progress.md` exist.
    - `docs/decisions/0001-agent-context-harness.md` exists.

- [x] T0.2 Establish baseline quality snapshot.
  - Acceptance criteria:
    - Run `ruff check .`, `ruff format --check .`, `pytest`.
    - Record pass/fail and notable failures in `progress.md`.

## Phase 1: Product Positioning And Onboarding (Attention)

- [x] T1.1 Rewrite top of `README.md` for 60-second adoption.
  - Acceptance criteria:
    - First screen includes one minimal GitHub Action snippet.
    - Includes safe default mode (`create_fix_pr: false`).
    - Includes explicit expected outputs and one screenshot/reference artifact.

- [ ] T1.2 Add differentiation section: "When to use ci-rootcause".
  - Acceptance criteria:
    - Defines 3-5 ideal use cases.
    - Defines 2-3 non-goals to prevent misuse.
    - Includes concise comparison table against formatter-only autofix flows.

- [ ] T1.3 Add social proof and release trust signals.
  - Acceptance criteria:
    - Badges for CI status, latest release, and test suite status.
    - Link to benchmark report and limitations near top-level README sections.

## Phase 2: Precision And Determinism

- [x] T2.1 Remove duplicated config/input parsing between CLI and action entrypoint.
  - Acceptance criteria:
    - Shared module for parsing booleans, thresholds, config files, and payload loaders.
    - Existing tests pass and at least 4 new tests cover shared parser paths.

- [ ] T2.2 Add deterministic output regression tests.
  - Acceptance criteria:
    - Add integration test asserting stable hash for `ci-rca.json` on fixed fixtures.
    - Add integration test asserting stable hash for `ci-rca.md` on fixed fixtures.

- [ ] T2.3 Strengthen classification precision coverage.
  - Acceptance criteria:
    - Expand classification fixture corpus with at least 10 new cases.
    - Add confusion-matrix-like summary in benchmark output artifact.

## Phase 3: Safety And PR Guardrails

- [ ] T3.1 Standardize PR skip/failure reason taxonomy.
  - Acceptance criteria:
    - Enumerated machine-readable reason codes for skip/fail states.
    - Action outputs include reason code + human-readable message.
    - Unit tests validate reason code stability.

- [ ] T3.2 Harden validated change boundaries.
  - Acceptance criteria:
    - Reject ambiguous path variants consistently in all entry paths.
    - Add tests for traversal, absolute path, and empty/invalid path edge cases.

## Phase 4: CI/Release Reliability

- [ ] T4.1 Add packaging/install smoke test in CI.
  - Acceptance criteria:
    - CI job executes `pip install .`.
    - CI job runs `ci-rootcause --help` and one fixture CLI run.

- [ ] T4.2 Upgrade publish-wrapper validation to tag-aware checks.
  - Acceptance criteria:
    - Smoke workflow validates the intended release tag, not stale hardcoded tag.
    - Fails fast if wrapper tag and source tag mismatch.

- [ ] T4.3 Add release quality gate checklist automation.
  - Acceptance criteria:
    - Release workflow checks benchmark artifact presence and contract compatibility tests.

## Phase 5: Growth Loop Enablement

- [ ] T5.1 Create reproducible demo pack for sharing.
  - Acceptance criteria:
    - Add `fixtures/demos/` with at least 3 narrative cases (input logs/diffs + expected output).
    - Add "demo script" section to README with exact commands.

- [ ] T5.2 Add issue templates for fixture contributions.
  - Acceptance criteria:
    - New issue template for "CI failure fixture submission".
    - Template requests logs, diff, expected classification, and privacy scrub confirmation.

## Sequencing
1. Finish Phase 0 before implementation work.
2. Execute Phases 1 and 2 in parallel where possible.
3. Phase 3 before enabling broader auto-PR workflows.
4. Phase 4 before broader release promotion.
5. Phase 5 to sustain external attention.
