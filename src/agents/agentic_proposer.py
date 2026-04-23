from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from src.path_safety import PathSafetyError, normalize_repo_relative_path


class AgenticProposalError(RuntimeError):
    """Base type for agentic proposal failures."""


class AgenticProposalProviderError(AgenticProposalError):
    """Raised when provider execution fails."""


class AgenticProposalContractError(AgenticProposalError):
    """Raised when proposer output violates the structured contract."""


class LlmPatchProposer(Protocol):
    def propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return a structured proposal payload."""


@dataclass(frozen=True)
class CandidateFixStep:
    file: str
    instruction: str
    rationale: str


@dataclass(frozen=True)
class PatchPlanOp:
    op: str
    file: str
    content: str


@dataclass(frozen=True)
class AgenticPatchProposal:
    summary: str
    candidate_fix_steps: tuple[CandidateFixStep, ...]
    patch_plan: tuple[PatchPlanOp, ...]


class HostedLlmPatchProposer:
    def __init__(self, *, provider: str, model: str, api_key: str) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key

    def propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        raise AgenticProposalProviderError(
            f"Hosted proposer is not yet implemented for provider '{self.provider}'"
        )


class LocalLlmPatchProposer:
    def __init__(self, *, model: str) -> None:
        self.model = model

    def propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        raise AgenticProposalProviderError(
            f"Local proposer is not yet implemented for model '{self.model}'"
        )


def _require_non_empty_str(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgenticProposalContractError(f"{field} must be a non-empty string")
    return value.strip()


def _normalize_file(file_value: Any, *, field: str) -> str:
    file_path = _require_non_empty_str(file_value, field=field)
    try:
        return normalize_repo_relative_path(file_path)
    except PathSafetyError as exc:
        raise AgenticProposalContractError(str(exc)) from exc


def validate_agentic_patch_proposal(payload: dict[str, Any]) -> AgenticPatchProposal:
    if not isinstance(payload, dict):
        raise AgenticProposalContractError("proposal payload must be a JSON object")

    summary = _require_non_empty_str(payload.get("summary"), field="summary")
    raw_steps = payload.get("candidate_fix_steps")
    raw_plan = payload.get("patch_plan")
    if not isinstance(raw_steps, list):
        raise AgenticProposalContractError("candidate_fix_steps must be a JSON list")
    if not isinstance(raw_plan, list):
        raise AgenticProposalContractError("patch_plan must be a JSON list")

    steps: list[CandidateFixStep] = []
    for index, item in enumerate(raw_steps):
        if not isinstance(item, dict):
            raise AgenticProposalContractError(
                f"candidate_fix_steps[{index}] must be a JSON object"
            )
        steps.append(
            CandidateFixStep(
                file=_normalize_file(item.get("file"), field=f"candidate_fix_steps[{index}].file"),
                instruction=_require_non_empty_str(
                    item.get("instruction"),
                    field=f"candidate_fix_steps[{index}].instruction",
                ),
                rationale=_require_non_empty_str(
                    item.get("rationale"),
                    field=f"candidate_fix_steps[{index}].rationale",
                ),
            )
        )

    plan: list[PatchPlanOp] = []
    for index, item in enumerate(raw_plan):
        if not isinstance(item, dict):
            raise AgenticProposalContractError(f"patch_plan[{index}] must be a JSON object")
        op = _require_non_empty_str(item.get("op"), field=f"patch_plan[{index}].op").lower()
        if op not in {"modify", "create", "delete", "rename"}:
            raise AgenticProposalContractError(
                f"patch_plan[{index}].op must be one of: modify, create, delete, rename"
            )
        plan.append(
            PatchPlanOp(
                op=op,
                file=_normalize_file(item.get("file"), field=f"patch_plan[{index}].file"),
                content=str(item.get("content", "")),
            )
        )

    return AgenticPatchProposal(
        summary=summary,
        candidate_fix_steps=tuple(steps),
        patch_plan=tuple(plan),
    )


def run_agentic_patch_proposal(
    payload: dict[str, Any],
    *,
    proposer: LlmPatchProposer,
) -> dict[str, Any]:
    try:
        raw = proposer.propose(payload)
        proposal = validate_agentic_patch_proposal(raw)
    except AgenticProposalContractError as exc:
        return {
            "proposal_created": False,
            "failure_reason_code": "AGENTIC_PROPOSAL_CONTRACT_ERROR",
            "failure_reason": str(exc),
        }
    except AgenticProposalProviderError as exc:
        return {
            "proposal_created": False,
            "failure_reason_code": "AGENTIC_PROPOSAL_PROVIDER_ERROR",
            "failure_reason": str(exc),
        }

    return {
        "proposal_created": True,
        "failure_reason_code": "",
        "failure_reason": "",
        "proposal_summary": proposal.summary,
        "candidate_fix_steps": [
            {"file": item.file, "instruction": item.instruction, "rationale": item.rationale}
            for item in proposal.candidate_fix_steps
        ],
        "patch_plan": [
            {"op": item.op, "file": item.file, "content": item.content}
            for item in proposal.patch_plan
        ],
    }
