# App Config Contract (MVP)

Repository-level app configuration schema (logical contract):

```json
{
  "enabled": true,
  "mode": "deterministic",
  "enable_pr_mode": false,
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
  - Has effect only when `enable_pr_mode=true`.
- `enable_pr_mode`:
  - Explicit opt-in gate for app-driven PR creation.
  - Must default to `false`.
  - When `false`, app mode keeps comment/artifact-only behavior.
- `min_pr_confidence`:
  - Float in `[0.0, 1.0]`.
- `post_comment`:
  - Whether app posts RCA summary comment for failed runs.

## Deterministic Defaults
- No automatic PR creation.
- Failure-safe handling when logs/diffs are missing.
- Machine-readable reason codes for skip/failure outcomes.
