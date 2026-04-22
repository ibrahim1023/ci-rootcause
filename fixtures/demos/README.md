# Demo Fixtures

Reproducible narrative demo cases for sharing ci-rootcause outputs.

Each case includes:
- `ci.log`
- `change.diff`
- `expected-ci-rca.json`
- `expected-ci-rca.md`

Cases:
- `01-dependency-lockfile-drift`: lockfile-driven dependency classification example.
- `02-typecheck-ts2345`: deterministic TypeScript typecheck failure example.
- `03-infra-timeout`: infrastructure/network timeout classification example.
