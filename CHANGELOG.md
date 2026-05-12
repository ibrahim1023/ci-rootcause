# Changelog

All notable user-facing changes to `ci-rootcause` are tracked here.

## [v0.2.0] - 2026-05-12

Release: https://github.com/ibrahim1023/ci-rootcause/releases/tag/v0.2.0

### Added

- GitHub App-first workflow for failed GitHub Actions `workflow_run` events.
- GitHub App webhook verification, event routing, and installation-token authentication.
- GitHub Actions log and diff ingestion for app-mode analysis.
- Idempotent RCA comments on PRs and commits.
- Repository allow/deny controls for app processing.
- App outcome taxonomy with stable `ok`, `partial`, `skipped`, and `error` states.
- Machine-readable reason codes for webhook, ingestion, comment, artifact, and PR-gate outcomes.
- Optional guarded fix PR creation for app mode.
- Explicit PR creation gates: app opt-in, confidence threshold, scoped file changes, validation commands, and max-file limits.
- Agentic execution modes: `deterministic`, `agentic_assist`, and `agentic_full` with explicit full-mode opt-in.
- Local/Ollama-compatible provider support.
- Hosted provider adapter support for OpenAI, Gemini, and Anthropic.
- Agentic proposal contract validation, bounded retries, and contract-repair context.
- Agentic validation gate before fix PR creation.
- Agentic failure taxonomy for missing keys, provider errors, validation failures, and max retry exhaustion.
- Async webhook acknowledgement for slow local LLM/Ollama runs.
- Local GitHub App server support for ngrok-based testing.
- App failure fixture workflow for end-to-end app testing.
- Curated MVP benchmark suite covering `TYPECHECK`, `LINT`, `TEST`, `DEPENDENCY`, and `INFRA` failures.
- Agentic benchmark coverage for lint, test, and typecheck fix proposals.
- Ollama comparison report for `qwen2.5-coder:3b` and `qwen2.5-coder:7b`.
- Evaluation harness coverage for behavior quality, contradiction handling, state continuity, and context compression.
- Release gates based on benchmark metrics and compatibility fixtures.

### Changed

- Repositioned the project around app-first CI root-cause analysis instead of action-first usage.
- README now leads with metrics, tested coverage, app-first quickstart, agentic modes, and evaluation strategy.
- GitHub Action mode remains supported as an optional/migration path.
- Root-cause ranking now better prioritizes actionable first-failure log signals.
- Confidence reporting is more explainable and remains deterministic.
- Parser behavior now extracts more actionable file/line CI failure locations.
- PR guardrails are stricter about evidence-backed paths and unsafe file operations.
- App comments suppress low-signal `TEST`/`UNKNOWN` findings below the configured threshold.
- App-created Python fix commits are formatted before PR creation.
- App fix PRs branch from the failing head and prefer diff-backed synthesis over stale worktree files.
- Release workflow now creates source repo releases directly.

### Fixed

- Case-insensitive GitHub webhook header lookup.
- GitHub App token API authentication scheme issues.
- Missing-base-SHA workflow runs now skip instead of failing hard.
- Hosted provider missing-key errors are surfaced as typed app outcomes.
- Validation commands can be configured through app environment variables.
- Agentic typecheck fixes avoid being suppressed by low-signal comment filtering.
- Agentic PR generation prefers patch-plan changes and diff-backed typecheck synthesis.
- `CI_ROOTCAUSE_APP_MAX_FIX_FILES` is now read from the app environment.

### Metrics

- Curated benchmark classification accuracy: `100%` (`13/13`).
- Top-1 root-cause accuracy: `100%` (`12/12` applicable cases).
- Agentic proposal validity: `100%` (`6/6` exercised cases).
- Guarded validation gate: `50%` (`3/6`, with three intentionally bad fixes blocked).
- Artifact hash reproducibility: `100%`.
- Confidence reproducibility: `100%`.
- Local test suite at release time: `299 passed`, `1 skipped`.

## [v0.1.5] - Previous Release

### Notes

- Last `v0.1.x` release before the app-first and agentic release line.
- Kept here as the comparison baseline for `v0.2.0`.

## [v0.1.0] - MVP

### Added

- Deterministic first-failure extraction and failure graph output.
- Diff-aware root-cause ranking with computed confidence.
- Guardrailed fix planning and optional PR creation flow.
- Stable machine-readable and Markdown RCA artifacts.
- Google ADK runtime orchestration path with deterministic local fallback.
- Structured trace logs and per-agent/pipeline timing metrics.
- Curated benchmark suite with measured MVP metrics.

[v0.2.0]: https://github.com/ibrahim1023/ci-rootcause/releases/tag/v0.2.0
[v0.1.5]: https://github.com/ibrahim1023/ci-rootcause/releases/tag/v0.1.5
[v0.1.0]: https://github.com/ibrahim1023/ci-rootcause/releases/tag/v0.1.0
