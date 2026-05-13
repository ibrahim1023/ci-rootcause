from __future__ import annotations

import re
from dataclasses import dataclass

ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(error|exception|traceback|failed|failure|assertionerror)\b",
        re.IGNORECASE,
    ),
    re.compile(r"npm err!", re.IGNORECASE),
    re.compile(r"^---\s*FAIL:", re.IGNORECASE),
)

LOCATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\s*File \"(?P<file>[^\"]+)\", line (?P<line>\d+)"),
    re.compile(r"\s*at (?P<file>[^:\s]+):(?P<line>\d+):\d+"),
    re.compile(r"(?P<file>[A-Za-z0-9_./-]+):(?P<line>\d+):\s*error:"),
    re.compile(r"(?P<file>[A-Za-z0-9_./-]+):(?P<line>\d+):\d+:\s*[A-Z]\d+"),
    re.compile(r"(?P<file>[A-Za-z0-9_./-]+)\((?P<line>\d+),(?P<column>\d+)\):\s*error"),
    re.compile(r"(?P<file>[A-Za-z0-9_./-]+):(?P<line>\d+):\s*AssertionError"),
    re.compile(r"(?P<file>tests/[A-Za-z0-9_./-]+\.py)::[A-Za-z0-9_:\[\]-]+"),
)

RUFF_ARROW_PATTERN = re.compile(r"-->\s+(?P<file>[A-Za-z0-9_./-]+):(?P<line>\d+):\d+")
DEPENDENCY_REQUIREMENT_PATTERN = re.compile(
    r"(?:requirement|package)\s+(?P<package>[A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedFailureEvent:
    event_index: int
    stage: str
    timestamp: str
    error_signature: str
    file: str | None
    line: int | None
    stack_frames: list[str]
    log_excerpt: str


@dataclass(frozen=True)
class ParsedLog:
    stages: list[str]
    failure_events: list[ParsedFailureEvent]


def _extract_stage(raw_line: str, current_stage: str) -> str:
    line = raw_line.strip()
    if line.startswith("##[group]"):
        return line.replace("##[group]", "", 1).strip() or current_stage
    if line.startswith("##[endgroup]"):
        return "global"
    return current_stage


def _normalize_signature(line: str) -> str:
    normalized = re.sub(r"\s+", " ", line.strip())
    return normalized[:160]


def _find_stack_context(lines: list[str], idx: int) -> tuple[str | None, int | None, list[str]]:
    start = max(0, idx - 5)
    end = min(len(lines), idx + 6)

    file_path: str | None = None
    line_no: int | None = None
    frames: list[str] = []

    for probe in lines[start:end]:
        arrow_match = RUFF_ARROW_PATTERN.search(probe)
        if arrow_match:
            file_path = arrow_match.group("file")
            line_no = int(arrow_match.group("line"))
            frames.append(f"{file_path}:{line_no}")
            continue

        dependency_match = DEPENDENCY_REQUIREMENT_PATTERN.search(probe)
        if dependency_match:
            package_name = dependency_match.group("package")
            package_frame = f"package:{package_name}"
            if package_frame not in frames:
                frames.append(package_frame)

        for pattern in LOCATION_PATTERNS:
            match = pattern.search(probe)
            if not match:
                continue

            file_path = match.group("file")
            raw_line = match.groupdict().get("line")
            if raw_line is not None:
                line_no = int(raw_line)
                frames.append(f"{file_path}:{line_no}")
            else:
                frames.append(file_path)
            break

    return file_path, line_no, frames


def _is_error_line(raw_line: str) -> bool:
    if any(pattern.search(raw_line) for pattern in ERROR_PATTERNS):
        return True
    if RUFF_ARROW_PATTERN.search(raw_line):
        return True
    return any(pattern.search(raw_line) for pattern in LOCATION_PATTERNS)


def parse_ci_log(raw_log: str, timestamp: str = "1970-01-01T00:00:00Z") -> ParsedLog:
    lines = raw_log.splitlines()
    current_stage = "global"
    stages: list[str] = [current_stage]
    events: list[ParsedFailureEvent] = []

    for idx, raw_line in enumerate(lines):
        current_stage = _extract_stage(raw_line, current_stage)
        if current_stage not in stages:
            stages.append(current_stage)

        if not _is_error_line(raw_line):
            continue

        file_path, line_no, frames = _find_stack_context(lines, idx)
        excerpt_start = max(0, idx - 1)
        excerpt_end = min(len(lines), idx + 2)
        excerpt = "\n".join(lines[excerpt_start:excerpt_end]).strip()

        events.append(
            ParsedFailureEvent(
                event_index=idx,
                stage=current_stage,
                timestamp=timestamp,
                error_signature=_normalize_signature(raw_line),
                file=file_path,
                line=line_no,
                stack_frames=frames,
                log_excerpt=excerpt,
            )
        )

    return ParsedLog(stages=stages, failure_events=events)
