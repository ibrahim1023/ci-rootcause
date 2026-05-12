from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.agentic_proposer import (
    AgenticProposalContractError,
    AgenticProposalProviderError,
    HostedLlmPatchProposer,
    LocalLlmPatchProposer,
    _extract_json_object,
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


class _FlakyThenGoodProposer:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, payload: dict) -> dict:  # noqa: ANN001
        del payload
        self.calls += 1
        if self.calls == 1:
            raise AgenticProposalProviderError("temporary provider error")
        return {
            "summary": "recovered",
            "candidate_fix_steps": [
                {"file": "src/a.py", "instruction": "fix", "rationale": "ci evidence"}
            ],
            "patch_plan": [{"op": "modify", "file": "src/a.py", "content": "print(1)\n"}],
        }


class _BadContractThenGoodProposer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def propose(self, payload: dict) -> dict:  # noqa: ANN001
        self.calls.append(dict(payload))
        if len(self.calls) == 1:
            return {
                "summary": "bad op",
                "candidate_fix_steps": [
                    {"file": "src/a.py", "instruction": "fix", "rationale": "ci evidence"}
                ],
                "patch_plan": [{"op": "append", "file": "src/a.py", "content": "print(1)\n"}],
            }

        retry_payload = self.calls[-1]
        assert (
            "must be one of: modify, create, delete, rename" in retry_payload["repair_instructions"]
        )
        assert "original allowed_files and CI evidence" in retry_payload["repair_instructions"]
        assert retry_payload["allowed_files"] == ["src/a.py"]
        assert retry_payload["primary_root_cause"]["evidence"] == "src/a.py:1: error"
        return {
            "summary": "recovered",
            "candidate_fix_steps": [
                {"file": "src/a.py", "instruction": "fix", "rationale": "ci evidence"}
            ],
            "patch_plan": [{"op": "modify", "file": "src/a.py", "content": "print(1)\n"}],
        }


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


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


def test_validate_agentic_patch_proposal_normalizes_common_modify_aliases() -> None:
    proposal = validate_agentic_patch_proposal(
        {
            "summary": "weak local model used update op",
            "candidate_fix_steps": [{"file": "src/a.py", "instruction": "x", "rationale": "y"}],
            "patch_plan": [{"op": "update", "file": "src/a.py", "content": "print(1)\n"}],
        }
    )

    assert proposal.patch_plan[0].op == "modify"


def test_validate_agentic_patch_proposal_rejects_incomplete_modify_plan() -> None:
    with pytest.raises(AgenticProposalContractError, match="content must be non-empty"):
        validate_agentic_patch_proposal(
            {
                "summary": "missing content",
                "candidate_fix_steps": [{"file": "src/a.py", "instruction": "x", "rationale": "y"}],
                "patch_plan": [{"op": "modify", "file": "src/a.py"}],
            }
        )


def test_agentic_regression_fixtures_cover_malformed_json_and_bad_plans() -> None:
    malformed = Path("fixtures/agentic-proposals/malformed-json.txt").read_text()
    with pytest.raises(AgenticProposalProviderError, match="did not contain JSON object"):
        _extract_json_object(malformed)

    unsupported = json.loads(
        Path("fixtures/agentic-proposals/unsupported-operation.json").read_text()
    )
    with pytest.raises(AgenticProposalContractError, match="must be one of"):
        validate_agentic_patch_proposal(unsupported)

    incomplete = json.loads(
        Path("fixtures/agentic-proposals/incomplete-patch-plan.json").read_text()
    )
    with pytest.raises(AgenticProposalContractError, match="content must be non-empty"):
        validate_agentic_patch_proposal(incomplete)


def test_validate_agentic_patch_proposal_rejects_unsafe_paths() -> None:
    with pytest.raises(AgenticProposalContractError, match="Parent directory traversal"):
        validate_agentic_patch_proposal(
            {
                "summary": "bad path",
                "candidate_fix_steps": [
                    {"file": "../escape.py", "instruction": "x", "rationale": "y"}
                ],
                "patch_plan": [{"op": "modify", "file": "../escape.py", "content": "x\n"}],
            }
        )


def test_run_agentic_patch_proposal_surfaces_provider_error_code() -> None:
    result = run_agentic_patch_proposal(
        payload={},
        proposer=_ProviderFailureProposer(),
        max_attempts=1,
    )

    assert result["proposal_created"] is False
    assert result["failure_reason_code"] == "AGENTIC_PROPOSAL_MAX_ATTEMPTS_EXCEEDED"
    assert result["attempt_count"] == 1


def test_run_agentic_patch_proposal_surfaces_contract_error_code() -> None:
    bad = _StaticProposer(
        {
            "summary": "bad contract",
            "candidate_fix_steps": "not-a-list",
            "patch_plan": [],
        }
    )
    result = run_agentic_patch_proposal(payload={}, proposer=bad, max_attempts=1)

    assert result["proposal_created"] is False
    assert result["failure_reason_code"] == "AGENTIC_PROPOSAL_MAX_ATTEMPTS_EXCEEDED"


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


