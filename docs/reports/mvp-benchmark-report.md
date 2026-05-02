# MVP Benchmark Report

- Suite: mvp-curated-v3
- Total cases: 13
- Completed cases: 13
- Completion rate: 1.0000
- Classification matches: 13
- Classification match rate: 1.0000
- Baseline classification matches: 9
- Baseline classification match rate: 0.6923
- Classification match lift vs baseline: 0.3077
- Primary root-cause matches: 13
- Primary root-cause accuracy: 1.0000
- Top-1 root-cause cases: 12
- Top-1 root-cause matches: 12
- Top-1 root-cause accuracy: 1.0000
- Agentic proposal valid rate: 1.0000
- Agentic proposal valid cases: 6
- Validation pass rate: 0.5000
- Validation pass cases: 6
- Confidence reproducibility: 1.0000
- Artifact hash reproducibility: 1.0000
- Mean time-to-diagnosis (ms): 61.7500
- Median time-to-diagnosis (ms): 0.5960
- P95 time-to-diagnosis (ms): 341.8690

## Case Results

- Case: case-agentic-ruff-fail
  - Classification: LINT (expected: LINT)
  - Primary root cause: src/app.py:7:5: F401 `os` imported but unused at src/app.py:7
  - Top-1 file/line: src/app.py:7
  - Confidence values: [0.54, 0.54]
  - Pipeline timing ms: 12.074

- Case: case-agentic-ruff-pass
  - Classification: LINT (expected: LINT)
  - Primary root cause: src/app.py:7:5: F401 `os` imported but unused at src/app.py:7
  - Top-1 file/line: src/app.py:7
  - Confidence values: [0.54, 0.54]
  - Pipeline timing ms: 11.522

- Case: case-agentic-test-fail
  - Classification: TEST (expected: TEST)
  - Primary root cause: E AssertionError: assert 3 == 4 at tests/test_math.py:12
  - Top-1 file/line: tests/test_math.py:12
  - Confidence values: [0.62, 0.62]
  - Pipeline timing ms: 394.596

- Case: case-agentic-test-pass
  - Classification: TEST (expected: TEST)
  - Primary root cause: E AssertionError: assert 3 == 4 at tests/test_math.py:12
  - Top-1 file/line: tests/test_math.py:12
  - Confidence values: [0.62, 0.62]
  - Pipeline timing ms: 341.869

- Case: case-agentic-typecheck-fail
  - Classification: TYPECHECK (expected: TYPECHECK)
  - Primary root cause: src/app_failure_typecheck.py:4: error: Argument 1 to "needs_int" has incompatible type "str"; expected "int" [arg-type] at src/app_failure_typecheck.py:4
  - Top-1 file/line: src/app_failure_typecheck.py:4
  - Confidence values: [0.9, 0.9]
  - Pipeline timing ms: 19.986

- Case: case-agentic-typecheck-pass
  - Classification: TYPECHECK (expected: TYPECHECK)
  - Primary root cause: src/app_failure_typecheck.py:4: error: Argument 1 to "needs_int" has incompatible type "str"; expected "int" [arg-type] at src/app_failure_typecheck.py:4
  - Top-1 file/line: src/app_failure_typecheck.py:4
  - Confidence values: [0.9, 0.9]
  - Pipeline timing ms: 19.496

- Case: case-infra-timeout
  - Classification: INFRA (expected: INFRA)
  - Primary root cause: ERROR: connection reset by peer while contacting package mirror at unknown file
  - Top-1 file/line: n/a
  - Confidence values: [0.4225, 0.4225]
  - Pipeline timing ms: 0.44

- Case: case-node-mixed-lock
  - Classification: DEPENDENCY (expected: DEPENDENCY)
  - Primary root cause: E AssertionError: assert 3 == 4 at tests/test_math.py:12
  - Top-1 file/line: tests/test_math.py:12
  - Confidence values: [0.64, 0.64]
  - Pipeline timing ms: 0.596

- Case: case-python-lock-only
  - Classification: DEPENDENCY (expected: DEPENDENCY)
  - Primary root cause: E AssertionError: assert 3 == 4 at tests/test_math.py:12
  - Top-1 file/line: tests/test_math.py:12
  - Confidence values: [0.64, 0.64]
  - Pipeline timing ms: 0.474

- Case: case-refactor-only
  - Classification: TEST (expected: TEST)
  - Primary root cause: E AssertionError: assert 3 == 4 at tests/test_math.py:12
  - Top-1 file/line: tests/test_math.py:12
  - Confidence values: [0.62, 0.62]
  - Pipeline timing ms: 0.476

- Case: case-rename-and-modify
  - Classification: TEST (expected: TEST)
  - Primary root cause: E AssertionError: assert 3 == 4 at tests/test_math.py:12
  - Top-1 file/line: tests/test_math.py:12
  - Confidence values: [0.62, 0.62]
  - Pipeline timing ms: 0.484

- Case: case-ruff-f401
  - Classification: LINT (expected: LINT)
  - Primary root cause: src/app.py:7:5: F401 `os` imported but unused at src/app.py:7
  - Top-1 file/line: src/app.py:7
  - Confidence values: [0.54, 0.54]
  - Pipeline timing ms: 0.342

- Case: case-typecheck-ts2345
  - Classification: TYPECHECK (expected: TYPECHECK)
  - Primary root cause: src/app.ts(14,5): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'. at src/app.ts:14
  - Top-1 file/line: src/app.ts:14
  - Confidence values: [0.62, 0.62]
  - Pipeline timing ms: 0.396
