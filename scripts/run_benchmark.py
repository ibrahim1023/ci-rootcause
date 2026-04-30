from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.suite import run_benchmark_suite


def _format_metric(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return "n/a"
    return str(value)


def _render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# MVP Benchmark Report",
        "",
        f"- Suite: {report['suite_name']}",
        f"- Total cases: {report['total_cases']}",
        f"- Completed cases: {report['completed_cases']}",
        f"- Completion rate: {_format_metric(report['completion_rate'])}",
        f"- Classification matches: {report['classification_matches']}",
        f"- Classification match rate: {_format_metric(report['classification_match_rate'])}",
        f"- Baseline classification matches: {report['baseline_classification_matches']}",
        (
            "- Baseline classification match rate: "
            f"{_format_metric(report['baseline_classification_match_rate'])}"
        ),
        (
            "- Classification match lift vs baseline: "
            f"{_format_metric(report['classification_match_lift'])}"
        ),
        f"- Primary root-cause matches: {report['primary_root_cause_matches']}",
        f"- Primary root-cause accuracy: {_format_metric(report['primary_root_cause_accuracy'])}",
        f"- Top-1 root-cause cases: {report['top1_root_cause_cases']}",
        f"- Top-1 root-cause matches: {report['top1_root_cause_matches']}",
        f"- Top-1 root-cause accuracy: {_format_metric(report['top1_root_cause_accuracy'])}",
        (f"- Agentic proposal valid rate: {_format_metric(report['agentic_proposal_valid_rate'])}"),
        f"- Agentic proposal valid cases: {report['agentic_proposal_valid_cases']}",
        f"- Validation pass rate: {_format_metric(report['validation_pass_rate'])}",
        f"- Validation pass cases: {report['validation_pass_cases']}",
        f"- Confidence reproducibility: {_format_metric(report['confidence_reproducibility'])}",
        (
            "- Artifact hash reproducibility: "
            f"{_format_metric(report['artifact_hash_reproducibility'])}"
        ),
        (f"- Mean time-to-diagnosis (ms): {_format_metric(report['mean_time_to_diagnosis_ms'])}"),
        (
            "- Median time-to-diagnosis (ms): "
            f"{_format_metric(report['median_time_to_diagnosis_ms'])}"
        ),
        f"- P95 time-to-diagnosis (ms): {_format_metric(report['p95_time_to_diagnosis_ms'])}",
        "",
        "## Case Results",
        "",
    ]

    for item in report.get("cases", []):
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"- Case: {item['case_id']}",
                (
                    "  - Classification: "
                    f"{item['classification']} "
                    f"(expected: {item['expected_classification']})"
                ),
                (f"  - Primary root cause: {item['primary_root_cause_title']}"),
                (
                    "  - Top-1 file/line: "
                    f"{item['actual_primary_root_cause_file']}:{item['actual_primary_root_cause_line']}"
                    if item.get("top1_root_cause_applicable")
                    else "  - Top-1 file/line: n/a"
                ),
                f"  - Confidence values: {item['confidence_values']}",
                f"  - Pipeline timing ms: {item['pipeline_timing_ms']}",
            ]
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ci-rootcause benchmark suite")
    parser.add_argument(
        "--suite",
        default="fixtures/benchmarks/mvp-suite.json",
        help="Path to the benchmark suite JSON.",
    )
    parser.add_argument(
        "--output-root",
        default="artifacts/benchmark-mvp",
        help="Directory for per-case benchmark artifacts.",
    )
    parser.add_argument(
        "--report-json",
        default="docs/reports/mvp-benchmark-report.json",
        help="Path to write the benchmark JSON report.",
    )
    parser.add_argument(
        "--report-md",
        default="docs/reports/mvp-benchmark-report.md",
        help="Path to write the benchmark Markdown summary.",
    )
    parser.add_argument(
        "--repeat-runs",
        default=2,
        type=int,
        help="Number of repeated runs per case.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    report = run_benchmark_suite(
        suite_path=args.suite,
        output_root=args.output_root,
        use_adk_runtime=False,
        repeat_runs=args.repeat_runs,
    )

    report_json_path = Path(args.report_json)
    report_md_path = Path(args.report_md)
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_md_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    report_md_path.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
