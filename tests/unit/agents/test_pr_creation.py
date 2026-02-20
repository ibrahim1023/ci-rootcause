from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.agents.pr_creation import (
    BranchCreationError,
    BranchCreationPlan,
    PatchApplicationError,
    ProviderAdapterError,
    ValidatedFileChange,
    apply_validated_changes,
    build_branch_creation_plan,
    build_fix_branch_name,
    commit_evidence_backed_changes,
    create_fix_branch,
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


def test_create_fix_branch_rejects_existing_branch(tmp_path: Path) -> None:
    runner = FakeGitRunner(fail_on=set(), seen=[])
    plan = BranchCreationPlan(
        base_ref="abc123deadbeef",
        head_ref="def456feedface",
        pr_branch="ci-rootcause/fix/abc123deadbe-def456feedfa",
    )

    with pytest.raises(BranchCreationError, match="already exists"):
        create_fix_branch(plan=plan, repo_path=str(tmp_path), git_runner=runner)


def test_run_pr_creation_returns_skip_when_disabled() -> None:
    result = run_pr_creation(payload={"create_fix_pr": False})

    assert result == {
        "pr_created": False,
        "pr_url": None,
        "pr_number": None,
        "pr_branch": None,
        "failure_reason": "create_fix_pr=false",
    }


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
    assert result["failure_reason"] == (
        "Branch and commit created; PR opening flow not implemented yet"
    )
    assert result["commit_message"] == (
        "ci-rootcause: apply evidence-backed fix plan (gha_555, files=1)"
    )
    assert ["git", "checkout", "ci-rootcause/fix/abc123deadbe-def456feedfa"] in runner.seen
    assert (tmp_path / "src/core/math.py").read_text(encoding="utf-8") == (
        "def calc() -> int:\n    return 1\n"
    )
