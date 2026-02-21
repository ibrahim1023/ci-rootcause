# MVP Benchmark Report

- Suite: mvp-curated-v1
- Total cases: 4
- Completed cases: 4
- Classification matches: 4
- Primary root-cause matches: 4
- Primary root-cause accuracy: 1.0000
- Confidence reproducibility: 1.0000
- Mean time-to-diagnosis (ms): 0.389

## Case Results

- Case: case-node-mixed-lock
  - Classification: DEPENDENCY (expected: DEPENDENCY)
  - Primary root cause: E AssertionError: assert 3 == 4 at unknown file
  - Root cause match: True
  - Confidence values: [0.6, 0.6]
  - Confidence reproducible: True
  - Pipeline timing ms: 0.601

- Case: case-python-lock-only
  - Classification: DEPENDENCY (expected: DEPENDENCY)
  - Primary root cause: E AssertionError: assert 3 == 4 at unknown file
  - Root cause match: True
  - Confidence values: [0.6, 0.6]
  - Confidence reproducible: True
  - Pipeline timing ms: 0.372

- Case: case-refactor-only
  - Classification: TEST (expected: TEST)
  - Primary root cause: E AssertionError: assert 3 == 4 at unknown file
  - Root cause match: True
  - Confidence values: [0.54, 0.54]
  - Confidence reproducible: True
  - Pipeline timing ms: 0.290

- Case: case-rename-and-modify
  - Classification: TEST (expected: TEST)
  - Primary root cause: E AssertionError: assert 3 == 4 at unknown file
  - Root cause match: True
  - Confidence values: [0.54, 0.54]
  - Confidence reproducible: True
  - Pipeline timing ms: 0.295
