from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from src.agents.agentic_proposer import AgenticProposalProviderError
from src.core.orchestration import (
    ADKRuntimeScaffold,
    AgentRegistration,
    CommitContext,
    DeterministicAgentRegistry,
    OrchestrationError,
    PipelineConfig,
    PipelineRequest,
    RepoContext,
    RunContext,
    _resolve_validated_changes_for_pr_creation,
    build_default_registry,
    resolve_pipeline_config,
    run_pipeline,
)


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


def test_default_registry_resolve_order_is_deterministic() -> None:
    first = build_default_registry().resolve_order()
    second = build_default_registry().resolve_order()

    assert first == second
    assert first == [
        "log_ingest",
        "diff_analysis",
        "failure_classification",
        "root_cause_ranker",
        "fix_planner",
        "reporter",
        "pr_creation",
    ]


def test_registry_detects_cycles() -> None:
    registry = DeterministicAgentRegistry()
    registry.register(
        AgentRegistration(
            name="a",
            depends_on=("b",),
            handler=lambda _: {},
        )
    )
    registry.register(
        AgentRegistration(
            name="b",
            depends_on=("a",),
            handler=lambda _: {},
        )
    )

    with pytest.raises(OrchestrationError, match="Cyclic or missing dependencies"):
        registry.resolve_order()


def test_adk_scaffold_manifest_is_stable() -> None:
    scaffold = ADKRuntimeScaffold(registry=build_default_registry())
    manifest = scaffold.manifest()

    assert [item["name"] for item in manifest] == [
        "log_ingest",
        "diff_analysis",
        "failure_classification",
        "root_cause_ranker",
        "fix_planner",
        "reporter",
        "pr_creation",
    ]
    assert scaffold.backend in {"google-adk", "google-adk-scaffold"}


def test_run_pipeline_wires_shared_context_and_outputs(tmp_path: Path) -> None:
    request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-20T00:00:00Z",
        commit="abc123",
        run_id="gha_2001",
        base_commit="abc123",
        head_commit="def456",
        output_dir=str(tmp_path),
        create_fix_pr=False,
    )

    result = run_pipeline(request=request)

    assert result.execution_order == build_default_registry().resolve_order()
    assert "root_cause_ranker" in result.shared
    assert "reporter" in result.agent_outputs
    assert result.agent_outputs["failure_classification"]["classification"] == "TEST"
    assert result.agent_outputs["pr_creation"]["pr_created"] is False
    assert result.agent_outputs["pr_creation"]["failure_reason"] == "create_fix_pr=false"
    assert result.pipeline_status == "completed"
    assert result.failures == []
    assert result.trace_id
    assert result.input_hashes["raw_log_sha256"]
    assert result.input_hashes["raw_diff_sha256"]
    assert result.input_hashes["historical_runs_sha256"]
    assert result.input_hashes["config_sha256"]
    assert result.pipeline_timing_ms >= 0.0
    assert "timing_metrics" in result.nondeterministic_components
    assert sorted(result.agent_timing_ms) == sorted(result.execution_order)
    assert all(duration >= 0.0 for duration in result.agent_timing_ms.values())
    assert result.structured_logs[0]["event"] == "pipeline_started"
    assert result.structured_logs[-1]["event"] == "pipeline_completed"
    assert "flaky_test_detection" in result.agent_outputs["failure_classification"]

    json_path = Path(result.agent_outputs["reporter"]["ci_rca_json_path"])
    md_path = Path(result.agent_outputs["reporter"]["ci_rca_md_path"])
    obs_path = tmp_path / "ci-rca-observability.json"
    assert json_path.exists()
    assert md_path.exists()
    assert obs_path.exists()
    obs_payload = json.loads(obs_path.read_text(encoding="utf-8"))
    assert obs_payload["trace_id"] == result.trace_id
    assert obs_payload["pipeline_status"] == "completed"
    assert obs_payload["failure_taxonomy"]["total_failures"] == 0
    assert obs_payload["agent_status_counts"]["completed"] == len(result.execution_order)


