from pathlib import Path

from src.agents.log_ingest import run_log_ingest


def test_log_ingest_builds_failure_graph_and_first_failure_event() -> None:
    raw_log = """##[group]Run test
E   AssertionError: assert 3 == 4
tests/test_math.py:12: AssertionError
##[endgroup]"""

    output = run_log_ingest(raw_log, timestamp="2026-02-19T00:00:00Z")

    assert "failure_graph" in output
    assert "first_failure_event" in output
    assert output["first_failure_event"] is not None
    assert output["failure_graph"]["nodes"][0]["is_first_failure"] is True


def test_log_ingest_applies_deterministic_tie_break() -> None:
    raw_log = """##[group]Run stage
E   RuntimeError: boom
E   RuntimeError: boom
##[endgroup]"""

    first = run_log_ingest(raw_log, timestamp="2026-02-19T00:00:00Z")
    second = run_log_ingest(raw_log, timestamp="2026-02-19T00:00:00Z")

    assert first["first_failure_event"] == second["first_failure_event"]
    assert first["failure_graph"] == second["failure_graph"]


def test_log_ingest_integration_with_fixture() -> None:
    raw_log = Path("fixtures/ci-logs/github-actions-python-failure.log").read_text()
    output = run_log_ingest(raw_log, timestamp="2026-02-19T00:00:00Z")

    assert output["first_failure_event"] is not None
    assert len(output["failure_graph"]["nodes"]) >= 1
    assert output["failure_graph"]["nodes"][0]["stage"] == "Run pytest"
    assert sum(1 for node in output["failure_graph"]["nodes"] if node["is_first_failure"]) == 1


def test_log_ingest_supports_matrix_fixture() -> None:
    raw_log = Path("fixtures/ci-logs/github-actions-matrix-mixed-failure.log").read_text(
        encoding="utf-8"
    )
    output = run_log_ingest(raw_log, timestamp="2026-02-23T00:00:00Z")

    assert output["first_failure_event"] is not None
    assert output["first_failure_event"]["stage"] == "Run pytest (ubuntu-latest, python-3.11)"
    assert len(output["failure_graph"]["nodes"]) >= 2


def test_log_ingest_supports_cancelled_partial_fixture() -> None:
    raw_log = Path("fixtures/ci-logs/github-actions-cancelled-partial.log").read_text(
        encoding="utf-8"
    )
    output = run_log_ingest(raw_log, timestamp="2026-02-23T00:00:00Z")

    assert output["first_failure_event"] is not None
    assert any(
        "timed out and was canceled" in event["error_signature"].lower()
        for event in output["failure_events"]
    )
