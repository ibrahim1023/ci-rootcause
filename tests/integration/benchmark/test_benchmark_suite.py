from __future__ import annotations

from pathlib import Path

import pytest

from src.benchmark.suite import run_benchmark_suite

SUITE_PATH = "fixtures/benchmarks/mvp-suite.json"


def test_run_benchmark_suite_executes_curated_cases(tmp_path: Path) -> None:
    result = run_benchmark_suite(
        suite_path=SUITE_PATH,
        output_root=str(tmp_path / "bench"),
        use_adk_runtime=False,
    )

    assert result["suite_name"] == "mvp-curated-v3"
    assert result["total_cases"] == 7
    assert result["completed_cases"] == 7
    assert result["completion_rate"] == 1.0
    assert result["classification_matches"] == 7
    assert result["classification_match_rate"] == 1.0
    assert result["baseline_classification_matches"] == 5
    assert result["baseline_classification_match_rate"] == 0.7143
    assert result["classification_match_lift"] == 0.2857
    assert "classification_confusion_matrix" in result
    assert result["classification_confusion_matrix"]["DEPENDENCY"]["DEPENDENCY"] == 2
    assert result["classification_confusion_matrix"]["INFRA"]["INFRA"] == 1
    assert result["classification_confusion_matrix"]["LINT"]["LINT"] == 1
    assert result["classification_confusion_matrix"]["TEST"]["TEST"] == 2
    assert result["classification_confusion_matrix"]["TYPECHECK"]["TYPECHECK"] == 1
    assert result["primary_root_cause_matches"] == 7
    assert result["primary_root_cause_accuracy"] == 1.0
    assert result["baseline_primary_root_cause_matches"] == 7
    assert result["baseline_primary_root_cause_accuracy"] == 1.0
    assert result["primary_root_cause_accuracy_lift"] == 0.0
    assert result["top1_root_cause_cases"] == 6
    assert result["top1_root_cause_matches"] == 6
    assert result["top1_root_cause_accuracy"] == 1.0
    assert result["confidence_reproducible_cases"] == 7
    assert result["confidence_reproducibility"] == 1.0
    assert result["artifact_hash_reproducible_cases"] == 7
    assert result["artifact_hash_reproducibility"] == 1.0
    assert result["mean_time_to_diagnosis_ms"] >= 0.0
    assert result["median_time_to_diagnosis_ms"] >= 0.0
    assert result["p95_time_to_diagnosis_ms"] >= 0.0

    case_ids = [item["case_id"] for item in result["cases"]]
    assert case_ids == sorted(case_ids)

    for item in result["cases"]:
        assert item["pipeline_status"] == "completed"
        assert item["classification"] == item["expected_classification"]
        assert item["baseline_classification"]
        assert isinstance(item["baseline_classification_match"], bool)
        assert item["primary_root_cause_title"]
        assert item["primary_root_cause_match"] is True
        assert item["baseline_primary_root_cause_title"]
        assert isinstance(item["baseline_primary_root_cause_match"], bool)
        assert item["expected_primary_root_cause_contains"] is not None
        assert "top1_root_cause_applicable" in item
        assert "top1_root_cause_match" in item
        assert item["confidence_is_reproducible"] is True
        assert len(item["confidence_values"]) == 2
        assert item["confidence_values"][0] == item["confidence_values"][1]
        assert len(item["status_values"]) == 2
        assert all(status == "completed" for status in item["status_values"])
        assert item["artifact_hash_is_reproducible"] is True
        assert len(item["artifact_json_hash_values"]) == 2
        assert len(item["artifact_md_hash_values"]) == 2
        assert item["timing_spread_ms"] >= 0.0
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
    assert first["confidence_reproducibility"] == second["confidence_reproducibility"] == 1.0
    assert first["top1_root_cause_accuracy"] == second["top1_root_cause_accuracy"] == 1.0


def test_run_benchmark_suite_rejects_non_positive_repeat_runs(tmp_path: Path) -> None:
    from src.benchmark.suite import BenchmarkSuiteError

    with pytest.raises(BenchmarkSuiteError, match="repeat_runs must be > 0"):
        run_benchmark_suite(
            suite_path=SUITE_PATH,
            output_root=str(tmp_path / "bench-invalid"),
            use_adk_runtime=False,
            repeat_runs=0,
        )
