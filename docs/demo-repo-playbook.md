# Public Demo Repository Playbook

Use this playbook to publish a public demo repository for `ci-rootcause` with controlled failures and reproducible RCA outputs.

## Target

Create a public repository (for example `ci-rootcause-demo`) with at least these controlled failures:

1. `dependency-lockfile-drift`
2. `typecheck-ts2345`
3. `infra-timeout`

Optional extras:

4. `node-install-eresolve`
5. `go-test-fail`

The first three are already packaged in [`fixtures/demos`](/Users/ibrahim/Documents/Work/ci-rootcause/fixtures/demos).

## Required Artifacts Per Demo

For each scenario, publish:

1. `ci.log`
2. `change.diff`
3. `expected-ci-rca.json`
4. `expected-ci-rca.md`
5. A screenshot or link to the GitHub App RCA comment (before)
6. Optional link to app-created fix PR (after)

## Suggested Demo Repository Structure

```text
ci-rootcause-demo/
  scenarios/
    01-dependency-lockfile-drift/
    02-typecheck-ts2345/
    03-infra-timeout/
  README.md
```

## Validation Flow

1. Trigger each failing workflow.
2. Confirm GitHub App posts or updates RCA comment.
3. Capture comment link as the "before" artifact.
4. If `create_fix_pr=true`, capture the generated fix PR link as optional "after" artifact.
5. Confirm generated RCA text matches `expected-ci-rca.md` within normal timestamp/path variance.

## Copy-Ready Links

- Scenario pack: [`fixtures/demos/README.md`](/Users/ibrahim/Documents/Work/ci-rootcause/fixtures/demos/README.md)
- Dependency demo: [`fixtures/demos/01-dependency-lockfile-drift`](/Users/ibrahim/Documents/Work/ci-rootcause/fixtures/demos/01-dependency-lockfile-drift)
- Typecheck demo: [`fixtures/demos/02-typecheck-ts2345`](/Users/ibrahim/Documents/Work/ci-rootcause/fixtures/demos/02-typecheck-ts2345)
- Infra demo: [`fixtures/demos/03-infra-timeout`](/Users/ibrahim/Documents/Work/ci-rootcause/fixtures/demos/03-infra-timeout)

## Non-Goals

- No automatic merge in demo flows.
- No private repository logs or secrets in published artifacts.
