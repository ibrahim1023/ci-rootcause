# CI Root Cause Analysis

TEST failure: E AssertionError: assert 3 == 4 at unknown file

## Classification
- TEST

## Primary Root Cause
- Title: E AssertionError: assert 3 == 4 at unknown file
- Confidence: 0.5400

## Evidence
- unknown (classification:test)

## Ranked Alternatives
1. tests/test_math.py:12: AssertionError at unknown file (score: 0.2600)

## Suggested Fix
1. Adjust implementation or assertion so observed behavior matches expected test contract.

## Metadata
- Commit: abc123
- Run ID: bench_003
