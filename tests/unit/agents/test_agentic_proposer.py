from __future__ import annotations

import pytest

from src.agents.agentic_proposer import (
    AgenticProposalContractError,
    AgenticProposalProviderError,
    run_agentic_patch_proposal,
    validate_agentic_patch_proposal,
)


class _StaticProposer:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def propose(self, payload: dict) -> dict:  # noqa: ANN001
        del payload
        return dict(self._payload)


class _ProviderFailureProposer:
    def propose(self, payload: dict) -> dict:  # noqa: ANN001
        del payload
        raise AgenticProposalProviderError("provider unavailable")


def test_validate_agentic_patch_proposal_accepts_valid_shape() -> None:
    proposal = validate_agentic_patch_proposal(
        {
            "summary": "Typecheck mismatch in parser",
            "candidate_fix_steps": [
                {
                    "file": "src/parser.py",
                    "instruction": "Align return type to annotation",
                    "rationale": "CI shows incompatible return type",
                }
            ],
            "patch_plan": [
                {
                    "op": "modify",
                    "file": "src/parser.py",
                    "content": "def parse() -> int:\n    return 1\n",
                }
            ],
        }
    )

    assert proposal.summary.startswith("Typecheck")
    assert proposal.candidate_fix_steps[0].file == "src/parser.py"
    assert proposal.patch_plan[0].op == "modify"


def test_validate_agentic_patch_proposal_rejects_invalid_op() -> None:
    with pytest.raises(AgenticProposalContractError, match="must be one of"):
        validate_agentic_patch_proposal(
            {
                "summary": "bad op",
                "candidate_fix_steps": [{"file": "src/a.py", "instruction": "x", "rationale": "y"}],
                "patch_plan": [{"op": "append", "file": "src/a.py", "content": ""}],
            }
        )


def test_run_agentic_patch_proposal_surfaces_provider_error_code() -> None:
    result = run_agentic_patch_proposal(payload={}, proposer=_ProviderFailureProposer())

    assert result["proposal_created"] is False
    assert result["failure_reason_code"] == "AGENTIC_PROPOSAL_PROVIDER_ERROR"


def test_run_agentic_patch_proposal_surfaces_contract_error_code() -> None:
    bad = _StaticProposer(
        {
            "summary": "bad contract",
            "candidate_fix_steps": "not-a-list",
            "patch_plan": [],
        }
    )
    result = run_agentic_patch_proposal(payload={}, proposer=bad)

    assert result["proposal_created"] is False
    assert result["failure_reason_code"] == "AGENTIC_PROPOSAL_CONTRACT_ERROR"


def test_run_agentic_patch_proposal_returns_structured_payload() -> None:
    good = _StaticProposer(
        {
            "summary": "good contract",
            "candidate_fix_steps": [
                {"file": "src/a.py", "instruction": "fix", "rationale": "ci evidence"}
            ],
            "patch_plan": [{"op": "modify", "file": "src/a.py", "content": "print(1)\n"}],
        }
    )
    result = run_agentic_patch_proposal(payload={"classification": "TYPECHECK"}, proposer=good)

    assert result["proposal_created"] is True
    assert result["failure_reason_code"] == ""
    assert result["candidate_fix_steps"][0]["file"] == "src/a.py"