def test_run_pipeline_adk_mode_matches_local_outputs(tmp_path: Path) -> None:
    base_request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-20T00:00:00Z",
        commit="abc123",
        run_id="gha_2101",
        base_commit="abc123",
        head_commit="def456",
        output_dir=str(tmp_path / "local"),
        create_fix_pr=False,
    )

    local_result = run_pipeline(request=replace(base_request, use_adk_runtime=False))
    adk_result = run_pipeline(request=replace(base_request, output_dir=str(tmp_path / "adk")))

    assert local_result.pipeline_status == adk_result.pipeline_status == "completed"
    assert local_result.execution_order == adk_result.execution_order
    assert local_result.agent_status == adk_result.agent_status
    assert local_result.failures == adk_result.failures
    assert local_result.trace_id == adk_result.trace_id
    assert local_result.input_hashes == adk_result.input_hashes
    assert sorted(local_result.agent_timing_ms) == sorted(adk_result.agent_timing_ms)
    assert local_result.pipeline_timing_ms >= 0.0
    assert adk_result.pipeline_timing_ms >= 0.0
    assert local_result.nondeterministic_components == ["timing_metrics"]
    assert adk_result.nondeterministic_components == ["timing_metrics"]
    assert (
        local_result.agent_outputs["failure_classification"]["classification"]
        == adk_result.agent_outputs["failure_classification"]["classification"]
    )
    assert (
        local_result.agent_outputs["root_cause_ranker"]
        == adk_result.agent_outputs["root_cause_ranker"]
    )


def test_trace_id_and_structured_logs_are_deterministic(tmp_path: Path) -> None:
    request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-20T00:00:00Z",
        commit="abc123",
        run_id="gha_2111",
        base_commit="abc123",
        head_commit="def456",
        output_dir=str(tmp_path / "one"),
        create_fix_pr=False,
        use_adk_runtime=False,
    )

    first = run_pipeline(request=request)
    second = run_pipeline(request=replace(request, output_dir=str(tmp_path / "two")))

    assert first.trace_id == second.trace_id
    assert first.input_hashes == second.input_hashes
    assert [item["sequence"] for item in first.structured_logs] == list(
        range(1, len(first.structured_logs) + 1)
    )
    assert [item["event"] for item in first.structured_logs] == [
        item["event"] for item in second.structured_logs
    ]


def test_timing_metrics_are_recorded_for_partial_runs(tmp_path: Path) -> None:
    registry = DeterministicAgentRegistry()
    registry.register(AgentRegistration(name="ok", depends_on=(), handler=lambda _: {"ok": True}))

    def _crash(_: object) -> dict:
        raise ValueError("boom")

    registry.register(AgentRegistration(name="crash", depends_on=("ok",), handler=_crash))
    registry.register(
        AgentRegistration(
            name="after_crash", depends_on=("crash",), handler=lambda _: {"should_not_run": True}
        )
    )

    request = PipelineRequest(
        raw_log="",
        raw_diff="",
        timestamp="2026-02-20T00:00:00Z",
        commit="abc123",
        run_id="gha_3111",
        base_commit="abc123",
        head_commit="def456",
        output_dir=str(tmp_path),
        fail_fast=False,
        use_adk_runtime=False,
    )
    result = run_pipeline(request=request, registry=registry)

    assert result.pipeline_status == "partial"
    assert result.pipeline_timing_ms >= 0.0
    assert sorted(result.agent_timing_ms) == ["after_crash", "crash", "ok"]
    assert all(duration >= 0.0 for duration in result.agent_timing_ms.values())
    observability = json.loads((tmp_path / "ci-rca-observability.json").read_text(encoding="utf-8"))
    assert observability["failure_taxonomy"]["total_failures"] == 1
    assert observability["failure_taxonomy"]["by_agent"]["crash"] == 1
    assert observability["failure_taxonomy"]["by_error_type"]["ValueError"] == 1


