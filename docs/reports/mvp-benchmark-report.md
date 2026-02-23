# MVP Benchmark Report

- Suite: mvp-curated-v2
- Total cases: 6
- Completed cases: 6
- Completion rate: 1.0000
- Classification matches: 6
- Classification match rate: 1.0000
- Baseline classification matches: 4
- Baseline classification match rate: 0.6667
- Classification match lift vs baseline: 0.3333
- Primary root-cause matches: 6
- Primary root-cause accuracy: 1.0000
- Baseline primary root-cause accuracy: 1.0000
- Primary root-cause accuracy lift vs baseline: 0.0000
- Confidence reproducibility: 1.0000
- Artifact hash reproducibility: 1.0000
- Mean time-to-diagnosis (ms): 0.386
- Median time-to-diagnosis (ms): 0.367
- P95 time-to-diagnosis (ms): 0.473

## Baseline Definition

- Baseline model: `basic-log-summarizer-v1`
- Inputs: first failure event only (`error_signature`, `log_excerpt`, `stage`)
- Deterministic heuristic labels: `INFRA`, `TYPECHECK`, `LINT`, `BUILD`, `TEST`, fallback `UNKNOWN`
- Baseline intentionally excludes diff context and dependency-drift signals.

## Case Results

- Case: case-infra-timeout
  - Classification: INFRA (expected: INFRA)
  - Baseline classification: INFRA (match: True)
  - Primary root cause: ERROR: connection reset by peer while contacting package mirror at unknown file
  - Root cause match: True
  - Confidence values: [0.54, 0.54]
  - Confidence reproducible: True
  - Pipeline timing ms: 0.473

- Case: case-node-mixed-lock
  - Classification: DEPENDENCY (expected: DEPENDENCY)
  - Baseline classification: TEST (match: False)
  - Primary root cause: E AssertionError: assert 3 == 4 at unknown file
  - Root cause match: True
  - Confidence values: [0.6, 0.6]
  - Confidence reproducible: True
  - Pipeline timing ms: 0.572

- Case: case-python-lock-only
  - Classification: DEPENDENCY (expected: DEPENDENCY)
  - Baseline classification: TEST (match: False)
  - Primary root cause: E AssertionError: assert 3 == 4 at unknown file
  - Root cause match: True
  - Confidence values: [0.6, 0.6]
  - Confidence reproducible: True
  - Pipeline timing ms: 0.425

- Case: case-refactor-only
  - Classification: TEST (expected: TEST)
  - Baseline classification: TEST (match: True)
  - Primary root cause: E AssertionError: assert 3 == 4 at unknown file
  - Root cause match: True
  - Confidence values: [0.54, 0.54]
  - Confidence reproducible: True
  - Pipeline timing ms: 0.264

- Case: case-rename-and-modify
  - Classification: TEST (expected: TEST)
  - Baseline classification: TEST (match: True)
  - Primary root cause: E AssertionError: assert 3 == 4 at unknown file
  - Root cause match: True
  - Confidence values: [0.54, 0.54]
  - Confidence reproducible: True
  - Pipeline timing ms: 0.271

- Case: case-typecheck-ts2345
  - Classification: TYPECHECK (expected: TYPECHECK)
  - Baseline classification: TYPECHECK (match: True)
  - Primary root cause: src/app.ts(14,5): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'. at unknown file
  - Root cause match: True
  - Confidence values: [0.54, 0.54]
  - Confidence reproducible: True
  - Pipeline timing ms: 0.309
