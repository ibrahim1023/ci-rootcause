# Migration Guide: Action Mode -> App Mode

## Goal

Move from workflow-YAML action integration to app-first webhook processing without breaking current users.

## Recommended Migration Sequence

1. Keep existing action workflow active.
2. Install and configure app mode with safe defaults:
   - `enable_pr_mode=false`
   - `create_fix_pr=false`
3. Validate app-mode outputs on failed runs:
   - comment posting behavior,
   - artifact path outputs,
   - outcome reason codes.
4. Compare app-mode RCA output against action-mode output on the same fixture runs.
5. Once stable, remove or reduce action workflow usage for target repositories.

## Backward Compatibility

- Action mode remains supported and unchanged.
- Existing action users do not need to migrate immediately.
- App mode and action mode can be run in parallel during transition.

## PR Creation Policy During Migration

- Keep PR creation disabled initially.
- If enabling PR creation later, explicitly set:
  - `enable_pr_mode=true`
  - `create_fix_pr=true`
- Existing guardrails still apply (confidence thresholds, evidence-backed file restrictions, no auto-merge).

## Validation Checklist

- Webhook signature verification succeeds.
- Failed `workflow_run` events are processed; non-failures are skipped.
- `ci-rca.json` and `ci-rca.md` paths are present.
- Duplicate comment spam does not occur on repeated runs.
- Reason-code outputs are stable and documented.
