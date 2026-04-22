from __future__ import annotations

from pathlib import PurePosixPath


class PathSafetyError(ValueError):
    """Raised when repository-relative path validation fails."""


def normalize_repo_relative_path(file_path: str) -> str:
    normalized_input = file_path.strip()
    if not normalized_input or normalized_input == ".":
        raise PathSafetyError("Change file path must not be empty")
    if "\\" in normalized_input:
        raise PathSafetyError(f"Backslashes are not allowed in file paths: {file_path}")
    if (
        normalized_input.startswith("./")
        or "/./" in normalized_input
        or normalized_input.endswith("/.")
    ):
        raise PathSafetyError(f"Dot-segment path syntax is not allowed: {file_path}")
    if "//" in normalized_input:
        raise PathSafetyError(f"Duplicate path separators are not allowed: {file_path}")
    if normalized_input.endswith("/"):
        raise PathSafetyError(f"Directory paths are not allowed for file changes: {file_path}")

    candidate = PurePosixPath(normalized_input)
    if candidate.is_absolute():
        raise PathSafetyError(f"Absolute paths are not allowed: {file_path}")
    if ".." in candidate.parts:
        raise PathSafetyError(f"Parent directory traversal is not allowed: {file_path}")

    normalized = candidate.as_posix()
    if not normalized or normalized == ".":
        raise PathSafetyError("Change file path must not be empty")
    return normalized
