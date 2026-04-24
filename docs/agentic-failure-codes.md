# Agentic Failure Reason Codes

This document defines the agentic-related reason-code categories surfaced through action outputs.

## Output Contract

When available, `pr_failure_reason_code` and `pr_failure_reason` in GitHub Action output include
agentic-specific failures even when PR creation is not attempted.

## Reason-Code Categories

| Code | Category | Meaning |
| --- | --- | --- |
| `AGENTIC_MISSING_KEY` | missing_key | Hosted provider selected in agentic mode without `provider_api_key`. |
| `AGENTIC_PROVIDER_ERROR` | provider_error | Provider call failed (network/API/response contract issues). |
| `VALIDATION_FAILED` | validation_failed | Validation commands failed before PR creation. |
| `AGENTIC_MAX_ATTEMPTS_EXCEEDED` | max_attempts_exceeded | Agentic proposer exhausted bounded retries without a valid proposal. |

## Notes

- Deterministic defaults remain unchanged.
- `create_fix_pr` defaults to `false`; these reason codes help explain agentic outcomes in safe mode.
