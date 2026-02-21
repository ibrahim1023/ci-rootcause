# CI Root Cause Analysis

DEPENDENCY failure: E AssertionError: assert 3 == 4 at unknown file

## Classification
- DEPENDENCY

## Primary Root Cause
- Title: E AssertionError: assert 3 == 4 at unknown file
- Confidence: 0.6000

## Evidence
- unknown (classification:dependency)

## Ranked Alternatives
1. tests/test_math.py:12: AssertionError at unknown file (score: 0.3200)

## Suggested Fix
1. Align dependency references with lockfile and import expectations.

## Metadata
- Commit: abc123
- Run ID: bench_002
