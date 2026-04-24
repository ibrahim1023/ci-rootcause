from __future__ import annotations

from pathlib import Path

from src.agents.agentic_proposer import AgenticProposalProviderError
from src.core.orchestration import PipelineRequest, run_pipeline


def _sample_log() -> str:
    return "\n".join(
        [
            "##[group] test",
            "Traceback (most recent call last):",
            '  File "src/app.py", line 7, in <module>',
            "AssertionError: expected 1 == 2",
            "##[endgroup]",
        ]
    )


def _sample_diff() -> str:
    return "\n".join(
        [
            "diff --git a/src/app.py b/src/app.py",
            "index 1111111..2222222 100644",
            "--- a/src/app.py",
            "+++ b/src/app.py",
            "@@ -1 +1 @@",
            "-value = 1",
            "+value = 2",
        ]
    )


def test_agentic_assist_integration_success_path(tmp_path: Path, monkeypatch) -> None:
    def _proposal(self, payload: dict) -> dict:  # noqa: ANN001
        del self, payload
        return {
            "summary": "candidate ready",
            "candidate_fix_steps": [
                {
                    "file": "src/app.py",
                    "instruction": "Fix assertion mismatch",
                    "rationale": "Matches failing evidence",
                }
            ],
            "patch_plan": [{"op": "modify", "file": "src/app.py", "content": "value = 1\n"}],
        }

    monkeypatch.setattr("src.core.orchestration.LocalLlmPatchProposer.propose", _proposal)

    request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-24T00:00:00Z",
        commit="abc123",
        run_id="gha_agentic_integration_success",
        base_commit="abc122",
        head_commit="abc123",
        output_dir=str(tmp_path / "success"),
        create_fix_pr=False,
        execution_mode="agentic_assist",
        llm_provider="local",
        llm_model="local-default",
        use_adk_runtime=False,
    )

    state = run_pipeline(request=request)

    assert state.pipeline_status == "completed"
    fix_output = state.agent_outputs["fix_planner"]
    assert fix_output["agentic_proposal"]["proposal_created"] is True
    assert any(step["file"] == "src/app.py" for step in fix_output["fix_steps"])


def test_agentic_assist_integration_fallback_matches_deterministic_baseline(
    tmp_path: Path, monkeypatch
) -> None:
    deterministic_request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-24T00:00:00Z",
        commit="abc123",
        run_id="gha_agentic_integration_baseline",
        base_commit="abc122",
        head_commit="abc123",
        output_dir=str(tmp_path / "deterministic"),
        create_fix_pr=False,
        execution_mode="deterministic",
        use_adk_runtime=False,
    )
    deterministic_state = run_pipeline(request=deterministic_request)

    def _provider_error(self, payload: dict) -> dict:  # noqa: ANN001
        del self, payload
        raise AgenticProposalProviderError("provider unavailable")

    monkeypatch.setattr(
        "src.core.orchestration.LocalLlmPatchProposer.propose",
        _provider_error,
    )

    assist_request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-24T00:00:00Z",
        commit="abc123",
        run_id="gha_agentic_integration_fallback",
        base_commit="abc122",
        head_commit="abc123",
        output_dir=str(tmp_path / "assist"),
        create_fix_pr=False,
        execution_mode="agentic_assist",
        llm_provider="local",
        llm_model="local-default",
        use_adk_runtime=False,
    )
    assist_state = run_pipeline(request=assist_request)

    assert assist_state.pipeline_status == "completed"
    assist_fix = assist_state.agent_outputs["fix_planner"]
    assert assist_fix["agentic_proposal"]["proposal_created"] is False
    assert (
        assist_fix["agentic_proposal"]["failure_reason_code"]
        == "AGENTIC_PROPOSAL_MAX_ATTEMPTS_EXCEEDED"
    )

    assert (
        assist_state.agent_outputs["failure_classification"]["classification"]
        == deterministic_state.agent_outputs["failure_classification"]["classification"]
    )
    assert assist_fix["fix_steps"] == deterministic_state.agent_outputs["fix_planner"]["fix_steps"]