def test_run_pipeline_returns_partial_results_when_fail_fast_is_disabled() -> None:
    registry = DeterministicAgentRegistry()
    registry.register(
        AgentRegistration(
            name="first",
            depends_on=(),
            handler=lambda _: {"ok": True},
        )
    )

    def _crash_handler(_: object) -> dict:
        raise ValueError("boom")

    registry.register(
        AgentRegistration(
            name="crash",
            depends_on=("first",),
            handler=_crash_handler,
        )
    )
    registry.register(
        AgentRegistration(
            name="after_crash",
            depends_on=("crash",),
            handler=lambda _: {"should_not_run": True},
        )
    )
    registry.register(
        AgentRegistration(
            name="independent",
            depends_on=(),
            handler=lambda _: {"independent": True},
        )
    )

    request = PipelineRequest(
        raw_log="",
        raw_diff="",
        timestamp="2026-02-20T00:00:00Z",
        commit="abc123",
        run_id="gha_3001",
        base_commit="abc123",
        head_commit="def456",
        output_dir=".",
        fail_fast=False,
    )

    result = run_pipeline(request=request, registry=registry)

    assert result.pipeline_status == "partial"
    assert result.agent_status["first"] == "completed"
    assert result.agent_status["crash"] == "failed"
    assert result.agent_status["after_crash"] == "skipped"


def test_run_pipeline_agentic_assist_uses_proposal_and_filters_to_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    def _fake_propose(self, payload: dict) -> dict:  # noqa: ANN001
        del self, payload
        return {
            "summary": "agentic suggestion",
            "candidate_fix_steps": [
                {
                    "file": "src/app.py",
                    "instruction": "Update assertion behavior",
                    "rationale": "Aligned with CI evidence",
                },
                {
                    "file": "src/other.py",
                    "instruction": "Unrelated speculative change",
                    "rationale": "Should be filtered",
                },
            ],
            "patch_plan": [
                {"op": "modify", "file": "src/app.py", "content": "value = 1\n"},
                {"op": "modify", "file": "src/other.py", "content": "value = 2\n"},
            ],
        }

    monkeypatch.setattr("src.core.orchestration.LocalLlmPatchProposer.propose", _fake_propose)

    request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-20T00:00:00Z",
        commit="abc123",
        run_id="gha_4101",
        base_commit="abc123",
        head_commit="def456",
        output_dir=str(tmp_path),
        create_fix_pr=False,
        execution_mode="agentic_assist",
        llm_provider="local",
        llm_model="local-default",
        use_adk_runtime=False,
    )
    result = run_pipeline(request=request)

    assert result.pipeline_status == "completed"
    fix_output = result.agent_outputs["fix_planner"]
    assert fix_output["agentic_proposal"]["proposal_created"] is True
    assert all(step["file"] == "src/app.py" for step in fix_output["fix_steps"])


def test_run_pipeline_agentic_assist_falls_back_when_provider_fails(
    tmp_path: Path, monkeypatch
) -> None:
    def _raise_provider(self, payload: dict) -> dict:  # noqa: ANN001
        del self, payload
        raise AgenticProposalProviderError("provider unavailable")

    monkeypatch.setattr("src.core.orchestration.LocalLlmPatchProposer.propose", _raise_provider)

    request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-20T00:00:00Z",
        commit="abc123",
        run_id="gha_4102",
        base_commit="abc123",
        head_commit="def456",
        output_dir=str(tmp_path),
        create_fix_pr=False,
        execution_mode="agentic_assist",
        llm_provider="local",
        llm_model="local-default",
        use_adk_runtime=False,
    )
    result = run_pipeline(request=request)

    assert result.pipeline_status == "completed"
    fix_output = result.agent_outputs["fix_planner"]
    assert fix_output["agentic_proposal"]["proposal_created"] is False
    assert (
        fix_output["agentic_proposal"]["failure_reason_code"]
        == "AGENTIC_PROPOSAL_MAX_ATTEMPTS_EXCEEDED"
    )


