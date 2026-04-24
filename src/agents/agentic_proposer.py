from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, parse
from urllib import request as urllib_request

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


def _provider_prompt(payload: dict[str, Any]) -> str:
    return (
        "You are a CI fix planner. Return STRICT JSON only with keys: "
        "summary, candidate_fix_steps, patch_plan. "
        "candidate_fix_steps items require file, instruction, rationale. "
        "patch_plan items require op, file, content. "
        "Use only evidence-backed paths from allowed_files.\n\n"
        f"INPUT:\n{json.dumps(payload, sort_keys=True)}"
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise AgenticProposalProviderError("provider response was empty")
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise AgenticProposalProviderError("provider response did not contain JSON object")
    snippet = stripped[start : end + 1]
    try:
        payload = json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise AgenticProposalProviderError(f"provider response JSON parse failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise AgenticProposalProviderError("provider JSON response must be an object")
    return payload


def _request_json(*, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(url=url, method="POST", headers=headers, data=body)
    try:
        with urllib_request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AgenticProposalProviderError(
            f"provider HTTP error {exc.code} for {url}: {detail}"
        ) from exc
    except error.URLError as exc:
        raise AgenticProposalProviderError(f"provider network error for {url}: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgenticProposalProviderError(f"provider returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AgenticProposalProviderError("provider response must be a JSON object")
    return parsed


def _decode_openai_payload(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    output = payload.get("output")
    if isinstance(output, list):
        fragments: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    fragments.append(part["text"])
        if fragments:
            return "\n".join(fragments)
    raise AgenticProposalProviderError("openai response missing output text")


def _decode_anthropic_payload(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        raise AgenticProposalProviderError("anthropic response missing content list")
    fragments: list[str] = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            fragments.append(item["text"])
    if not fragments:
        raise AgenticProposalProviderError("anthropic response missing text content")
    return "\n".join(fragments)


def _decode_gemini_payload(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise AgenticProposalProviderError("gemini response missing candidates")
    first = candidates[0]
    if not isinstance(first, dict):
        raise AgenticProposalProviderError("gemini first candidate must be object")
    content = first.get("content")
    if not isinstance(content, dict):
        raise AgenticProposalProviderError("gemini candidate content missing")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise AgenticProposalProviderError("gemini content parts missing")
    fragments: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            fragments.append(part["text"])
    if not fragments:
        raise AgenticProposalProviderError("gemini response missing text part")
    return "\n".join(fragments)


class HostedLlmPatchProposer:
    def __init__(self, *, provider: str, model: str, api_key: str) -> None:
        self.provider = provider.strip().lower()
        self.model = model.strip()
        self.api_key = api_key.strip()
        if not self.api_key:
            raise AgenticProposalProviderError("provider api key is required for hosted proposer")

    def _propose_openai(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = _request_json(
            url="https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            payload={
                "model": self.model,
                "input": _provider_prompt(payload),
                "temperature": 0,
            },
        )
        return _extract_json_object(_decode_openai_payload(response))

    def _propose_anthropic(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = _request_json(
            url="https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload={
                "model": self.model,
                "max_tokens": 1200,
                "temperature": 0,
                "messages": [{"role": "user", "content": _provider_prompt(payload)}],
            },
        )
        return _extract_json_object(_decode_anthropic_payload(response))

    def _propose_gemini(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = parse.urlencode({"key": self.api_key})
        response = _request_json(
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?{query}",
            headers={"Content-Type": "application/json"},
            payload={
                "contents": [{"parts": [{"text": _provider_prompt(payload)}]}],
                "generationConfig": {"temperature": 0},
            },
        )
        return _extract_json_object(_decode_gemini_payload(response))

    def propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.provider == "openai":
            return self._propose_openai(payload)
        if self.provider == "anthropic":
            return self._propose_anthropic(payload)
        if self.provider == "gemini":
            return self._propose_gemini(payload)
        raise AgenticProposalProviderError(f"unsupported hosted provider: {self.provider}")


class LocalLlmPatchProposer:
    def __init__(self, *, model: str, base_url: str = "http://localhost:11434") -> None:
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")

    def propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = _request_json(
            url=f"{self.base_url}/api/generate",
            headers={"Content-Type": "application/json"},
            payload={
                "model": self.model,
                "prompt": _provider_prompt(payload),
                "stream": False,
                "format": "json",
            },
        )
        text = response.get("response")
        if not isinstance(text, str):
            raise AgenticProposalProviderError("ollama response missing string field 'response'")
        return _extract_json_object(text)


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
    max_attempts: int = 2,
) -> dict[str, Any]:
    attempt_limit = max(1, int(max_attempts))
    attempt_summaries: list[dict[str, Any]] = []
    proposal: AgenticPatchProposal | None = None
    for attempt in range(1, attempt_limit + 1):
        try:
            candidate_payload = dict(payload)
            candidate_payload["agentic_attempt"] = attempt
            candidate_payload["previous_attempts"] = list(attempt_summaries)
            raw = proposer.propose(candidate_payload)
            proposal = validate_agentic_patch_proposal(raw)
            attempt_summaries.append(
                {"attempt": attempt, "status": "success", "failure_reason_code": ""}
            )
            break
        except AgenticProposalContractError as exc:
            attempt_summaries.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "failure_reason_code": "AGENTIC_PROPOSAL_CONTRACT_ERROR",
                    "failure_reason": str(exc),
                }
            )
            continue
        except AgenticProposalProviderError as exc:
            attempt_summaries.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "failure_reason_code": "AGENTIC_PROPOSAL_PROVIDER_ERROR",
                    "failure_reason": str(exc),
                }
            )
            continue

    if proposal is None:
        return {
            "proposal_created": False,
            "failure_reason_code": "AGENTIC_PROPOSAL_MAX_ATTEMPTS_EXCEEDED",
            "failure_reason": "agentic proposal attempts exhausted",
            "attempt_count": len(attempt_summaries),
            "attempt_summaries": attempt_summaries,
        }

    return {
        "proposal_created": True,
        "failure_reason_code": "",
        "failure_reason": "",
        "attempt_count": len(attempt_summaries),
        "attempt_summaries": attempt_summaries,
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
