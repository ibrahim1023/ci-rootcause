from __future__ import annotations

from pathlib import Path

import pytest

from src.benchmark.suite import BenchmarkSuiteError, load_benchmark_suite

SUITE_PATH = "fixtures/benchmarks/mvp-suite.json"


def test_load_benchmark_suite_returns_sorted_cases() -> None:
    suite_name, cases = load_benchmark_suite(SUITE_PATH)

    assert suite_name == "mvp-curated-v3"
    assert len(cases) == 9
    assert [case.case_id for case in cases] == sorted(case.case_id for case in cases)
    assert {case.expected_classification for case in cases} == {
        "DEPENDENCY",
        "LINT",
        "TEST",
        "TYPECHECK",
        "INFRA",
    }
    typecheck_case = next(case for case in cases if case.case_id == "case-typecheck-ts2345")
    assert typecheck_case.expected_primary_root_cause_file == "src/app.ts"
    assert typecheck_case.expected_primary_root_cause_line == 14
    agentic_case = next(case for case in cases if case.case_id == "case-agentic-ruff-pass")
    assert agentic_case.execution_mode == "agentic_assist"
    assert agentic_case.create_fix_pr is True
    assert agentic_case.dry_run is True
    assert agentic_case.llm_provider == "local"


def test_load_benchmark_suite_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    suite = tmp_path / "dup.json"
    suite.write_text(
        """
        {
          "suite_name": "dup",
          "cases": [
            {"case_id":"same","description":"a","log_path":"a","diff_path":"b","timestamp":"t","commit":"c","run_id":"r1","base_commit":"b","head_commit":"h"},
            {"case_id":"same","description":"b","log_path":"a","diff_path":"b","timestamp":"t","commit":"c","run_id":"r2","base_commit":"b","head_commit":"h"}
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkSuiteError, match="Duplicate benchmark case_id"):
        load_benchmark_suite(str(suite))
