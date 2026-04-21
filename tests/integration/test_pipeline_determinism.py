from __future__ import annotations

import hashlib
from pathlib import Path

from src.core.orchestration import PipelineRequest, run_pipeline

LOG_FIXTURE = Path("fixtures/ci-logs/github-actions-python-failure.log")
DIFF_FIXTURES = [
    Path("fixtures/diffs/refactor-only.diff"),
    Path("fixtures/diffs/rename-and-modify.diff"),
    Path("fixtures/diffs/python-lockfile-only.diff"),
    Path("fixtures/diffs/node-mixed-code-lock.diff"),
]
REFRACTOR_ONLY_FIXED_HASHES = {
    "ci_rca_json_sha256": "92462dd31f9569404ce733514126b632312959522ad37fa0b1c78ff828d2150f",
    "ci_rca_md_sha256": "a9123fe3a2736070c0b9387b56ebc4ba06d8fd42e3d9323eb32ba55384c2fb46",
}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_case(tmp_path: Path, *, diff_fixture: Path, case_id: str) -> dict[str, str]:
    output_dir = tmp_path / case_id
    request = PipelineRequest(
        raw_log=LOG_FIXTURE.read_text(encoding="utf-8"),
        raw_diff=diff_fixture.read_text(encoding="utf-8"),
        timestamp="2026-02-21T00:00:00Z",
        commit="abc123",
        run_id=f"gha_determinism_{diff_fixture.stem}",
        base_commit="abc122",
        head_commit="abc123",
        output_dir=str(output_dir),
        create_fix_pr=False,
    )
    result = run_pipeline(request=request)
    reporter = result.agent_outputs["reporter"]
    ranker = result.agent_outputs["root_cause_ranker"]
    classification = result.agent_outputs["failure_classification"]

    json_path = Path(reporter["ci_rca_json_path"])
    md_path = Path(reporter["ci_rca_md_path"])

    return {
        "pipeline_status": result.pipeline_status,
        "classification": classification["classification"],
        "confidence": f"{float(ranker['confidence']):.4f}",
        "primary_root_cause_title": str(ranker["primary_root_cause"]["title"]),
        "ci_rca_json_sha256": _file_sha256(json_path),
        "ci_rca_md_sha256": _file_sha256(md_path),
    }


def test_pipeline_executes_on_curated_fixtures(tmp_path: Path) -> None:
    for fixture in DIFF_FIXTURES:
        result = _run_case(
            tmp_path=tmp_path,
            diff_fixture=fixture,
            case_id=f"{fixture.stem}-single",
        )

        assert result["pipeline_status"] == "completed"
        assert result["classification"] in {
            "INFRA",
            "DEPENDENCY",
            "BUILD",
            "TEST",
            "LINT",
            "TYPECHECK",
            "SECURITY",
            "UNKNOWN",
        }
        assert result["primary_root_cause_title"]
        assert len(result["ci_rca_json_sha256"]) == 64
        assert len(result["ci_rca_md_sha256"]) == 64


def test_pipeline_output_hashes_are_deterministic_across_repeat_runs(tmp_path: Path) -> None:
    for fixture in DIFF_FIXTURES:
        first = _run_case(
            tmp_path=tmp_path,
            diff_fixture=fixture,
            case_id=f"{fixture.stem}-run1",
        )
        second = _run_case(
            tmp_path=tmp_path,
            diff_fixture=fixture,
            case_id=f"{fixture.stem}-run2",
        )

        assert first == second


def test_pipeline_output_hashes_match_fixed_refactor_only_baseline(tmp_path: Path) -> None:
    result = _run_case(
        tmp_path=tmp_path,
        diff_fixture=Path("fixtures/diffs/refactor-only.diff"),
        case_id="refactor-only-fixed-baseline",
    )

    assert result["ci_rca_json_sha256"] == REFRACTOR_ONLY_FIXED_HASHES["ci_rca_json_sha256"]
    assert result["ci_rca_md_sha256"] == REFRACTOR_ONLY_FIXED_HASHES["ci_rca_md_sha256"]
