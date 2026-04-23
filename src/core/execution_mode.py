from __future__ import annotations

from enum import Enum


class ExecutionMode(str, Enum):
    DETERMINISTIC = "deterministic"
    AGENTIC_ASSIST = "agentic_assist"
    AGENTIC_FULL = "agentic_full"


def parse_execution_mode(value: str, *, name: str = "mode") -> ExecutionMode:
    normalized = value.strip().lower()
    for mode in ExecutionMode:
        if normalized == mode.value:
            return mode
    supported = ", ".join(mode.value for mode in ExecutionMode)
    raise ValueError(f"Invalid value for {name}: '{value}'. Supported: {supported}")
