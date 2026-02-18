# Contributing

## Branch Naming

Use one of these formats:

- `feat/<short-description>`
- `fix/<short-description>`
- `chore/<short-description>`
- `docs/<short-description>`

## Pull Request Checklist

- [ ] Linked relevant task(s) from `docs/task.md`
- [ ] Updated docs (`docs/scope.md`, `README.md`) when contracts/behavior changed
- [ ] Added or updated tests
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] `pytest` passes
- [ ] No secrets or run artifacts committed

## Test Requirements

At minimum for code changes:

- Add unit tests for deterministic logic changes
- Add/extend integration tests for pipeline behavior changes
- Keep deterministic outputs stable for same inputs

## Notes

- Never auto-merge generated fix PRs.
- Do not bypass branch protections.
