# Agentic Proposal Rubric

## Target Behavior
Agentic/Ollama proposals should improve fix planning without bypassing deterministic guardrails.

## Deterministic Gates
- Output must be valid JSON after provider decoding.
- Output must include `summary`, `candidate_fix_steps`, and `patch_plan`.
- `candidate_fix_steps` items must include `file`, `instruction`, and `rationale`.
- `patch_plan` items must include `op`, `file`, and `content`.
- `op` must be one of `modify`, `create`, `delete`, or `rename`.
- All files must be repo-relative, safe paths.
- All files must be within the allowed evidence scope.
- Proposal must not require auto-merge or hidden privileged operations.

## Failure Modes
- `schema_invalid`: malformed or missing required fields.
- `unsupported_operation`: patch operation outside the allowed set.
- `unsafe_path`: absolute path or parent traversal.
- `out_of_scope_file`: proposal changes a file not supported by evidence.
- `unsupported_claim`: proposal claims a cause not visible in evidence.
- `provider_failure`: local or hosted provider could not return a response.

## Initial Threshold
Agentic proposal schema pass rate must be at least `0.80` before agentic output is promoted in comments or auto-fix flows.
