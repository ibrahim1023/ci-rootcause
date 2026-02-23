from __future__ import annotations

from pathlib import Path

from src.core.orchestration import PipelineRequest, run_pipeline


def _run_fixture_pipeline(log_path: str, output_dir: Path, run_id: str):
    request = PipelineRequest(
        raw_log=Path(log_path).read_text(encoding="utf-8"),
        raw_diff=Path("fixtures/diffs/refactor-only.diff").read_text(encoding="utf-8"),
        timestamp="2026-02-23T00:00:00Z",
        commit="abc123",
        run_id=run_id,
        base_commit="abc122",
        head_commit="abc123",
        output_dir=str(output_dir),
        create_fix_pr=False,
        use_adk_runtime=False,
    )
    return run_pipeline(request=request)


def test_pipeline_handles_matrix_mixed_fixture(tmp_path: Path) -> None:
    state = _run_fixture_pipeline(
        "fixtures/ci-logs/github-actions-matrix-mixed-failure.log",
        tmp_path / "matrix",
        "gha_matrix_fixture",
    )

    assert state.pipeline_status == "completed"
    assert state.agent_outputs["failure_classification"]["classification"] == "TYPECHECK"
    assert state.agent_outputs["log_ingest"]["first_failure_event"] is not None


def test_pipeline_handles_cancelled_partial_fixture(tmp_path: Path) -> None:
    state = _run_fixture_pipeline(
        "fixtures/ci-logs/github-actions-cancelled-partial.log",
        tmp_path / "cancelled",
        "gha_cancelled_fixture",
    )

    assert state.pipeline_status == "completed"
    assert state.agent_outputs["failure_classification"]["classification"] == "INFRA"
    assert state.agent_outputs["log_ingest"]["first_failure_event"] is not None
