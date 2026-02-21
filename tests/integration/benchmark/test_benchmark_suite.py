from __future__ import annotations

from pathlib import Path

from src.benchmark.suite import run_benchmark_suite

SUITE_PATH = "fixtures/benchmarks/mvp-suite.json"


def test_run_benchmark_suite_executes_curated_cases(tmp_path: Path) -> None:
    result = run_benchmark_suite(
        suite_path=SUITE_PATH,
        output_root=str(tmp_path / "bench"),
        use_adk_runtime=False,
    )

    assert result["suite_name"] == "mvp-curated-v1"
    assert result["total_cases"] == 4
    assert result["completed_cases"] == 4
    assert result["classification_matches"] == 4
    assert result["primary_root_cause_matches"] == 4
    assert result["primary_root_cause_accuracy"] == 1.0

    case_ids = [item["case_id"] for item in result["cases"]]
    assert case_ids == sorted(case_ids)

    for item in result["cases"]:
        assert item["pipeline_status"] == "completed"
        assert item["classification"] == item["expected_classification"]
        assert item["primary_root_cause_title"]
        assert item["primary_root_cause_match"] is True
        assert item["expected_primary_root_cause_contains"] == "AssertionError"
        assert len(item["trace_id"]) == 24
        assert item["pipeline_timing_ms"] >= 0.0
        assert len(item["ci_rca_json_sha256"]) == 64
        assert len(item["ci_rca_md_sha256"]) == 64


def test_run_benchmark_suite_is_repeatable_for_same_inputs(tmp_path: Path) -> None:
    first = run_benchmark_suite(
        suite_path=SUITE_PATH,
        output_root=str(tmp_path / "bench1"),
        use_adk_runtime=False,
    )
    second = run_benchmark_suite(
        suite_path=SUITE_PATH,
        output_root=str(tmp_path / "bench2"),
        use_adk_runtime=False,
    )

    assert [item["case_id"] for item in first["cases"]] == [
        item["case_id"] for item in second["cases"]
    ]
    assert [item["classification"] for item in first["cases"]] == [
        item["classification"] for item in second["cases"]
    ]
    assert [item["primary_root_cause_title"] for item in first["cases"]] == [
        item["primary_root_cause_title"] for item in second["cases"]
    ]
