from pathlib import Path

from src.parsers.ci_log_parser import parse_ci_log


def test_parse_ci_log_extracts_stage_and_failure_event() -> None:
    raw_log = """##[group]Run pytest
E   AssertionError: assert 3 == 4
tests/test_math.py:12: AssertionError
##[endgroup]"""

    result = parse_ci_log(raw_log, timestamp="2026-02-19T00:00:00Z")

    assert "Run pytest" in result.stages
    assert len(result.failure_events) >= 1
    first = result.failure_events[0]
    assert first.stage == "Run pytest"
    assert "AssertionError" in first.error_signature
    assert first.timestamp == "2026-02-19T00:00:00Z"


def test_parse_ci_log_extracts_python_stack_frame_from_traceback() -> None:
    raw_log = """##[group]Run tests
Traceback (most recent call last):
  File \"src/app.py\", line 9, in <module>
    main()
RuntimeError: boom
##[endgroup]"""

    result = parse_ci_log(raw_log)

    event = result.failure_events[-1]
    assert event.file == "src/app.py"
    assert event.line == 9
    assert "src/app.py:9" in event.stack_frames


def test_parse_ci_log_handles_no_errors() -> None:
    raw_log = """##[group]Run lint
All checks passed
##[endgroup]"""

    result = parse_ci_log(raw_log)

    assert result.stages == ["global", "Run lint"]
    assert result.failure_events == []


def test_parse_ci_log_handles_matrix_style_groups() -> None:
    raw_log = Path("fixtures/ci-logs/github-actions-matrix-mixed-failure.log").read_text(
        encoding="utf-8"
    )

    result = parse_ci_log(raw_log)

    assert "Run pytest (ubuntu-latest, python-3.11)" in result.stages
    assert "Run pytest (ubuntu-latest, python-3.12)" in result.stages
    assert any("TS2345" in event.error_signature for event in result.failure_events)


def test_parse_ci_log_handles_cancelled_partial_runs() -> None:
    raw_log = Path("fixtures/ci-logs/github-actions-cancelled-partial.log").read_text(
        encoding="utf-8"
    )

    result = parse_ci_log(raw_log)

    assert len(result.failure_events) >= 1
    assert any(
        "timed out and was canceled" in event.error_signature.lower()
        for event in result.failure_events
    )
