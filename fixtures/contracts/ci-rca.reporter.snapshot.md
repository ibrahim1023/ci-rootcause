# CI Root Cause Analysis

Type error in changed module

## Classification
- TYPECHECK

## Primary Root Cause
- Title: Invalid return type in src/core/math.py
- Confidence: 0.8200

## Evidence
- src/core/math.py:42 (mypy)

## Ranked Alternatives
1. Outdated lockfile (score: 0.2900)

## Suggested Fix
1. Update return type annotation in src/core/math.py

## Metadata
- Commit: abc123
- Run ID: gha_001
