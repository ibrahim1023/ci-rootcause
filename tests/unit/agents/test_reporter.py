import json
from pathlib import Path

from src.agents.reporter import run_reporter
from src.contracts.converters import rca_output_from_agent_outputs


def _sample_payload() -> dict:
    return {
        "summary": "Type error in changed module",
        "classification": "TYPECHECK",
        "primary_root_cause": {
            "title": "Invalid return type in src/core/math.py",
            "evidence": [
                {
                    "file": "src/core/math.py",
                    "line": 42,
                    "excerpt": "Incompatible return type",
                    "signal": "mypy",
                }
            ],
            "confidence": 0.82,
        },
        "ranked_alternatives": [
            {
                "title": "Outdated lockfile",
                "evidence": [
                    {
                        "file": "poetry.lock",
                        "line": None,
                        "excerpt": "Dependency mismatch",
                        "signal": "lockfile",
                    }
                ],
                "score": 0.29,
            }
        ],
        "suggested_fix": ["Update return type annotation in src/core/math.py"],
        "meta": {"commit": "abc123", "run_id": "gha_001"},
    }


def test_reporter_writes_json_and_markdown_snapshots(tmp_path: Path) -> None:
    payload = _sample_payload()
    result = run_reporter(payload=payload, output_dir=str(tmp_path))

    json_text = Path(result["ci_rca_json_path"]).read_text(encoding="utf-8")
    md_text = Path(result["ci_rca_md_path"]).read_text(encoding="utf-8")

    expected_json = Path("fixtures/contracts/ci-rca.reporter.snapshot.json").read_text(
        encoding="utf-8"
    )
    expected_md = Path("fixtures/contracts/ci-rca.reporter.snapshot.md").read_text(
        encoding="utf-8"
    )

    assert json_text == expected_json
    assert md_text == expected_md


def test_reporter_output_is_deterministic_across_runs(tmp_path: Path) -> None:
    payload = _sample_payload()
    first = run_reporter(payload=payload, output_dir=str(tmp_path / "first"))
    second = run_reporter(payload=payload, output_dir=str(tmp_path / "second"))

    first_json = Path(first["ci_rca_json_path"]).read_text(encoding="utf-8")
    second_json = Path(second["ci_rca_json_path"]).read_text(encoding="utf-8")
    first_md = Path(first["ci_rca_md_path"]).read_text(encoding="utf-8")
    second_md = Path(second["ci_rca_md_path"]).read_text(encoding="utf-8")

    assert first_json == second_json
    assert first_md == second_md


def test_reporter_pr_comment_and_upload_hooks_contract(tmp_path: Path) -> None:
    result = run_reporter(payload=_sample_payload(), output_dir=str(tmp_path))

    assert result["pr_comment"]["format"] == "markdown"
    assert result["pr_comment"]["version"] == "1"
    assert result["pr_comment"]["body"].startswith("<!-- ci-rootcause:pr-comment:v1 -->")
    assert result["artifact_upload_hooks"] == [
        {"name": "ci-rca-json", "path": str(tmp_path / "ci-rca.json")},
        {"name": "ci-rca-md", "path": str(tmp_path / "ci-rca.md")},
    ]


def test_reporter_backward_compatibility_with_rca_contract(tmp_path: Path) -> None:
    result = run_reporter(payload=_sample_payload(), output_dir=str(tmp_path))
    generated = json.loads(Path(result["ci_rca_json_path"]).read_text(encoding="utf-8"))

    fixture_payload = json.loads(Path("fixtures/contracts/ci-rca.sample.json").read_text())
    assert set(generated.keys()) == set(fixture_payload.keys())

    contract = rca_output_from_agent_outputs(generated)
    assert contract.meta.run_id == fixture_payload["meta"]["run_id"]
