from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.agents.pr_creation import (
    BranchCreationPlan,
    GuardrailViolationError,
    PatchApplicationError,
    ProviderAdapterError,
    PullRequestRequest,
    ValidatedFileChange,
    apply_validated_changes,
    build_branch_creation_plan,
    build_fix_branch_name,
    build_pull_request_request,
    commit_evidence_backed_changes,
    create_fix_branch,
    create_or_reuse_pull_request,
    find_existing_pull_request,
    run_pr_creation,
)


@dataclass
class FakeGitRunner:
    fail_on: set[str]
    seen: list[list[str]]

    def run(self, args: list[str], cwd: Path) -> None:
        self.seen.append(args)
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


def test_build_fix_branch_name_is_deterministic() -> None:
    branch = build_fix_branch_name(base_ref="ABC123deadbeef", head_ref="def456feedface")
    assert branch == "ci-rootcause/fix/abc123deadbe-def456feedfa"


def test_build_branch_creation_plan_uses_meta_refs() -> None:
    payload = {
        "create_fix_pr": True,
        "meta": {
            "base_commit": "abc123deadbeef",
            "head_commit": "def456feedface",
        },
    }

    plan = build_branch_creation_plan(payload)

    assert plan == BranchCreationPlan(
        base_ref="abc123deadbeef",
        head_ref="def456feedface",
        pr_branch="ci-rootcause/fix/abc123deadbe-def456feedfa",
    )


def test_create_fix_branch_runs_expected_git_commands(tmp_path: Path) -> None:
    runner = FakeGitRunner(fail_on={"show-ref"}, seen=[])
    plan = BranchCreationPlan(
        base_ref="abc123deadbeef",
        head_ref="def456feedface",
        pr_branch="ci-rootcause/fix/abc123deadbe-def456feedfa",
    )

    branch = create_fix_branch(plan=plan, repo_path=str(tmp_path), git_runner=runner)

    assert branch == plan.pr_branch
    assert runner.seen == [
        ["git", "rev-parse", "--verify", "abc123deadbeef"],
        [
            "git",
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/ci-rootcause/fix/abc123deadbe-def456feedfa",
        ],
        ["git", "branch", "ci-rootcause/fix/abc123deadbe-def456feedfa", "abc123deadbeef"],
    ]


def test_create_fix_branch_is_idempotent_when_branch_exists(tmp_path: Path) -> None:
    runner = FakeGitRunner(fail_on=set(), seen=[])
    plan = BranchCreationPlan(
        base_ref="abc123deadbeef",
        head_ref="def456feedface",
        pr_branch="ci-rootcause/fix/abc123deadbe-def456feedfa",
    )

    branch = create_fix_branch(plan=plan, repo_path=str(tmp_path), git_runner=runner)

    assert branch == plan.pr_branch
    assert runner.seen == [
        ["git", "rev-parse", "--verify", "abc123deadbeef"],
        [
            "git",
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/ci-rootcause/fix/abc123deadbe-def456feedfa",
        ],
    ]


def test_run_pr_creation_returns_skip_when_disabled() -> None:
    result = run_pr_creation(payload={"create_fix_pr": False})

    assert result == {
        "pr_created": False,
        "pr_url": None,
        "pr_number": None,
        "pr_branch": None,
        "failure_reason": "create_fix_pr=false",
    }


def test_build_pull_request_request_includes_summary_and_confidence() -> None:
    payload = {
        "repository": "acme/ci-rootcause",
        "target_branch": "main",
        "summary": "Typecheck failure in core module",
        "classification": "TYPECHECK",
        "confidence": 0.82,
        "primary_root_cause": {"title": "Invalid return type"},
        "meta": {"run_id": "gha_900"},
    }

    request_payload = build_pull_request_request(
        payload=payload,
        pr_branch="ci-rootcause/fix/abc123-def456",
        changed_files=["src/core/math.py"],
    )

    assert request_payload == PullRequestRequest(
        owner="acme",
        repo="ci-rootcause",
        title="ci-rootcause: suggested fix (gha_900)",
        body=request_payload.body,
        head_branch="ci-rootcause/fix/abc123-def456",
        base_branch="main",
    )
    assert "Classification: `TYPECHECK`" in request_payload.body
    assert "Confidence: `0.8200`" in request_payload.body
    assert "`src/core/math.py`" in request_payload.body


