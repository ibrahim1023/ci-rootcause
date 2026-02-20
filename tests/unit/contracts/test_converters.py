from src.contracts.converters import (
    failure_graph_from_log_ingest,
    pr_result_from_agent_output,
    rca_output_from_agent_outputs,
)


def test_failure_graph_converter() -> None:
    payload = {
        "failure_graph": [
            {
                "stage": "test",
                "timestamp": "2026-02-19T12:00:00Z",
                "error_signature": "AssertionError",
                "file": "tests/test_app.py",
                "line": 22,
                "stack_frames": ["tests/test_app.py:22"],
                "log_excerpt": "assert a == b",
                "is_first_failure": True,
            }
        ]
    }

    graph = failure_graph_from_log_ingest(payload)
    assert len(graph.nodes) == 1
    assert graph.nodes[0].is_first_failure is True


def test_rca_output_converter() -> None:
    payload = {
        "summary": "Typecheck failure",
        "classification": "TYPECHECK",
        "primary_root_cause": {
            "title": "Invalid return type",
            "evidence": [{"file": "src/core/math.py", "line": 42}],
            "confidence": 0.8,
        },
        "ranked_alternatives": [
            {
                "title": "Dependency mismatch",
                "evidence": [{"file": "poetry.lock"}],
                "score": 0.2,
            }
        ],
        "suggested_fix": ["Fix function signature"],
        "meta": {"commit": "abc123", "run_id": "gha_1"},
    }

    output = rca_output_from_agent_outputs(payload)
    assert output.classification.value == "TYPECHECK"
    assert output.primary_root_cause.confidence == 0.8


def test_pr_result_converter() -> None:
    payload = {
        "pr_created": False,
        "failure_reason": "Patch exceeded max_fix_files",
    }

    result = pr_result_from_agent_output(payload)
    assert result.pr_created is False
    assert result.failure_reason == "Patch exceeded max_fix_files"


def test_pr_result_converter_is_deterministic_for_created_pr_payload() -> None:
    payload = {
        "pr_created": True,
        "pr_url": "https://github.com/acme/repo/pull/11",
        "pr_number": "11",
        "pr_branch": "ci-rootcause/fix/abc123-ghi456",
    }

    first = pr_result_from_agent_output(payload)
    second = pr_result_from_agent_output(payload)

    assert first == second
    assert first.pr_branch == "ci-rootcause/fix/abc123-ghi456"
    assert first.pr_number == 11
