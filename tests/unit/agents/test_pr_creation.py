from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.agents.pr_creation import (
    BranchCreationError,
    BranchCreationPlan,
    ProviderAdapterError,
    build_branch_creation_plan,
    build_fix_branch_name,
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
