from src.agents.root_cause_ranker import run_root_cause_ranker


def _base_failure_graph() -> dict:
    return {
        "nodes": [
            {
                "stage": "test",
                "timestamp": "2026-02-19T10:00:00Z",
                "file": "src/core/math.py",
                "line": 42,
                "error_signature": "AssertionError: assert 3 == 4",
                "stack_frames": ["src/core/math.py:42"],
                "log_excerpt": "assert 3 == 4",
                "is_first_failure": True,
            },
            {
                "stage": "test",
                "timestamp": "2026-02-19T10:00:05Z",
                "file": "src/other.py",
                "line": 5,
                "error_signature": "AssertionError: follow-up",
                "stack_frames": ["src/other.py:5"],
                "log_excerpt": "follow-up fail",
                "is_first_failure": False,
            },
        ]
    }


def test_ranker_generates_candidates_and_evidence() -> None:
    result = run_root_cause_ranker(
        failure_graph=_base_failure_graph(),
        changed_files=["src/core/math.py"],
        changed_modules=["math"],
        dependency_change_flags={"has_lockfile_change": False, "has_manifest_change": False},
        classification="TEST",
    )

    assert len(result["ranked_causes"]) == 2
    assert result["ranked_causes"][0]["evidence"][0]["file"] == "src/core/math.py"


def test_ranker_applies_scoring_formula_deterministically() -> None:
    result = run_root_cause_ranker(
        failure_graph=_base_failure_graph(),
        changed_files=["src/core/math.py"],
        changed_modules=["math"],
        dependency_change_flags={"has_lockfile_change": False, "has_manifest_change": False},
        classification="TEST",
    )

    top = result["ranked_causes"][0]
    breakdown = top["score_breakdown"]
    expected = round(
        (0.30 * breakdown["first_failure_score"])
        + (0.25 * breakdown["diff_proximity_score"])
        + (0.10 * breakdown["module_proximity_score"])
        + (0.10 * breakdown["dependency_drift_score"])
        + (0.10 * breakdown["classification_alignment_score"])
        + (0.15 * breakdown["evidence_quality_score"]),
        4,
    )

    assert top["score"] == expected
    assert result["confidence"] == expected
    assert "file_and_line_evidence" in top["confidence_reasons"]


def test_ranker_uses_tie_break_order() -> None:
    graph = {
        "nodes": [
            {
                "stage": "test",
                "timestamp": "2026-02-19T10:00:01Z",
                "file": "src/a.py",
                "line": 10,
                "error_signature": "UnknownError",
                "stack_frames": [],
                "log_excerpt": "x",
                "is_first_failure": False,
            },
            {
                "stage": "test",
                "timestamp": "2026-02-19T10:00:00Z",
                "file": "src/b.py",
                "line": 10,
                "error_signature": "UnknownError",
                "stack_frames": [],
                "log_excerpt": "x",
                "is_first_failure": False,
            },
        ]
    }

    result = run_root_cause_ranker(
        failure_graph=graph,
        changed_files=[],
        changed_modules=[],
        dependency_change_flags={"has_lockfile_change": False, "has_manifest_change": False},
        classification="UNKNOWN",
    )

    assert "src/b.py" in result["ranked_causes"][0]["title"]


def test_ranker_integration_prefers_first_failure_in_changed_file() -> None:
    graph = _base_failure_graph()
    result = run_root_cause_ranker(
        failure_graph=graph,
        changed_files=["src/core/math.py", "src/other.py"],
        changed_modules=["math", "other"],
        dependency_change_flags={"has_lockfile_change": True, "has_manifest_change": True},
        classification="TEST",
    )

    assert "src/core/math.py" in result["primary_root_cause"]["title"]
    assert result["primary_root_cause"]["score"] >= result["ranked_causes"][1]["score"]


def test_ranker_penalizes_generic_ci_wrapper_candidates() -> None:
    graph = {
        "nodes": [
            {
                "stage": "test",
                "timestamp": "2026-02-19T10:00:00Z",
                "file": None,
                "line": None,
                "error_signature": "##[error]Process completed with exit code 1.",
                "stack_frames": [],
                "log_excerpt": "##[error]Process completed with exit code 1.",
                "is_first_failure": True,
            },
            {
                "stage": "test",
                "timestamp": "2026-02-19T10:00:01Z",
                "file": "app_failure_typecheck.py",
                "line": 4,
                "error_signature": (
                    "app_failure_typecheck.py:4: error: Argument 1 has "
                    'incompatible type "str"; expected "int" [arg-type]'
                ),
                "stack_frames": ["app_failure_typecheck.py:4"],
                "log_excerpt": "app_failure_typecheck.py:4: error: Argument 1",
                "is_first_failure": False,
            },
        ]
    }

    result = run_root_cause_ranker(
        failure_graph=graph,
        changed_files=[],
        changed_modules=[],
        dependency_change_flags={"has_lockfile_change": False, "has_manifest_change": False},
        classification="TYPECHECK",
    )

    primary = result["primary_root_cause"]
    assert "app_failure_typecheck.py" in primary["title"]
    assert "file_and_line_evidence" in primary["confidence_reasons"]