def test_run_agentic_patch_proposal_retries_and_recovers() -> None:
    proposer = _FlakyThenGoodProposer()
    result = run_agentic_patch_proposal(payload={}, proposer=proposer, max_attempts=2)

    assert result["proposal_created"] is True
    assert result["attempt_count"] == 2
    assert (
        result["attempt_summaries"][0]["failure_reason_code"] == "AGENTIC_PROPOSAL_PROVIDER_ERROR"
    )
    assert result["attempt_summaries"][1]["status"] == "success"


def test_run_agentic_patch_proposal_retries_contract_error_with_repair_context() -> None:
    proposer = _BadContractThenGoodProposer()
    result = run_agentic_patch_proposal(
        payload={
            "allowed_files": ["src/a.py"],
            "primary_root_cause": {
                "file": "src/a.py",
                "line": 1,
                "evidence": "src/a.py:1: error",
            },
        },
        proposer=proposer,
        max_attempts=2,
    )

    assert result["proposal_created"] is True
    assert result["attempt_count"] == 2
    assert len(proposer.calls) == 2
    assert (
        result["attempt_summaries"][0]["failure_reason_code"] == "AGENTIC_PROPOSAL_CONTRACT_ERROR"
    )
    assert "repair_instructions" not in proposer.calls[0]
    assert proposer.calls[1]["previous_attempts"][0]["failure_reason"] == (
        "patch_plan[0].op must be one of: modify, create, delete, rename"
    )


def test_hosted_openai_proposer_parses_response(monkeypatch) -> None:
    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del timeout
        assert req.full_url == "https://api.openai.com/v1/responses"
        payload = {
            "output_text": json.dumps(
                {
                    "summary": "openai summary",
                    "candidate_fix_steps": [
                        {"file": "src/a.py", "instruction": "fix", "rationale": "because"}
                    ],
                    "patch_plan": [{"op": "modify", "file": "src/a.py", "content": "print(1)\n"}],
                }
            )
        }
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("src.agents.agentic_proposer.urllib_request.urlopen", fake_urlopen)
    proposer = HostedLlmPatchProposer(provider="openai", model="gpt-5.4-mini", api_key="key")

    payload = proposer.propose({"classification": "TYPECHECK", "allowed_files": ["src/a.py"]})
    assert payload["summary"] == "openai summary"


def test_hosted_gemini_proposer_parses_response(monkeypatch) -> None:
    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del timeout
        assert ":generateContent?" in req.full_url
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "summary": "gemini summary",
                                        "candidate_fix_steps": [
                                            {
                                                "file": "src/a.py",
                                                "instruction": "fix",
                                                "rationale": "because",
                                            }
                                        ],
                                        "patch_plan": [
                                            {
                                                "op": "modify",
                                                "file": "src/a.py",
                                                "content": "print(1)\n",
                                            }
                                        ],
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("src.agents.agentic_proposer.urllib_request.urlopen", fake_urlopen)
    proposer = HostedLlmPatchProposer(provider="gemini", model="gemini-2.5-flash", api_key="key")

    payload = proposer.propose({"classification": "TYPECHECK", "allowed_files": ["src/a.py"]})
    assert payload["summary"] == "gemini summary"


def test_hosted_anthropic_proposer_parses_response(monkeypatch) -> None:
    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del timeout
        assert req.full_url == "https://api.anthropic.com/v1/messages"
        payload = {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "summary": "anthropic summary",
                            "candidate_fix_steps": [
                                {"file": "src/a.py", "instruction": "fix", "rationale": "because"}
                            ],
                            "patch_plan": [
                                {"op": "modify", "file": "src/a.py", "content": "print(1)\n"}
                            ],
                        }
                    )
                }
            ]
        }
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("src.agents.agentic_proposer.urllib_request.urlopen", fake_urlopen)
    proposer = HostedLlmPatchProposer(
        provider="anthropic", model="claude-sonnet-4.5", api_key="key"
    )

    payload = proposer.propose({"classification": "TYPECHECK", "allowed_files": ["src/a.py"]})
    assert payload["summary"] == "anthropic summary"


def test_local_ollama_proposer_parses_response(monkeypatch) -> None:
    captured_prompt = ""

    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        nonlocal captured_prompt
        del timeout
        assert req.full_url == "http://localhost:11434/api/generate"
        request_payload = json.loads(req.data.decode("utf-8"))
        captured_prompt = request_payload["prompt"]
        payload = {
            "response": json.dumps(
                {
                    "summary": "ollama summary",
                    "candidate_fix_steps": [
                        {"file": "src/a.py", "instruction": "fix", "rationale": "because"}
                    ],
                    "patch_plan": [{"op": "modify", "file": "src/a.py", "content": "print(1)\n"}],
                }
            )
        }
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("src.agents.agentic_proposer.urllib_request.urlopen", fake_urlopen)
    proposer = LocalLlmPatchProposer(model="qwen2.5-coder")

    payload = proposer.propose({"classification": "TYPECHECK", "allowed_files": ["src/a.py"]})
    assert payload["summary"] == "ollama summary"
    assert (
        "Allowed patch_plan op values are exactly: modify, create, delete, rename"
        in captured_prompt
    )
    assert "Never use unsupported operations such as append" in captured_prompt
    assert '"patch_plan"' in captured_prompt
    assert '"candidate_fix_steps"' in captured_prompt
