from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.execution_mode import ExecutionMode
from src.core.execution_mode import parse_execution_mode as _parse_execution_mode
from src.path_safety import PathSafetyError, normalize_repo_relative_path


class InputParsingError(ValueError):
    """Raised when input parsing/validation fails."""


def parse_bool(value: str, *, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise InputParsingError(f"Invalid boolean value for {name}: '{value}'")


def parse_positive_int(value: str, *, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise InputParsingError(f"Invalid integer value for {name}: '{value}'") from exc
    if parsed <= 0:
        raise InputParsingError(f"{name} must be > 0")
    return parsed


def parse_confidence_threshold(value: str, *, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise InputParsingError(f"Invalid float value for {name}: '{value}'") from exc
    if not (0.0 <= parsed <= 1.0):
        raise InputParsingError(f"{name} must be between 0.0 and 1.0")
    return parsed


def parse_execution_mode(value: str, *, name: str = "mode") -> ExecutionMode:
    try:
        return _parse_execution_mode(value, name=name)
    except ValueError as exc:
        raise InputParsingError(str(exc)) from exc


def load_simple_config(path: Path, *, missing_ok: bool) -> dict[str, str]:
    if not path.exists():
        if missing_ok:
            return {}
        raise InputParsingError(f"config_path does not exist: '{path}'")

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise InputParsingError(f"Unable to read config_path '{path}': {exc}") from exc

    config: dict[str, str] = {}
    for index, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise InputParsingError(f"Invalid config line {index} in '{path}': expected key: value")
        key, value = line.split(":", maxsplit=1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise InputParsingError(f"Invalid config line {index} in '{path}': empty key")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        config[key] = value
    return config


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputParsingError(f"Unable to read file '{path}': {exc}") from exc


def load_validated_changes(
    path: Path | None,
    *,
    expected_list_message: str,
) -> list[dict[str, str]]:
    if path is None:
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputParsingError(f"Unable to read validated changes file '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputParsingError(f"Invalid JSON in validated changes file '{path}': {exc}") from exc

    if not isinstance(raw, list):
        raise InputParsingError(expected_list_message)

    normalized: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise InputParsingError("Each validated change must be a JSON object")
        file_path_raw = str(item.get("file", ""))
        content = item.get("content")
        if not isinstance(content, str):
            raise InputParsingError(
                "Each validated change must include string fields: file, content"
            )
        try:
            file_path = normalize_repo_relative_path(file_path_raw)
        except PathSafetyError as exc:
            raise InputParsingError(str(exc)) from exc
        normalized.append({"file": file_path, "content": content})

    return normalized


def load_historical_runs(
    path: Path | None,
    *,
    expected_list_message: str,
) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputParsingError(f"Unable to read historical runs file '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputParsingError(f"Invalid JSON in historical runs file '{path}': {exc}") from exc

    if not isinstance(raw, list):
        raise InputParsingError(expected_list_message)

    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise InputParsingError("Each historical run must be a JSON object")
        failure_events = item.get("failure_events", [])
        if failure_events is not None and not isinstance(failure_events, list):
            raise InputParsingError(
                "Each historical run field 'failure_events' must be a JSON list"
            )
        normalized.append(dict(item))
    return normalized