def test_run_pipeline_agentic_assist_falls_back_when_proposal_path_is_unsafe(
    tmp_path: Path, monkeypatch
) -> None:
    def _unsafe(self, payload: dict) -> dict:  # noqa: ANN001
        del self, payload
        return {
            "summary": "unsafe",
            "candidate_fix_steps": [
                {
                    "file": "../escape.py",
                    "instruction": "unsafe change",
                    "rationale": "should be rejected",
                }
            ],
            "patch_plan": [{"op": "modify", "file": "../escape.py", "content": "x"}],
        }

    monkeypatch.setattr("src.core.orchestration.LocalLlmPatchProposer.propose", _unsafe)

    request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-20T00:00:00Z",
        commit="abc123",
        run_id="gha_4103",
        base_commit="abc123",
        head_commit="def456",
        output_dir=str(tmp_path),
        create_fix_pr=False,
        execution_mode="agentic_assist",
        llm_provider="local",
        llm_model="local-default",
        use_adk_runtime=False,
    )
    result = run_pipeline(request=request)

    assert result.pipeline_status == "completed"
    fix_output = result.agent_outputs["fix_planner"]
    assert fix_output["agentic_proposal"]["proposal_created"] is False
    assert (
        fix_output["agentic_proposal"]["failure_reason_code"]
        == "AGENTIC_PROPOSAL_MAX_ATTEMPTS_EXCEEDED"
    )


def test_observability_includes_agentic_attempt_metadata(tmp_path: Path, monkeypatch) -> None:
    def _raise_provider(self, payload: dict) -> dict:  # noqa: ANN001
        del self, payload
        raise AgenticProposalProviderError(
            "provider HTTP error 401 for "
            "https://example.invalid/generate?key=secret-token: Bearer secret-token"
        )

    monkeypatch.setattr("src.core.orchestration.LocalLlmPatchProposer.propose", _raise_provider)

    request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-20T00:00:00Z",
        commit="abc123",
        run_id="gha_4104",
        base_commit="abc123",
        head_commit="def456",
        output_dir=str(tmp_path),
        create_fix_pr=False,
        execution_mode="agentic_assist",
        llm_provider="local",
        llm_model="local-default",
        use_adk_runtime=False,
    )
    run_pipeline(request=request)

    observability = json.loads((tmp_path / "ci-rca-observability.json").read_text(encoding="utf-8"))
    assert observability["agentic"]["provider"] == "local"
    assert observability["agentic"]["model"] == "local-default"
    assert observability["agentic"]["proposal_created"] is False
    assert (
        observability["agentic"]["failure_reason_code"] == "AGENTIC_PROPOSAL_MAX_ATTEMPTS_EXCEEDED"
    )
    assert observability["agentic"]["attempt_count"] > 0
    assert observability["agentic"]["attempt_summaries"]
    serialized_agentic = json.dumps(observability["agentic"], sort_keys=True)
    assert "secret-token" not in serialized_agentic
    assert "key=<redacted>" in serialized_agentic
    assert "Bearer <redacted>" in serialized_agentic
    assert observability["agentic"]["pr_failure_reason_code"] == "CREATE_FIX_PR_DISABLED"


def test_observability_artifact_failure_does_not_fail_pipeline(tmp_path: Path) -> None:
    blocked_output = tmp_path / "occupied-path"
    blocked_output.write_text("not-a-directory", encoding="utf-8")

    registry = DeterministicAgentRegistry()
    registry.register(AgentRegistration(name="only", depends_on=(), handler=lambda _: {"ok": True}))

    request = PipelineRequest(
        raw_log="",
        raw_diff="",
        timestamp="2026-02-23T00:00:00Z",
        commit="abc123",
        run_id="gha_obs_fail_1",
        base_commit="abc122",
        head_commit="abc123",
        output_dir=str(blocked_output),
        fail_fast=False,
        use_adk_runtime=False,
    )

    result = run_pipeline(request=request, registry=registry)

    assert result.pipeline_status == "completed"
    assert any(log["event"] == "observability_write_failed" for log in result.structured_logs)


