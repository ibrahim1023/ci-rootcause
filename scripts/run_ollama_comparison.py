from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.ollama_comparison import run_ollama_comparison


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare fixture-backed agentic benchmark cases against a live Ollama run"
    )
    parser.add_argument("--suite", default="fixtures/benchmarks/mvp-suite.json")
    parser.add_argument("--output-root", default="artifacts/ollama-comparison")
    parser.add_argument("--report-json", default="artifacts/ollama-comparison/latest.json")
    parser.add_argument("--llm-model", required=True)
    parser.add_argument("--llm-base-url", default="http://localhost:11434")
    parser.add_argument("--repeat-runs", default=1, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = run_ollama_comparison(
        suite_path=args.suite,
        output_root=args.output_root,
        llm_model=args.llm_model,
        llm_base_url=args.llm_base_url,
        repeat_runs=args.repeat_runs,
    )
    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