def test_create_or_reuse_pull_request_returns_existing_pr_when_present() -> None:
    existing = {"html_url": "https://github.com/acme/repo/pull/5", "number": 5}
    client = FakeGitHubClient(existing=existing, created=None)

    result = create_or_reuse_pull_request(
        payload={
            "repository": "acme/repo",
            "meta": {"run_id": "gha_222"},
        },
        pr_branch="ci-rootcause/fix/abc123-def456",
        changed_files=["src/core/math.py"],
        github_client=client,
    )

    assert result == existing
    assert client.create_calls == 0


def test_find_existing_pull_request_uses_branch_and_base_context() -> None:
    existing = {"html_url": "https://github.com/acme/repo/pull/8", "number": 8}
    client = FakeGitHubClient(existing=existing, created=None)

    result = find_existing_pull_request(
        payload={
            "repository": "acme/repo",
            "target_branch": "main",
            "meta": {"run_id": "gha_909"},
        },
        pr_branch="ci-rootcause/fix/abc123-def456",
        github_client=client,
    )

    assert result == existing


def test_apply_validated_changes_writes_content_deterministically(tmp_path: Path) -> None:
    changed_files = apply_validated_changes(
        changes=[
            ValidatedFileChange(file="src/b.txt", content="two\n"),
            ValidatedFileChange(file="src/a.txt", content="one\n"),
        ],
        repo_path=str(tmp_path),
    )

    assert changed_files == ["src/a.txt", "src/b.txt"]
    assert (tmp_path / "src/a.txt").read_text(encoding="utf-8") == "one\n"
    assert (tmp_path / "src/b.txt").read_text(encoding="utf-8") == "two\n"


def test_commit_evidence_backed_changes_uses_only_given_files(tmp_path: Path) -> None:
    runner = FakeGitRunner(fail_on=set(), seen=[])
    message = commit_evidence_backed_changes(
        plan=BranchCreationPlan(
            base_ref="abc123deadbeef",
            head_ref="def456feedface",
            pr_branch="ci-rootcause/fix/abc123deadbe-def456feedfa",
        ),
        payload={"meta": {"run_id": "gha_123"}},
        changed_files=["src/b.txt", "src/a.txt"],
        repo_path=str(tmp_path),
        git_runner=runner,
    )

    assert message == "ci-rootcause: apply evidence-backed fix plan (gha_123, files=2)"
    assert runner.seen == [
        ["git", "add", "--", "src/a.txt", "src/b.txt"],
        [
            "git",
            "commit",
            "-m",
            "ci-rootcause: apply evidence-backed fix plan (gha_123, files=2)",
        ],
    ]


def test_run_pr_creation_rejects_non_evidence_file(tmp_path: Path) -> None:
    payload = {
        "create_fix_pr": True,
        "base_ref": "abc123deadbeef",
        "head_ref": "def456feedface",
        "allowed_files": ["src/evidence.py"],
        "validated_changes": [{"file": "src/other.py", "content": "print('x')\n"}],
    }

    with pytest.raises(PatchApplicationError, match="outside evidence scope"):
        run_pr_creation(
            payload=payload,
            repo_path=str(tmp_path),
            git_runner=FakeGitRunner(set(), []),
        )


def test_run_pr_creation_rejects_auto_merge_guardrail(tmp_path: Path) -> None:
    payload = {
        "create_fix_pr": True,
        "auto_merge": True,
    }

    with pytest.raises(GuardrailViolationError, match="auto-merge is prohibited"):
        run_pr_creation(payload=payload, repo_path=str(tmp_path))


def test_run_pr_creation_rejects_empty_change_path(tmp_path: Path) -> None:
    payload = {
        "create_fix_pr": True,
        "base_ref": "abc123deadbeef",
        "head_ref": "def456feedface",
        "allowed_files": ["src/evidence.py"],
        "validated_changes": [{"file": "   ", "content": "print('x')\n"}],
    }

    with pytest.raises(PatchApplicationError, match="must not be empty"):
        run_pr_creation(
            payload=payload,
            repo_path=str(tmp_path),
            git_runner=FakeGitRunner(set(), []),
        )


