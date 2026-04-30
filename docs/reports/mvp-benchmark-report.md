# MVP Benchmark Report

- Suite: mvp-curated-v3
- Total cases: 9
- Completed cases: 9
- Completion rate: 1.0000
- Classification matches: 9
- Classification match rate: 1.0000
- Baseline classification matches: 7
- Baseline classification match rate: 0.7778
- Classification match lift vs baseline: 0.2222
- Primary root-cause matches: 9
- Primary root-cause accuracy: 1.0000
- Top-1 root-cause cases: 8
- Top-1 root-cause matches: 8
- Top-1 root-cause accuracy: 1.0000
- Agentic proposal valid rate: 1.0000
- Agentic proposal valid cases: 2
- Validation pass rate: 0.5000
- Validation pass cases: 2
- Confidence reproducibility: 1.0000
- Artifact hash reproducibility: 1.0000
- Mean time-to-diagnosis (ms): 2.7440
- Median time-to-diagnosis (ms): 0.4950
- P95 time-to-diagnosis (ms): 10.6760

## Case Results

- Case: case-agentic-ruff-fail
  - Classification: LINT (expected: LINT)
  - Primary root cause: src/app.py:7:5: F401 `os` imported but unused at src/app.py:7
  - Top-1 file/line: src/app.py:7
  - Confidence values: [0.54, 0.54]
  - Pipeline timing ms: 10.796

- Case: case-agentic-ruff-pass
  - Classification: LINT (expected: LINT)
  - Primary root cause: src/app.py:7:5: F401 `os` imported but unused at src/app.py:7
  - Top-1 file/line: src/app.py:7
  - Confidence values: [0.54, 0.54]
  - Pipeline timing ms: 10.676

- Case: case-infra-timeout
  - Classification: INFRA (expected: INFRA)
  - Primary root cause: ERROR: connection reset by peer while contacting package mirror at unknown file
  - Top-1 file/line: n/a
  - Confidence values: [0.4225, 0.4225]
  - Pipeline timing ms: 0.444

- Case: case-node-mixed-lock
  - Classification: DEPENDENCY (expected: DEPENDENCY)
  - Primary root cause: E AssertionError: assert 3 == 4 at tests/test_math.py:12
  - Top-1 file/line: tests/test_math.py:12
  - Confidence values: [0.64, 0.64]
  - Pipeline timing ms: 0.545

- Case: case-python-lock-only
  - Classification: DEPENDENCY (expected: DEPENDENCY)
  - Primary root cause: E AssertionError: assert 3 == 4 at tests/test_math.py:12
  - Top-1 file/line: tests/test_math.py:12
  - Confidence values: [0.64, 0.64]
  - Pipeline timing ms: 0.459

- Case: case-refactor-only
  - Classification: TEST (expected: TEST)
  - Primary root cause: E AssertionError: assert 3 == 4 at tests/test_math.py:12
  - Top-1 file/line: tests/test_math.py:12
  - Confidence values: [0.62, 0.62]
  - Pipeline timing ms: 0.495

- Case: case-rename-and-modify
  - Classification: TEST (expected: TEST)
  - Primary root cause: E AssertionError: assert 3 == 4 at tests/test_math.py:12
  - Top-1 file/line: tests/test_math.py:12
  - Confidence values: [0.62, 0.62]
  - Pipeline timing ms: 0.533

- Case: case-ruff-f401
  - Classification: LINT (expected: LINT)
  - Primary root cause: src/app.py:7:5: F401 `os` imported but unused at src/app.py:7
  - Top-1 file/line: src/app.py:7
  - Confidence values: [0.54, 0.54]
  - Pipeline timing ms: 0.327

- Case: case-typecheck-ts2345
  - Classification: TYPECHECK (expected: TYPECHECK)
  - Primary root cause: src/app.ts(14,5): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'. at src/app.ts:14
  - Top-1 file/line: src/app.ts:14
  - Confidence values: [0.62, 0.62]
  - Pipeline timing ms: 0.424
