from __future__ import annotations

import json
from pathlib import Path

from src.cli import main


def _sample_log() -> str:
    return "\n".join(
        [
            "##[group] test",
            "Traceback (most recent call last):",
            '  File "src/app.py", line 7, in <module>',
            "AssertionError: expected 1 == 2",
            "##[endgroup]",
        ]
    )


def _sample_diff() -> str:
    return "\n".join(
        [
            "diff --git a/src/app.py b/src/app.py",
            "index 1111111..2222222 100644",
            "--- a/src/app.py",
            "+++ b/src/app.py",
            "@@ -1 +1 @@",
            "-value = 1",
            "+value = 2",
        ]
    )


def test_cli_runs_pipeline_and_writes_artifacts(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "ci.log"
    diff_path = tmp_path / "change.diff"
    out_dir = tmp_path / "artifacts"
    log_path.write_text(_sample_log(), encoding="utf-8")
    diff_path.write_text(_sample_diff(), encoding="utf-8")

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--diff-path",
            str(diff_path),
            "--output-dir",
            str(out_dir),
            "--timestamp",
            "2026-02-20T00:00:00Z",
            "--commit",
            "abc123",
            "--run-id",
            "gha_5001",
            "--base-commit",
            "abc123",
            "--head-commit",
            "def456",
            "--repository",
            "acme/ci-rootcause",
        ]
    )

    assert exit_code == 0
    assert (out_dir / "ci-rca.json").exists()
    assert (out_dir / "ci-rca.md").exists()

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert payload["pipeline_status"] == "completed"
    assert payload["classification"] == "TEST"
    assert payload["primary_root_cause_title"]
    assert payload["rca_json_path"].endswith("ci-rca.json")
    assert payload["rca_md_path"].endswith("ci-rca.md")
    assert payload["pr_created"] is False


def test_cli_returns_error_for_missing_log_file(tmp_path: Path, capsys) -> None:
    diff_path = tmp_path / "change.diff"
    diff_path.write_text(_sample_diff(), encoding="utf-8")

    exit_code = main(
        [
            "--log-path",
            str(tmp_path / "missing.log"),
            "--diff-path",
            str(diff_path),
            "--output-dir",
            str(tmp_path / "artifacts"),
            "--timestamp",
            "2026-02-20T00:00:00Z",
            "--commit",
            "abc123",
            "--run-id",
            "gha_5002",
            "--base-commit",
            "abc123",
            "--head-commit",
            "def456",
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "ci-rootcause CLI error:" in captured.out


def test_cli_returns_error_for_invalid_historical_runs_payload(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "ci.log"
    diff_path = tmp_path / "change.diff"
    historical_path = tmp_path / "historical.json"

    log_path.write_text(_sample_log(), encoding="utf-8")
    diff_path.write_text(_sample_diff(), encoding="utf-8")
    historical_path.write_text('{"invalid": true}', encoding="utf-8")

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--diff-path",
            str(diff_path),
            "--output-dir",
            str(tmp_path / "artifacts"),
            "--timestamp",
            "2026-02-20T00:00:00Z",
            "--commit",
            "abc123",
            "--run-id",
            "gha_5003",
            "--base-commit",
            "abc123",
            "--head-commit",
            "def456",
            "--historical-runs-path",
            str(historical_path),
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Historical runs payload must be a JSON list" in captured.out


def test_cli_returns_error_for_invalid_min_pr_confidence(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "ci.log"
    diff_path = tmp_path / "change.diff"

    log_path.write_text(_sample_log(), encoding="utf-8")
    diff_path.write_text(_sample_diff(), encoding="utf-8")

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--diff-path",
            str(diff_path),
            "--output-dir",
            str(tmp_path / "artifacts"),
            "--timestamp",
            "2026-02-20T00:00:00Z",
            "--commit",
            "abc123",
            "--run-id",
            "gha_5004",
            "--base-commit",
            "abc123",
            "--head-commit",
            "def456",
            "--min-pr-confidence",
            "invalid",
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "could not convert string to float: 'invalid'" in captured.out
