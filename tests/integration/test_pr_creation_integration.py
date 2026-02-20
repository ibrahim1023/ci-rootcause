from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.agents.pr_creation import ProviderAdapterError, run_pr_creation


@dataclass
class FakeGitRunner:
    fail_on: set[str]

    def run(self, args: list[str], cwd: Path) -> None:
        del cwd
        joined = " ".join(args)
        for pattern in self.fail_on:
            if pattern in joined:
                raise ProviderAdapterError(f"Git command failed ({joined}): 1")


@dataclass
class FakeGitHubClient:
    existing: dict | None
    created: dict | None
    create_calls: int = 0

    def find_open_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        head_branch: str,
        base_branch: str,
    ) -> dict | None:
        del owner, repo, head_branch, base_branch
        return self.existing

    def create_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
    ) -> dict:
        del owner, repo, title, body, head_branch, base_branch
        self.create_calls += 1
        if self.created is None:
            raise AssertionError("created payload missing")
        return self.created


def _base_payload() -> dict:
    return {
        "create_fix_pr": True,
        "repository": "acme/repo",
        "target_branch": "main",
        "summary": "Type mismatch in math module",
        "classification": "TYPECHECK",
        "confidence": 0.73,
        "primary_root_cause": {"title": "Invalid return type in src/core/math.py"},
        "meta": {
            "base_commit": "abc123deadbeef",
            "head_commit": "def456feedface",
            "run_id": "gha_integration_1",
        },
        "allowed_files": ["src/core/math.py"],
        "validated_changes": [
            {"file": "src/core/math.py", "content": "def calc() -> int:\n    return 7\n"}
        ],
        "github_token": "token-for-wrapper-mode",
    }


def test_pr_creation_dry_run_mode(tmp_path: Path) -> None:
    payload = _base_payload() | {"dry_run": True}
    result = run_pr_creation(
        payload=payload,
        repo_path=str(tmp_path),
        git_runner=FakeGitRunner(fail_on={"show-ref"}),
    )

    assert result["pr_created"] is False
    assert result["failure_reason"] == "dry_run=true"
    assert result["pr_branch"] == "ci-rootcause/fix/abc123deadbe-def456feedfa"
    assert (tmp_path / "src/core/math.py").exists()


def test_pr_creation_live_wrapper_mode_with_duplicate_protection(tmp_path: Path) -> None:
    payload = _base_payload()
    client = FakeGitHubClient(
        existing={"html_url": "https://github.com/acme/repo/pull/33", "number": 33},
        created={"html_url": "https://github.com/acme/repo/pull/44", "number": 44},
    )
    result = run_pr_creation(
        payload=payload,
        repo_path=str(tmp_path),
        git_runner=FakeGitRunner(fail_on={"show-ref"}),
        github_client=client,
    )

    assert result["pr_created"] is True
    assert result["pr_number"] == 33
    assert result["pr_url"] == "https://github.com/acme/repo/pull/33"
    assert client.create_calls == 0
