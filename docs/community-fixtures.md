# Community Fixture Submission

Contribute sanitized CI failures to improve `ci-rootcause` coverage and precision.

## Submission Path

Use the GitHub issue template:

- [CI Failure Fixture Submission](https://github.com/ibrahim1023/ci-rootcause/issues/new?template=ci-failure-fixture.yml)

The template lives at:

- [`.github/ISSUE_TEMPLATE/ci-failure-fixture.yml`](/Users/ibrahim/Documents/Work/ci-rootcause/.github/ISSUE_TEMPLATE/ci-failure-fixture.yml)

## Required Inputs

1. CI provider
2. Expected classification
3. Expected primary root cause snippet
4. Sanitized CI log excerpt
5. Sanitized diff excerpt

## Privacy Rules

1. Remove all tokens, secrets, private URLs, usernames, and internal hostnames.
2. Replace proprietary file paths and identifiers with neutral placeholders.
3. Include only the minimal lines needed to reproduce classification and first-failure extraction.
4. Confirm the fixture can be shared publicly.

## Acceptance Criteria

A fixture is accepted when it:

1. Reproduces a real failure signature in deterministic tests.
2. Improves classification or root-cause extraction coverage.
3. Does not include sensitive information.
4. Includes expected classification and expected primary root-cause hints.

## Maintainer Flow

1. Copy sanitized log/diff into `fixtures/ci-logs` and `fixtures/diffs` when needed.
2. Add or update benchmark/classification cases.
3. Add regression tests for misclassified signatures.
4. Update leaderboard/report outputs if benchmark composition changes.
