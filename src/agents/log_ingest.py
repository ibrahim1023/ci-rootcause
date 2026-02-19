from __future__ import annotations

from dataclasses import asdict

from src.parsers.ci_log_parser import parse_ci_log


def run_log_ingest(raw_log: str, timestamp: str = "1970-01-01T00:00:00Z") -> dict:
    parsed = parse_ci_log(raw_log=raw_log, timestamp=timestamp)
    return {
        "stages": parsed.stages,
        "failure_events": [asdict(event) for event in parsed.failure_events],
    }
