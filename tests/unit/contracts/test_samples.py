import json
from pathlib import Path

from src.contracts.converters import pr_result_from_agent_output, rca_output_from_agent_outputs


def test_sample_rca_artifact_is_valid_contract() -> None:
    payload = json.loads(Path("fixtures/contracts/ci-rca.sample.json").read_text())
    contract = rca_output_from_agent_outputs(payload)
    assert contract.meta.run_id == "gha_001"


def test_sample_pr_result_artifact_is_valid_contract() -> None:
    payload = json.loads(Path("fixtures/contracts/pr-result.sample.json").read_text())
    contract = pr_result_from_agent_output(payload)
    assert contract.pr_created is False
