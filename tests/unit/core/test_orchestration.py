from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

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

    json_path = Path(result.agent_outputs["reporter"]["ci_rca_json_path"])
    md_path = Path(result.agent_outputs["reporter"]["ci_rca_md_path"])
    assert json_path.exists()
    assert md_path.exists()


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
    adk_result = run_pipeline(
        request=replace(base_request, run_id="gha_2102", output_dir=str(tmp_path / "adk"))
    )

    assert local_result.pipeline_status == adk_result.pipeline_status == "completed"
    assert local_result.execution_order == adk_result.execution_order
    assert local_result.agent_status == adk_result.agent_status
    assert local_result.failures == adk_result.failures
    assert (
        local_result.agent_outputs["failure_classification"]["classification"]
        == adk_result.agent_outputs["failure_classification"]["classification"]
    )
    assert local_result.agent_outputs["root_cause_ranker"] == adk_result.agent_outputs[
        "root_cause_ranker"
    ]


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
    assert result.agent_status["independent"] == "completed"
    assert result.failures == [
        {
            "agent": "crash",
            "error_type": "ValueError",
            "message": "boom",
        }
    ]
    assert result.agent_outputs["after_crash"] == {
        "status": "skipped",
        "reason": "dependency_failed",
        "blocked_by": ["crash"],
    }


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
