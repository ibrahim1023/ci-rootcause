from __future__ import annotations

import json
from pathlib import Path

from src.contracts.converters import pr_result_from_agent_output, rca_output_from_agent_outputs

COMPAT_DIR = Path("fixtures/contracts/compat")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_rca_schema_compatibility_matrix() -> None:
    rca_files = sorted(COMPAT_DIR.glob("ci-rca.v*.json"))
    assert rca_files, "expected versioned RCA compatibility fixtures"

    canonical_serializations: list[str] = []
    for fixture in rca_files:
        payload = _load(fixture)
        contract = rca_output_from_agent_outputs(payload)
        canonical_serializations.append(contract.to_json())
        assert contract.meta.commit
        assert contract.meta.run_id

    assert len(set(canonical_serializations)) == 1


def test_pr_result_schema_compatibility_matrix() -> None:
    pr_files = sorted(COMPAT_DIR.glob("pr-result.v*.json"))
    assert pr_files, "expected versioned PR result compatibility fixtures"

    for fixture in pr_files:
        payload = _load(fixture)
        contract = pr_result_from_agent_output(payload)
        if contract.pr_created:
            assert contract.pr_url
            assert contract.pr_number is not None and contract.pr_number > 0
            assert contract.pr_branch
        else:
            assert contract.failure_reason