def test_run_pr_creation_applies_changes_and_commits(tmp_path: Path) -> None:
    runner = FakeGitRunner(fail_on={"show-ref"}, seen=[])
    payload = {
        "create_fix_pr": True,
        "dry_run": True,
        "meta": {
            "base_commit": "abc123deadbeef",
            "head_commit": "def456feedface",
            "run_id": "gha_555",
        },
        "allowed_files": ["src/core/math.py"],
        "validated_changes": [
            {"file": "src/core/math.py", "content": "def calc() -> int:\n    return 1\n"}
        ],
    }

    result = run_pr_creation(payload=payload, repo_path=str(tmp_path), git_runner=runner)

    assert result["pr_branch"] == "ci-rootcause/fix/abc123deadbe-def456feedfa"
    assert result["pr_created"] is False
    assert result["failure_reason"] == "dry_run=true"
    assert result["commit_message"] == (
        "ci-rootcause: apply evidence-backed fix plan (gha_555, files=1)"
    )
    assert ["git", "checkout", "ci-rootcause/fix/abc123deadbe-def456feedfa"] in runner.seen
    assert (tmp_path / "src/core/math.py").read_text(encoding="utf-8") == (
        "def calc() -> int:\n    return 1\n"
    )


def test_run_pr_creation_dry_run_skips_pr_open(tmp_path: Path) -> None:
    runner = FakeGitRunner(fail_on={"show-ref"}, seen=[])
    payload = {
        "create_fix_pr": True,
        "dry_run": True,
        "meta": {
            "base_commit": "abc123deadbeef",
            "head_commit": "def456feedface",
            "run_id": "gha_777",
        },
        "allowed_files": ["src/core/math.py"],
        "validated_changes": [
            {"file": "src/core/math.py", "content": "def calc() -> int:\n    return 2\n"}
        ],
    }

    result = run_pr_creation(payload=payload, repo_path=str(tmp_path), git_runner=runner)

    assert result["pr_created"] is False
    assert result["failure_reason"] == "dry_run=true"
    assert result["pr_url"] is None
    assert result["pr_number"] is None


def test_run_pr_creation_opens_pr_via_client(tmp_path: Path) -> None:
    runner = FakeGitRunner(fail_on={"show-ref"}, seen=[])
    client = FakeGitHubClient(
        existing=None,
        created={"html_url": "https://github.com/acme/repo/pull/12", "number": 12},
    )
    payload = {
        "create_fix_pr": True,
        "repository": "acme/repo",
        "target_branch": "main",
        "summary": "Fix type mismatch",
        "classification": "TYPECHECK",
        "confidence": 0.91,
        "primary_root_cause": {"title": "Invalid return type in src/core/math.py"},
        "meta": {
            "base_commit": "abc123deadbeef",
            "head_commit": "def456feedface",
            "run_id": "gha_888",
        },
        "allowed_files": ["src/core/math.py"],
        "validated_changes": [
            {"file": "src/core/math.py", "content": "def calc() -> int:\n    return 3\n"}
        ],
        "github_token": "unused-in-test",
    }

    result = run_pr_creation(
        payload=payload,
        repo_path=str(tmp_path),
        git_runner=runner,
        github_client=client,
    )

    assert result["pr_created"] is True
    assert result["pr_url"] == "https://github.com/acme/repo/pull/12"
    assert result["pr_number"] == 12
    assert result["failure_reason"] is None


def test_run_pr_creation_short_circuits_when_open_pr_exists(tmp_path: Path) -> None:
    runner = FakeGitRunner(fail_on={"show-ref"}, seen=[])
    client = FakeGitHubClient(
        existing={"html_url": "https://github.com/acme/repo/pull/18", "number": 18},
        created={"html_url": "https://github.com/acme/repo/pull/19", "number": 19},
    )
    payload = {
        "create_fix_pr": True,
        "repository": "acme/repo",
        "target_branch": "main",
        "meta": {
            "base_commit": "abc123deadbeef",
            "head_commit": "def456feedface",
            "run_id": "gha_1000",
        },
        "allowed_files": ["src/core/math.py"],
        "validated_changes": [
            {"file": "src/core/math.py", "content": "def calc() -> int:\n    return 4\n"}
        ],
        "github_token": "unused-in-test",
    }

    result = run_pr_creation(
        payload=payload,
        repo_path=str(tmp_path),
        git_runner=runner,
        github_client=client,
    )

    assert result["pr_created"] is True
    assert result["pr_url"] == "https://github.com/acme/repo/pull/18"
    assert result["pr_number"] == 18
    assert result["commit_message"] is None
    assert runner.seen == []
