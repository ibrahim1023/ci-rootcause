# Contract Summary

This document describes the current MVP contract models in `src/contracts/models.py`.

## Failure Classification Agent Output

`run_failure_classification(...)` returns:

- `classification` (`FailureClass` value)
- `signals` (deterministic matched signals)
- `flaky_test_detection` (deterministic historical pattern result)

`flaky_test_detection` includes:

- `detected` (boolean)
- `score` (`0.0` to `1.0`)
- `matched_test_ids`
- `matched_failure_runs`
- `unique_failure_signatures`
- `history_window_size`

## Failure Graph

`FailureGraph` is a list of `FailureNode` objects.

Required failure node fields:

- `stage`
- `timestamp`
- `error_signature`

Optional failure node fields:

- `file`
- `line` (must be `> 0` when present)
- `stack_frames`
- `log_excerpt`
- `is_first_failure`

Validation rules:

- `FailureGraph.nodes` must not be empty.
- Exactly one node must have `is_first_failure=true`.

## RCA Output (`ci-rca.json`)

`RCAOutput` includes:

- `summary`
- `classification` (`FailureClass` enum)
- `primary_root_cause`
- `ranked_alternatives`
- `suggested_fix`
- `meta` (`commit`, `run_id`)

Validation rules:

- `summary` is required.
- Confidence and score values are constrained to `[0, 1]`.
- Evidence entries must include `file`.

Deterministic serialization:

- `RCAOutput.to_json()` uses stable key ordering (`sort_keys=True`).

## PR Creation Result

`PRCreationResult` includes:

- `pr_created`
- `pr_url`
- `pr_number`
- `pr_branch`
- `failure_reason`

Validation rules:

- If `pr_created=true`: `pr_url`, `pr_number (>0)`, and `pr_branch` are required.
- If `pr_created=false`: `failure_reason` is required.

## Conversion Helpers

`src/contracts/converters.py` provides:

- `failure_graph_from_log_ingest(payload)`
- `rca_output_from_agent_outputs(payload)`
- `pr_result_from_agent_output(payload)`

These helpers convert raw agent payloads to typed contract models and validate them.

## Compatibility Matrix Fixtures

Versioned compatibility fixtures are tracked under `fixtures/contracts/compat/`.

- RCA: `ci-rca.v*.json`
- PR result: `pr-result.v*.json`

`tests/unit/contracts/test_schema_compatibility_matrix.py` validates that current converters
accept these snapshots and preserve canonical contract semantics.
