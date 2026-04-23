# App Config Contract (MVP)

Repository-level app configuration schema (logical contract):

```json
{
  "enabled": true,
  "mode": "deterministic",
  "create_fix_pr": false,
  "min_pr_confidence": 0.75,
  "post_comment": true
}
```

## Field Notes
- `enabled`:
  - Whether app processing is enabled for the repository.
- `mode`:
  - `deterministic` | `agentic_assist` | `agentic_full`.
  - MVP default: `deterministic`.
- `create_fix_pr`:
  - Must default to `false`.
  - If enabled later, existing PR guardrails must still apply.
- `min_pr_confidence`:
  - Float in `[0.0, 1.0]`.
- `post_comment`:
  - Whether app posts RCA summary comment for failed runs.

## Deterministic Defaults
- No automatic PR creation.
- Failure-safe handling when logs/diffs are missing.
- Machine-readable reason codes for skip/failure outcomes.
