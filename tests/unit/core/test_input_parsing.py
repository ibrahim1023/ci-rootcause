from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.input_parsing import (
    InputParsingError,
    load_historical_runs,
    load_simple_config,
    load_validated_changes,
    parse_bool,
    parse_confidence_threshold,
    parse_execution_mode,
    parse_positive_int,
)


def test_parse_bool_accepts_supported_literals() -> None:
    assert parse_bool("true", name="flag") is True
    assert parse_bool("1", name="flag") is True
    assert parse_bool("no", name="flag") is False


def test_parse_bool_rejects_invalid_value() -> None:
    with pytest.raises(InputParsingError, match="Invalid boolean value for flag"):
        parse_bool("maybe", name="flag")


def test_parse_positive_int_rejects_non_positive() -> None:
    with pytest.raises(InputParsingError, match="max_fix_files must be > 0"):
        parse_positive_int("0", name="max_fix_files")


def test_parse_confidence_threshold_rejects_out_of_range() -> None:
    with pytest.raises(InputParsingError, match="min_pr_confidence must be between 0.0 and 1.0"):
        parse_confidence_threshold("1.1", name="min_pr_confidence")


def test_parse_execution_mode_accepts_supported_value() -> None:
    parsed = parse_execution_mode("agentic_assist")
    assert parsed.value == "agentic_assist"


def test_parse_execution_mode_rejects_invalid_value() -> None:
    with pytest.raises(InputParsingError, match="Invalid value for mode"):
        parse_execution_mode("fast-and-loose")


def test_load_simple_config_respects_missing_ok(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yml"
    assert load_simple_config(missing, missing_ok=True) == {}
    with pytest.raises(InputParsingError, match="config_path does not exist"):
        load_simple_config(missing, missing_ok=False)


def test_load_validated_changes_uses_expected_list_message(tmp_path: Path) -> None:
    path = tmp_path / "validated.json"
    path.write_text('{"invalid": true}', encoding="utf-8")

    with pytest.raises(InputParsingError, match="custom validated list error"):
        load_validated_changes(path, expected_list_message="custom validated list error")


def test_load_validated_changes_rejects_missing_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "validated.json"
    path.write_text('[{"file":"src/app.py"}]', encoding="utf-8")

    with pytest.raises(
        InputParsingError,
        match="Each validated change must include string fields: file, content",
    ):
        load_validated_changes(path, expected_list_message="unused")


def test_load_historical_runs_rejects_non_list_failure_events(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text('[{"failure_events":"bad"}]', encoding="utf-8")

    with pytest.raises(InputParsingError, match="Each historical run field 'failure_events'"):
        load_historical_runs(path, expected_list_message="unused")


@pytest.mark.parametrize(
    "path_value, expected_message",
    [
        ("/tmp/abs.py", "Absolute paths are not allowed"),
        ("../escape.py", "Parent directory traversal is not allowed"),
        ("./src/file.py", "Dot-segment path syntax is not allowed"),
        ("src//file.py", "Duplicate path separators are not allowed"),
        ("src\\file.py", "Backslashes are not allowed in file paths"),
    ],
)
def test_load_validated_changes_rejects_ambiguous_paths(
    tmp_path: Path, path_value: str, expected_message: str
) -> None:
    path = tmp_path / "validated.json"
    path.write_text(
        json.dumps([{"file": path_value, "content": "print(1)\n"}]),
        encoding="utf-8",
    )

    with pytest.raises(InputParsingError, match=expected_message):
        load_validated_changes(path, expected_list_message="unused")
