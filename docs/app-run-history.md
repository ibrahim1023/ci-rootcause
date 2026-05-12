# App Run History Design

`ci-rootcause` does not require persistent storage for local development or the first
single-process deployment. GitHub comments are upserted with stable markers, inline comments
are matched by marker plus file/line, and commit statuses use a stable context.

For production deployments, add lightweight run history when you need restart recovery,
multi-instance workers, delivery dashboards, or stricter duplicate-delivery guarantees.

## Idempotency Keys

Recommended primary key:

```text
repository + workflow_run_id + run_attempt + head_sha + output_mode
```

Store GitHub delivery IDs separately because the same workflow run can be redelivered with a
new delivery ID.

## Minimal Record

```json
{
  "repository": "owner/repo",
  "delivery_id": "github-delivery-uuid",
  "workflow_run_id": 123456,
  "run_attempt": 1,
  "head_sha": "abc123",
  "base_sha": "def456",
  "pull_request_number": 42,
  "output_mode": "summary-inline",
  "status": "processing",
  "reason_code": "",
  "summary_comment_id": 1001,
  "inline_comment_ids": [
    {
      "path": "src/app.py",
      "line": 7,
      "comment_id": 2002
    }
  ],
  "status_context": "ci-rootcause/rca",
  "fix_pr_number": null,
  "rca_json_path": "artifacts/app/ci-rca.json",
  "rca_md_path": "artifacts/app/ci-rca.md",
  "created_at": "2026-05-12T00:00:00Z",
  "updated_at": "2026-05-12T00:00:30Z"
}
```

## State Transitions

- `accepted`: webhook signature and event shape passed.
- `processing`: worker started log/diff retrieval and RCA.
- `completed`: RCA and configured outputs succeeded.
- `partial`: RCA completed but a downstream output failed.
- `skipped`: event was intentionally ignored by policy.
- `error`: processing failed before RCA output was available.

## Local Mode

Local mode can remain storage-free. Redelivery is safe because GitHub output markers let the
app update existing comments. Commit statuses are immutable in GitHub, but repeated status
publishing uses the same context so the latest status is deterministic.

## Production Storage

A small SQLite database, Postgres table, Redis hash, or durable key-value store is enough.
Required capabilities:

- atomic insert-or-get by idempotency key,
- update by workflow run key,
- list recent records by repository,
- store output identifiers for comments, statuses, artifacts, and fix PR links.

## Restart Recovery

On startup, a production worker can scan records in `accepted` or `processing` state that are
older than a timeout and mark them as `error` or retry them. Retrying should reuse the same
idempotency key and existing GitHub output IDs where present.

## Non-Goals

- No auto-merge state is stored.
- No source code snapshots are stored.
- No secrets or raw private CI logs should be stored unless the deployment owner explicitly
  opts into that retention policy.
