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


def test_parse_ci_log_extracts_mypy_file_and_line() -> None:
    raw_log = """##[group]Run mypy
fixtures/canary/typecheck_target.py:5: error: Incompatible types in assignment
Found 1 error in 1 file (checked 1 source file)
##[endgroup]"""

    result = parse_ci_log(raw_log)

    event = result.failure_events[0]
    assert event.file == "fixtures/canary/typecheck_target.py"
    assert event.line == 5
    assert "fixtures/canary/typecheck_target.py:5" in event.stack_frames


def test_parse_ci_log_extracts_ruff_file_line_and_column_style() -> None:
    raw_log = """##[group]Run ruff
src/app.py:7:5: F401 `os` imported but unused
Found 1 error.
##[endgroup]"""

    result = parse_ci_log(raw_log)

    event = result.failure_events[0]
    assert event.file == "src/app.py"
    assert event.line == 7
    assert "src/app.py:7" in event.stack_frames


def test_parse_ci_log_extracts_ruff_arrow_location() -> None:
    raw_log = """##[group]Run ruff
invalid-syntax: Expected a parameter or the end of the parameter list
 --> bad.py:1:10
  |
1 | def oops(:
  |          ^
Found 1 error.
##[endgroup]"""

    result = parse_ci_log(raw_log)

    assert any(event.file == "bad.py" and event.line == 1 for event in result.failure_events)


def test_parse_ci_log_extracts_pytest_failure_location() -> None:
    raw_log = """##[group]Run pytest
tests/test_api.py::test_returns_200 FAILED
tests/test_api.py:14: AssertionError
##[endgroup]"""

    result = parse_ci_log(raw_log)

    event = result.failure_events[-1]
    assert event.file == "tests/test_api.py"
    assert event.line == 14


def test_parse_ci_log_extracts_typescript_parenthesized_location() -> None:
    raw_log = "\n".join(
        [
            "##[group]Run typecheck",
            "src/app.ts(14,5): error TS2345: Argument of type 'number' "
            "is not assignable to parameter of type 'string'.",
            "error Command failed with exit code 2.",
            "##[endgroup]",
        ]
    )

    result = parse_ci_log(raw_log)

    event = result.failure_events[0]
    assert event.file == "src/app.ts"
    assert event.line == 14
    assert "src/app.ts:14" in event.stack_frames


def test_parse_ci_log_extracts_dependency_package_name() -> None:
    raw_log = """##[group]Install dependencies
ERROR: Could not find a version that satisfies the requirement missing-package-abc123
ERROR: No matching distribution found for missing-package-abc123
##[endgroup]"""

    result = parse_ci_log(raw_log)

    assert result.failure_events
    assert any(
        "package:missing-package-abc123" in event.stack_frames for event in result.failure_events
    )


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
