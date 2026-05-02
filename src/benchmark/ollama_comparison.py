from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from src.benchmark.suite import run_benchmark_suite


class OllamaComparisonError(RuntimeError):
    """Raised when the Ollama comparison benchmark cannot be prepared."""


def _load_suite(path: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise OllamaComparisonError(f"Unable to read benchmark suite '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OllamaComparisonError(f"Invalid benchmark suite JSON '{path}': {exc}") from exc
    if not isinstance(payload, dict):
        raise OllamaComparisonError("Benchmark suite root must be a JSON object")
    return payload


def _agentic_cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise OllamaComparisonError("Benchmark suite must include a cases list")
    cases = [dict(item) for item in raw_cases if isinstance(item, dict)]
    filtered = [
        case for case in cases if str(case.get("execution_mode", "")).strip() == "agentic_assist"
    ]
    if not filtered:
        raise OllamaComparisonError("No agentic_assist cases found in benchmark suite")
    return filtered


def build_live_ollama_suite(
    *,
    suite_path: str,
    llm_model: str,
    llm_base_url: str,
) -> dict[str, Any]:
    payload = _load_suite(suite_path)
    cases = _agentic_cases(payload)
    live_cases: list[dict[str, Any]] = []
    for case in cases:
        live_case = dict(case)
        live_case.pop("mocked_agentic_proposal_path", None)
        live_case["llm_provider"] = "local"
        live_case["llm_model"] = llm_model
        live_case["llm_base_url"] = llm_base_url
        live_cases.append(live_case)
    return {
        "suite_name": f"{str(payload.get('suite_name', 'benchmark')).strip()}-live-ollama",
        "cases": live_cases,
    }


def run_ollama_comparison(
    *,
    suite_path: str,
    output_root: str,
    llm_model: str,
    llm_base_url: str = "http://localhost:11434",
    repeat_runs: int = 1,
) -> dict[str, Any]:
    baseline_report = run_benchmark_suite(
        suite_path=suite_path,
        output_root=str(Path(output_root) / "fixture-baseline"),
        use_adk_runtime=False,
        repeat_runs=repeat_runs,
    )
    live_suite = build_live_ollama_suite(
        suite_path=suite_path,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )
    with TemporaryDirectory(prefix="ci-rootcause-ollama-suite-") as temp_dir:
        suite_file = Path(temp_dir) / "live-ollama-suite.json"
        suite_file.write_text(json.dumps(live_suite, indent=2) + "\n", encoding="utf-8")
        live_report = run_benchmark_suite(
            suite_path=str(suite_file),
            output_root=str(Path(output_root) / "live-ollama"),
            use_adk_runtime=False,
            repeat_runs=repeat_runs,
        )

    return {
        "baseline_suite_name": baseline_report["suite_name"],
        "live_suite_name": live_report["suite_name"],
        "llm_provider": "local",
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "baseline": {
            "total_cases": baseline_report["total_cases"],
            "classification_match_rate": baseline_report["classification_match_rate"],
            "agentic_proposal_valid_rate": baseline_report["agentic_proposal_valid_rate"],
            "validation_pass_rate": baseline_report["validation_pass_rate"],
        },
        "live": {
            "total_cases": live_report["total_cases"],
            "classification_match_rate": live_report["classification_match_rate"],
            "agentic_proposal_valid_rate": live_report["agentic_proposal_valid_rate"],
            "validation_pass_rate": live_report["validation_pass_rate"],
        },
        "live_report": live_report,
    }