def test_run_pipeline_fail_fast_raises_orchestration_error() -> None:
    registry = DeterministicAgentRegistry()
    registry.register(
        AgentRegistration(
            name="crash",
            depends_on=(),
            handler=lambda _: (_ for _ in ()).throw(ValueError("boom-fast")),
        )
    )

    request = PipelineRequest(
        raw_log="",
        raw_diff="",
        timestamp="2026-02-20T00:00:00Z",
        commit="abc123",
        run_id="gha_3002",
        base_commit="abc123",
        head_commit="def456",
        output_dir=".",
        fail_fast=True,
    )

    with pytest.raises(OrchestrationError, match="Pipeline failed in agent 'crash'"):
        run_pipeline(request=request, registry=registry)


def test_resolve_pipeline_config_from_legacy_request_fields() -> None:
    request = PipelineRequest(
        raw_log="",
        raw_diff="",
        timestamp="2026-02-20T09:00:00Z",
        commit="abc123",
        run_id="gha_4001",
        base_commit="abc122",
        head_commit="abc123",
        output_dir=".",
        repository="acme/ci-rootcause",
        target_branch="main",
    )

    config = resolve_pipeline_config(request)

    assert config.ci_provider == "github-actions"
    assert config.provider_adapter == "github"
    assert config.repo.repository == "acme/ci-rootcause"
    assert config.commit.commit == "abc123"
    assert config.run.run_id == "gha_4001"
    assert config.run.timestamp == "2026-02-20T09:00:00Z"


def test_run_pipeline_uses_explicit_pipeline_config(tmp_path: Path) -> None:
    config = PipelineConfig(
        ci_provider="github-actions",
        provider_adapter="github",
        repo=RepoContext(repository="acme/ci-rootcause", target_branch="develop"),
        commit=CommitContext(commit="abc123", base_commit="abc122", head_commit="abc123"),
        run=RunContext(run_id="gha_4002", timestamp="2026-02-20T10:00:00Z", job_id="job_17"),
    )
    request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="1970-01-01T00:00:00Z",
        commit="legacy-unused",
        run_id="legacy-unused",
        base_commit="legacy-unused",
        head_commit="legacy-unused",
        output_dir=str(tmp_path),
        create_fix_pr=False,
        config=config,
    )

    result = run_pipeline(request=request)

    assert result.config == config
    assert result.agent_outputs["reporter"]["ci_rca_payload"]["meta"]["run_id"] == "gha_4002"
    assert result.agent_outputs["reporter"]["ci_rca_payload"]["meta"]["commit"] == "abc123"


def test_run_pipeline_honors_offline_only_mode_for_pr_creation(tmp_path: Path) -> None:
    request = PipelineRequest(
        raw_log=_sample_log(),
        raw_diff=_sample_diff(),
        timestamp="2026-02-24T00:00:00Z",
        commit="abc123",
        run_id="gha_offline_1",
        base_commit="abc122",
        head_commit="abc123",
        output_dir=str(tmp_path),
        create_fix_pr=True,
        offline_only=True,
        use_adk_runtime=False,
    )

    result = run_pipeline(request=request)

    assert result.pipeline_status == "completed"
    assert result.agent_outputs["pr_creation"]["pr_created"] is False
    assert result.agent_outputs["pr_creation"]["failure_reason"] == "offline_only=true"


def test_pr_creation_prefers_request_validated_changes_over_synthesis() -> None:
    explicit = [{"file": "src/core/math.py", "content": "explicit\n"}]
    resolved = _resolve_validated_changes_for_pr_creation(
        request_validated_changes=explicit,
        classification="TYPECHECK",
        primary_root_cause={
            "evidence": [{"file": "src/core/math.py", "line": 3}],
        },
        fix_output={"fix_steps": [{"file": "src/core/math.py"}]},
    )

    assert resolved == explicit


