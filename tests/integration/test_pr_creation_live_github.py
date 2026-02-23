from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest

from src.agents.pr_creation import run_pr_creation


def _git(repo_path: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


@pytest.mark.live_github
def test_live_github_pr_creation_and_idempotency() -> None:
    if os.getenv("CI_ROOTCAUSE_LIVE_GITHUB") != "1":
        pytest.skip("set CI_ROOTCAUSE_LIVE_GITHUB=1 to run live GitHub integration test")

    repo_path_raw = os.getenv("CI_ROOTCAUSE_LIVE_REPO_PATH", "").strip()
    repository = os.getenv("CI_ROOTCAUSE_LIVE_REPOSITORY", "").strip()
    github_token = os.getenv("CI_ROOTCAUSE_LIVE_GITHUB_TOKEN", "").strip()
    target_branch = os.getenv("CI_ROOTCAUSE_LIVE_TARGET_BRANCH", "main").strip()

    if not repo_path_raw:
        pytest.skip("CI_ROOTCAUSE_LIVE_REPO_PATH is required for live GitHub test")
    if not repository or "/" not in repository:
        pytest.skip("CI_ROOTCAUSE_LIVE_REPOSITORY must be owner/repo")
    if not github_token:
        pytest.skip("CI_ROOTCAUSE_LIVE_GITHUB_TOKEN is required for live GitHub test")

    repo_path = Path(repo_path_raw).resolve()
    if not repo_path.exists():
        pytest.skip(f"repo path does not exist: {repo_path}")

    head_commit = _git(repo_path, "rev-parse", "HEAD")
    base_commit = _git(repo_path, "rev-parse", "HEAD~1")
    run_id = f"live-{uuid.uuid4().hex[:12]}"
    change_file = f"tmp/ci-rootcause-live-{run_id}.txt"

    payload = {
        "create_fix_pr": True,
        "repository": repository,
        "target_branch": target_branch,
        "summary": "live GitHub integration test for ci-rootcause PR creation",
        "classification": "TEST",
        "confidence": 0.95,
        "min_pr_confidence": 0.75,
        "primary_root_cause": {"title": "live integration smoke validation"},
        "meta": {
            "base_commit": base_commit,
            "head_commit": head_commit,
            "run_id": run_id,
        },
        "allowed_files": [change_file],
        "validated_changes": [{"file": change_file, "content": f"run_id={run_id}\n"}],
        "github_token": github_token,
    }

    first = run_pr_creation(payload=payload, repo_path=str(repo_path))
    assert first["pr_created"] is True
    assert first["pr_number"] is not None
    assert first["pr_url"]
    assert first["pr_branch"]

    second = run_pr_creation(payload=payload, repo_path=str(repo_path))
    assert second["pr_created"] is True
    assert second["pr_number"] == first["pr_number"]
    assert second["pr_url"] == first["pr_url"]
    assert second["commit_message"] is None
