# GitHub App Complex Testing Plan

## Goal
Validate `ci-rootcause` GitHub App behavior under realistic and failure-heavy conditions before broader rollout.

## Scope
- In scope: webhook validation, installation token flow, ingestion, pipeline execution, comment publishing, reason-code behavior, guardrails, and operational resilience.
- Out of scope: product marketing, billing analytics, unrelated CI workflows.

## Environments
- Local app server + ngrok for interactive debugging.
- GitHub test repository installation for end-to-end validation.
- Optional staging deployment for soak/reliability tests.

## Preconditions
- GitHub App created and installed on test repositories.
- Webhook URL points to active endpoint.
- Env configured:
  - `GITHUB_APP_ID`
  - `GITHUB_APP_PRIVATE_KEY_PEM`
  - `GITHUB_WEBHOOK_SECRET`
- Default safe config:
  - `CI_ROOTCAUSE_APP_ENABLE_PR_MODE=false`
  - `CI_ROOTCAUSE_APP_CREATE_FIX_PR=false`
  - `CI_ROOTCAUSE_APP_MODE=deterministic`

## Test Phases

### Phase 1: Webhook Contract Validation

#### T1.1 Signature Handling
- Valid signature should process.
- Missing signature should fail with webhook validation failure.
- Invalid signature should fail with webhook validation failure.

Expected:
- HTTP status and reason code align with `docs/app-outcome-codes.md`.

#### T1.2 Event Type Handling
- `workflow_run` handled.
- Unsupported event ignored with `UNSUPPORTED_EVENT`.

Expected:
- Ignored events return `skipped` and do not run pipeline.

#### T1.3 Payload Validation
- Missing repository/workflow fields.
- Invalid `workflow_run.id` / `run_attempt`.

Expected:
- Deterministic error codes (`MISSING_*`, `INVALID_*`).

### Phase 2: Auth And Installation Token Flow

#### T2.1 Installation Context
- Valid `installation.id` should mint token and proceed.
- Missing/invalid `installation.id` should return app auth error.

#### T2.2 App Credential Errors
- Wrong App ID.
- Wrong private key.
- Expired/invalid JWT.

Expected:
- Typed auth/token failures (no silent success, no panic).

### Phase 3: End-to-End Runtime Scenarios (Real GitHub)

#### T3.1 PR-Linked Failed Run
- Trigger failing workflow on PR branch.

Expected:
- App posts/updates PR comment.
- `classification`, `confidence`, root cause summary present.

#### T3.2 Non-PR Failed Run
- Trigger failure on branch without PR.

Expected:
- App falls back to commit comment path.

#### T3.3 Failure Class Coverage
- Dependency failure fixture.
- Infra timeout failure fixture.
- Typecheck failure fixture.

Expected:
- Correct classification and stable artifacts/reason codes.

### Phase 4: Guardrails And Safety

#### T4.1 Repository Policy Controls
- Disabled repo.
- Denylisted repo.
- Allowlist-only mode with non-allowlisted repo.

Expected:
- `REPOSITORY_DISABLED`, `REPOSITORY_DENYLISTED`, `REPOSITORY_NOT_ALLOWLISTED`.

#### T4.2 PR Safety Defaults
- Confirm safe defaults never create PRs unless explicit opt-in flags are enabled.

Expected:
- `pr_created=false` in default profile.

#### T4.3 Agentic Guardrails
- Agentic hosted provider without API key.
- Validation command failure in PR path.

Expected:
- Missing key / validation failure reason codes surfaced.

### Phase 5: Reliability And Resilience

#### T5.1 Duplicate Delivery Replay
- Replay same webhook payload 3 times.

Expected:
- Idempotent comment update behavior (no comment spam).

#### T5.2 Transient API Failure
- Inject temporary GitHub API errors.

Expected:
- Retries are bounded; final code is deterministic on failure.

#### T5.3 Rate Limit Simulation
- Force/approximate API rate limit responses.

Expected:
- Retry/backoff behavior; clear failure reason code if exhausted.

### Phase 6: Load And Soak

#### T6.1 Burst Test
- 20-50 webhook deliveries over 1-2 minutes.

Expected:
- Stable process, no crash loop, acceptable latency.

#### T6.2 Short Soak
- Continuous deliveries over 15-30 minutes.

Expected:
- No memory/handle leaks, consistent reason-code distribution.

### Phase 7: Operations Readiness

#### T7.1 Secret Rotation Drill
- Rotate webhook secret and app private key.

Expected:
- Controlled recovery with minimal disruption.

#### T7.2 Restart Recovery
- Restart service during incoming events.

Expected:
- Service recovers; failures are visible and bounded.

#### T7.3 Observability Check
- Aggregate logs by `status`, `reason_code`, repository, workflow id.

Expected:
- Clear error budget visibility for go/no-go decisions.

## Pass Criteria
- No critical auth/webhook contract failures.
- End-to-end PR and commit comment flows work.
- Guardrails hold under negative tests.
- Retry/idempotency behavior is bounded and deterministic.
- Release thresholds remain green.

## Exit Criteria
- All Phase 1-4 scenarios pass.
- Phase 5-7 have no unresolved critical defects.
- Documented known issues have workarounds and owners.

## Execution Checklist
- [ ] Run Phase 1-2 locally with ngrok.
- [ ] Run Phase 3 against test repo.
- [ ] Run Phase 4 negative/safety cases.
- [ ] Run Phase 5 reliability tests.
- [ ] Run Phase 6 load/soak sample.
- [ ] Run Phase 7 operational drills.
- [ ] Produce test report with failures and action items.

## Quick Trigger Workflow

Use `.github/workflows/app-failure-fixtures.yml` to generate controlled failed `workflow_run`
events from the Actions UI (`workflow_dispatch`).

Scenarios:
- `typecheck`
- `syntax`
- `dependency`
- `infra`