def test_pr_creation_uses_agentic_patch_plan_as_validated_changes() -> None:
    resolved = _resolve_validated_changes_for_pr_creation(
        request_validated_changes=[],
        classification="TYPECHECK",
        primary_root_cause={
            "evidence": [{"file": "app_failure_typecheck.py", "line": 4}],
        },
        fix_output={
            "fix_steps": [{"file": "app_failure_typecheck.py"}],
            "agentic_proposal": {
                "patch_plan": [
                    {
                        "op": "modify",
                        "file": "app_failure_typecheck.py",
                        "content": "result: int = needs_int(7)\n",
                    }
                ]
            },
        },
    )

    assert resolved == [
        {
            "file": "app_failure_typecheck.py",
            "content": "result: int = needs_int(7)\n",
        }
    ]


def test_pr_creation_ignores_typecheck_proposal_that_suppresses_errors(tmp_path: Path) -> None:
    target = tmp_path / "app_failure_typecheck.py"
    target.write_text(
        'def needs_int(value: int) -> int:\n    return value\n\nresult: int = needs_int("7")\n',
        encoding="utf-8",
    )

    current = Path.cwd()
    try:
        os.chdir(tmp_path)
        resolved = _resolve_validated_changes_for_pr_creation(
            request_validated_changes=[],
            classification="TYPECHECK",
            primary_root_cause={
                "evidence": [{"file": "app_failure_typecheck.py", "line": 4}],
            },
            fix_output={
                "fix_steps": [{"file": "app_failure_typecheck.py"}],
                "agentic_proposal": {
                    "patch_plan": [
                        {
                            "op": "modify",
                            "file": "app_failure_typecheck.py",
                            "content": (
                                "def needs_int(value: int) -> int:\n    return value\n\n"
                                'result: int = needs_int("7")  # type: ignore[assignment]\n'
                            ),
                        }
                    ]
                },
            },
        )
    finally:
        os.chdir(current)

    assert len(resolved) == 1
    assert resolved[0]["file"] == "app_failure_typecheck.py"
    assert "needs_int(7)" in resolved[0]["content"]
    assert "type: ignore" not in resolved[0]["content"]


def test_pr_creation_ignores_unsupported_agentic_patch_plan_ops() -> None:
    resolved = _resolve_validated_changes_for_pr_creation(
        request_validated_changes=[],
        classification="TYPECHECK",
        primary_root_cause={
            "evidence": [{"file": "app_failure_typecheck.py", "line": 4}],
        },
        fix_output={
            "fix_steps": [{"file": "app_failure_typecheck.py"}],
            "agentic_proposal": {
                "patch_plan": [
                    {
                        "op": "delete",
                        "file": "app_failure_typecheck.py",
                        "content": "",
                    }
                ]
            },
        },
    )

    assert resolved == []


def test_pr_creation_synthesizes_typecheck_validated_changes(tmp_path: Path) -> None:
    target = tmp_path / "src" / "core" / "math.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def calc(x: int) -> str:\n    return x\n", encoding="utf-8")

    current = Path.cwd()
    try:
        os.chdir(tmp_path)
        resolved = _resolve_validated_changes_for_pr_creation(
            request_validated_changes=[],
            classification="TYPECHECK",
            primary_root_cause={
                "evidence": [{"file": "src/core/math.py", "line": 2}],
            },
            fix_output={"fix_steps": [{"file": "src/core/math.py"}]},
        )
    finally:
        os.chdir(current)

    assert len(resolved) == 1
    assert resolved[0]["file"] == "src/core/math.py"
    assert "type: ignore[assignment]" in resolved[0]["content"]


