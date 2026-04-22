from __future__ import annotations

from pathlib import Path

from src.action_entrypoint import main


def _parse_github_output(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, value = line.split("=", maxsplit=1)
        payload[key] = value
    return payload


def test_action_entrypoint_emits_expected_outputs(tmp_path: Path, monkeypatch) -> None:
    output_file = tmp_path / "github_output.txt"
    artifact_dir = tmp_path / "artifacts"
    config_path = tmp_path / "ci-rootcause.yml"

    config_path.write_text(
        "\n".join(
            [
                f"log_path: {Path('fixtures/ci-logs/github-actions-python-failure.log').resolve()}",
                f"diff_path: {Path('fixtures/diffs/refactor-only.diff').resolve()}",
                f"output_dir: {artifact_dir}",
                "timestamp: 2026-02-21T00:00:00Z",
                "run_id: gha_8001",
                "commit: abc123",
                "base_commit: abc122",
                "head_commit: abc123",
                "repository: acme/ci-rootcause",
                "target_branch: main",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("INPUT_GITHUB_TOKEN", "dummy-token")
    monkeypatch.setenv("INPUT_CREATE_FIX_PR", "false")
    monkeypatch.setenv("INPUT_POST_PR_COMMENT", "true")
    monkeypatch.setenv("INPUT_BASE_REF", "")
    monkeypatch.setenv("INPUT_HEAD_REF", "")
    monkeypatch.setenv("INPUT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("INPUT_MAX_FIX_FILES", "5")

    exit_code = main()

    assert exit_code == 0
    payload = _parse_github_output(output_file)
    assert payload["classification"] == "TEST"
    assert float(payload["confidence"]) >= 0.0
    assert payload["primary_root_cause_title"]
    assert payload["pr_created"] == "false"
    assert payload["pr_url"] == ""
    assert payload["pr_number"] == ""
    assert payload["pr_failure_reason_code"] == "CREATE_FIX_PR_DISABLED"
    assert payload["pr_failure_reason"] == "create_fix_pr=false"
    assert payload["rca_json_path"].endswith("ci-rca.json")
    assert payload["rca_md_path"].endswith("ci-rca.md")
    assert (artifact_dir / "ci-rca.json").exists()
    assert (artifact_dir / "ci-rca.md").exists()


def test_action_entrypoint_requires_github_token(tmp_path: Path, monkeypatch) -> None:
    output_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.delenv("INPUT_GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("INPUT_CREATE_FIX_PR", "false")
    monkeypatch.setenv("INPUT_POST_PR_COMMENT", "true")
    monkeypatch.setenv("INPUT_CONFIG_PATH", str(tmp_path / "missing.yml"))
    monkeypatch.setenv("INPUT_MAX_FIX_FILES", "5")

    exit_code = main()

    assert exit_code == 2
    payload = _parse_github_output(output_file)
    assert payload["classification"] == "UNKNOWN"
    assert payload["pr_created"] == "false"
    assert payload["pr_failure_reason_code"] == "ACTION_INPUT_ERROR"
    assert payload["pr_failure_reason"] == "Missing required action input: github_token"


def test_action_entrypoint_disables_pr_when_patch_scope_exceeds_limit(
    tmp_path: Path, monkeypatch
) -> None:
    output_file = tmp_path / "github_output.txt"
    artifact_dir = tmp_path / "artifacts"
    validated_changes_path = tmp_path / "validated_changes.json"
    config_path = tmp_path / "ci-rootcause.yml"

    validated_changes_path.write_text(
        (
            '[{"file":"src/app.py","content":"print(1)\\n"},'
            '{"file":"src/new_file.py","content":"print(2)\\n"}]'
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        "\n".join(
            [
                f"log_path: {Path('fixtures/ci-logs/github-actions-python-failure.log').resolve()}",
                f"diff_path: {Path('fixtures/diffs/refactor-only.diff').resolve()}",
                f"validated_changes_path: {validated_changes_path}",
                f"output_dir: {artifact_dir}",
                "timestamp: 2026-02-21T00:00:00Z",
                "run_id: gha_8002",
                "commit: abc123",
                "base_commit: abc122",
                "head_commit: abc123",
                "repository: acme/ci-rootcause",
                "target_branch: main",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("INPUT_GITHUB_TOKEN", "dummy-token")
    monkeypatch.setenv("INPUT_CREATE_FIX_PR", "true")
    monkeypatch.setenv("INPUT_POST_PR_COMMENT", "true")
    monkeypatch.setenv("INPUT_BASE_REF", "")
    monkeypatch.setenv("INPUT_HEAD_REF", "")
    monkeypatch.setenv("INPUT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("INPUT_MAX_FIX_FILES", "1")

    exit_code = main()

    assert exit_code == 0
    payload = _parse_github_output(output_file)
    assert payload["pr_created"] == "false"
    assert payload["pr_failure_reason_code"] == "MAX_FIX_FILES_EXCEEDED"
    assert payload["pr_failure_reason"] == "validated changes exceed max_fix_files limit"
    assert (artifact_dir / "ci-rca.json").exists()
    assert (artifact_dir / "ci-rca.md").exists()


def test_action_entrypoint_rejects_invalid_historical_runs_payload(
    tmp_path: Path, monkeypatch
) -> None:
    output_file = tmp_path / "github_output.txt"
    config_path = tmp_path / "ci-rootcause.yml"
    historical_path = tmp_path / "historical.json"
    historical_path.write_text('{"invalid": true}', encoding="utf-8")

    config_path.write_text(
        "\n".join(
            [
                "raw_log: pytest failed",
                "raw_diff: diff --git a/a.py b/a.py",
                f"historical_runs_path: {historical_path}",
                f"output_dir: {tmp_path / 'artifacts'}",
                "timestamp: 2026-02-21T00:00:00Z",
                "run_id: gha_8003",
                "commit: abc123",
                "base_commit: abc122",
                "head_commit: abc123",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("INPUT_GITHUB_TOKEN", "dummy-token")
    monkeypatch.setenv("INPUT_CREATE_FIX_PR", "false")
    monkeypatch.setenv("INPUT_POST_PR_COMMENT", "true")
    monkeypatch.setenv("INPUT_BASE_REF", "")
    monkeypatch.setenv("INPUT_HEAD_REF", "")
    monkeypatch.setenv("INPUT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("INPUT_MAX_FIX_FILES", "5")

    exit_code = main()

    assert exit_code == 2
    payload = _parse_github_output(output_file)
    assert payload["classification"] == "UNKNOWN"
    assert payload["pr_created"] == "false"
    assert payload["pr_failure_reason_code"] == "ACTION_INPUT_ERROR"
    assert payload["pr_failure_reason"] == "historical_runs_path must point to a JSON list"


def test_action_entrypoint_rejects_invalid_min_pr_confidence(tmp_path: Path, monkeypatch) -> None:
    output_file = tmp_path / "github_output.txt"
    config_path = tmp_path / "ci-rootcause.yml"
    config_path.write_text(
        "\n".join(
            [
                "raw_log: pytest failed",
                "raw_diff: diff --git a/a.py b/a.py",
                f"output_dir: {tmp_path / 'artifacts'}",
                "timestamp: 2026-02-21T00:00:00Z",
                "run_id: gha_8004",
                "commit: abc123",
                "base_commit: abc122",
                "head_commit: abc123",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("INPUT_GITHUB_TOKEN", "dummy-token")
    monkeypatch.setenv("INPUT_CREATE_FIX_PR", "false")
    monkeypatch.setenv("INPUT_POST_PR_COMMENT", "true")
    monkeypatch.setenv("INPUT_BASE_REF", "")
    monkeypatch.setenv("INPUT_HEAD_REF", "")
    monkeypatch.setenv("INPUT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("INPUT_MAX_FIX_FILES", "5")
    monkeypatch.setenv("INPUT_MIN_PR_CONFIDENCE", "1.5")

    exit_code = main()

    assert exit_code == 2
    payload = _parse_github_output(output_file)
    assert payload["classification"] == "UNKNOWN"
    assert payload["pr_created"] == "false"
    assert payload["pr_failure_reason_code"] == "ACTION_INPUT_ERROR"
    assert payload["pr_failure_reason"] == "min_pr_confidence must be between 0.0 and 1.0"


def test_action_entrypoint_offline_only_skips_pr_creation(tmp_path: Path, monkeypatch) -> None:
    output_file = tmp_path / "github_output.txt"
    artifact_dir = tmp_path / "artifacts"
    config_path = tmp_path / "ci-rootcause.yml"

    config_path.write_text(
        "\n".join(
            [
                f"log_path: {Path('fixtures/ci-logs/github-actions-python-failure.log').resolve()}",
                f"diff_path: {Path('fixtures/diffs/refactor-only.diff').resolve()}",
                f"output_dir: {artifact_dir}",
                "timestamp: 2026-02-24T00:00:00Z",
                "run_id: gha_8005",
                "commit: abc123",
                "base_commit: abc122",
                "head_commit: abc123",
                "repository: acme/ci-rootcause",
                "target_branch: main",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("INPUT_GITHUB_TOKEN", "dummy-token")
    monkeypatch.setenv("INPUT_CREATE_FIX_PR", "true")
    monkeypatch.setenv("INPUT_OFFLINE_ONLY", "true")
    monkeypatch.setenv("INPUT_POST_PR_COMMENT", "true")
    monkeypatch.setenv("INPUT_BASE_REF", "")
    monkeypatch.setenv("INPUT_HEAD_REF", "")
    monkeypatch.setenv("INPUT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("INPUT_MAX_FIX_FILES", "5")

    exit_code = main()

    assert exit_code == 0
    payload = _parse_github_output(output_file)
    assert payload["pr_created"] == "false"
    assert payload["pr_failure_reason_code"] == "OFFLINE_ONLY"
    assert payload["pr_failure_reason"] == "offline_only=true"


def test_action_entrypoint_rejects_unknown_rollout_profile(tmp_path: Path, monkeypatch) -> None:
    output_file = tmp_path / "github_output.txt"
    config_path = tmp_path / "ci-rootcause.yml"
    config_path.write_text(
        "\n".join(
            [
                "raw_log: pytest failed",
                "raw_diff: diff --git a/a.py b/a.py",
                f"output_dir: {tmp_path / 'artifacts'}",
                "timestamp: 2026-02-24T00:00:00Z",
                "run_id: gha_8006",
                "commit: abc123",
                "base_commit: abc122",
                "head_commit: abc123",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("INPUT_GITHUB_TOKEN", "dummy-token")
    monkeypatch.setenv("INPUT_CREATE_FIX_PR", "false")
    monkeypatch.setenv("INPUT_POST_PR_COMMENT", "true")
    monkeypatch.setenv("INPUT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("INPUT_MAX_FIX_FILES", "5")
    monkeypatch.setenv("INPUT_ROLLOUT_PROFILE", "unknown-profile")

    exit_code = main()

    assert exit_code == 2
    payload = _parse_github_output(output_file)
    assert payload["classification"] == "UNKNOWN"
    assert payload["pr_created"] == "false"
    assert payload["pr_failure_reason_code"] == "ACTION_INPUT_ERROR"
    assert (
        payload["pr_failure_reason"]
        == "Unsupported rollout_profile 'unknown-profile'. Expected 'safe-github-rollout'."
    )


def test_action_entrypoint_rejects_ambiguous_validated_change_path(
    tmp_path: Path, monkeypatch
) -> None:
    output_file = tmp_path / "github_output.txt"
    config_path = tmp_path / "ci-rootcause.yml"
    validated_path = tmp_path / "validated_changes.json"
    validated_path.write_text(
        '[{"file":"./src/app.py","content":"print(1)\\n"}]',
        encoding="utf-8",
    )
    config_path.write_text(
        "\n".join(
            [
                "raw_log: pytest failed",
                "raw_diff: diff --git a/a.py b/a.py",
                f"validated_changes_path: {validated_path}",
                f"output_dir: {tmp_path / 'artifacts'}",
                "timestamp: 2026-02-24T00:00:00Z",
                "run_id: gha_8007",
                "commit: abc123",
                "base_commit: abc122",
                "head_commit: abc123",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setenv("INPUT_GITHUB_TOKEN", "dummy-token")
    monkeypatch.setenv("INPUT_CREATE_FIX_PR", "false")
    monkeypatch.setenv("INPUT_POST_PR_COMMENT", "true")
    monkeypatch.setenv("INPUT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("INPUT_MAX_FIX_FILES", "5")

    exit_code = main()

    assert exit_code == 2
    payload = _parse_github_output(output_file)
    assert payload["pr_failure_reason_code"] == "ACTION_INPUT_ERROR"
    assert "Dot-segment path syntax is not allowed" in payload["pr_failure_reason"]
