# CI Root Cause Analysis

TYPECHECK failure: src/app.ts(14,5): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'. at unknown file

## Classification
- TYPECHECK

## Primary Root Cause
- Title: src/app.ts(14,5): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'. at unknown file
- Confidence: 0.5400

## Evidence
- unknown (classification:typecheck)

## Ranked Alternatives
1. error Command failed with exit code 2. at unknown file (score: 0.2200)

## Suggested Fix
1. Update type annotations and value flow to satisfy static type checks.

## Metadata
- Commit: def123
- Run ID: bench_005