def test_pr_creation_synthesizes_semantic_int_literal_fix_when_safe(tmp_path: Path) -> None:
    target = tmp_path / "typecheck_target.py"
    target.write_text(
        'def sentinel_value() -> int:\n    value: int = "7"\n    return value\n',
        encoding="utf-8",
    )

    current = Path.cwd()
    try:
        os.chdir(tmp_path)
        resolved = _resolve_validated_changes_for_pr_creation(
            request_validated_changes=[],
            classification="TYPECHECK",
            primary_root_cause={
                "evidence": [{"file": "typecheck_target.py", "line": 2}],
            },
            fix_output={"fix_steps": [{"file": "typecheck_target.py"}]},
        )
    finally:
        os.chdir(current)

    assert len(resolved) == 1
    assert resolved[0]["file"] == "typecheck_target.py"
    assert "value: int = 7" in resolved[0]["content"]
    assert "type: ignore[assignment]" not in resolved[0]["content"]


def test_pr_creation_synthesizes_semantic_int_call_arg_fix_when_safe(tmp_path: Path) -> None:
    target = tmp_path / "app_failure_typecheck.py"
    target.write_text(
        'def needs_int(value: int) -> int:\n    return value\n\nresult: int = needs_int("7")\n',
        encoding="utf-8",
    )

    current = Path.cwd()
    try:
        os.chdir(tmp_path)
        resolved = _resolve_validated_changes_for_pr_creation(
            request_validated_changes=[],
            classification="TYPECHECK",
            primary_root_cause={
                "evidence": [{"file": "app_failure_typecheck.py", "line": 4}],
            },
            fix_output={"fix_steps": [{"file": "app_failure_typecheck.py"}]},
        )
    finally:
        os.chdir(current)

    assert len(resolved) == 1
    assert resolved[0]["file"] == "app_failure_typecheck.py"
    assert "needs_int(7)" in resolved[0]["content"]
    assert "type: ignore" not in resolved[0]["content"]


def test_pr_creation_does_not_synthesize_for_non_typecheck() -> None:
    resolved = _resolve_validated_changes_for_pr_creation(
        request_validated_changes=[],
        classification="TEST",
        primary_root_cause={
            "evidence": [{"file": "src/core/math.py", "line": 3}],
        },
        fix_output={"fix_steps": [{"file": "src/core/math.py"}]},
    )

    assert resolved == []


def test_resolve_pipeline_config_detects_gitlab_ci_environment(monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_CI", "true")
    monkeypatch.setenv("CI_PROJECT_PATH", "acme/ci-rootcause")
    monkeypatch.setenv("CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "develop")

    request = PipelineRequest(
        raw_log="",
        raw_diff="",
        timestamp="2026-02-22T12:00:00Z",
        commit="abc123",
        run_id="gl_4003",
        base_commit="abc122",
        head_commit="abc123",
        output_dir=".",
        repository=None,
        target_branch=None,
    )

    config = resolve_pipeline_config(request)

    assert config.ci_provider == "gitlab-ci"
    assert config.provider_adapter == "gitlab"
    assert config.repo.repository == "acme/ci-rootcause"
    assert config.repo.target_branch == "develop"


def test_resolve_pipeline_config_request_overrides_detected_provider(monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_CI", "true")
    monkeypatch.setenv("CI_PROJECT_PATH", "acme/gitlab-repo")

    request = PipelineRequest(
        raw_log="",
        raw_diff="",
        timestamp="2026-02-22T12:00:00Z",
        commit="abc123",
        run_id="custom_4004",
        base_commit="abc122",
        head_commit="abc123",
        output_dir=".",
        ci_provider="custom-ci",
        provider_adapter="custom",
        repository="acme/custom-repo",
        target_branch="release",
    )

    config = resolve_pipeline_config(request)

    assert config.ci_provider == "custom-ci"
    assert config.provider_adapter == "custom"
    assert config.repo.repository == "acme/custom-repo"
    assert config.repo.target_branch == "release"
