from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ProviderAdapterError(RuntimeError):
    """Raised when git provider command execution fails."""


class BranchCreationError(RuntimeError):
    """Raised when the fix branch cannot be created."""


class GitCommandRunner(Protocol):
    def run(self, args: list[str], cwd: Path) -> None:
        """Execute a git command."""


@dataclass(frozen=True)
class BranchCreationPlan:
    base_ref: str
    head_ref: str
    pr_branch: str


def _normalize_ref_segment(value: str) -> str:
    normalized = "".join(ch for ch in value.lower() if ch.isalnum())
    if not normalized:
        raise BranchCreationError("Branch segment must contain at least one alphanumeric character")
    return normalized[:12]


def build_fix_branch_name(base_ref: str, head_ref: str) -> str:
    base_segment = _normalize_ref_segment(base_ref)
    head_segment = _normalize_ref_segment(head_ref)
    return f"ci-rootcause/fix/{base_segment}-{head_segment}"


def build_branch_creation_plan(payload: dict[str, Any]) -> BranchCreationPlan:
    meta = payload.get("meta", {})
    base_ref = str(payload.get("base_ref") or meta.get("base_commit") or "").strip()
    head_ref = str(payload.get("head_ref") or meta.get("head_commit") or "").strip()

    if not base_ref:
        raise BranchCreationError("Missing base_ref or meta.base_commit for branch creation")
    if not head_ref:
        raise BranchCreationError("Missing head_ref or meta.head_commit for branch creation")

    return BranchCreationPlan(
        base_ref=base_ref,
        head_ref=head_ref,
        pr_branch=build_fix_branch_name(base_ref=base_ref, head_ref=head_ref),
    )


class SubprocessGitRunner:
    def run(self, args: list[str], cwd: Path) -> None:
        try:
            subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise ProviderAdapterError(
                f"Git command failed ({' '.join(args)}): {stderr or exc.returncode}"
            ) from exc


def create_fix_branch(
    plan: BranchCreationPlan,
    repo_path: str,
    git_runner: GitCommandRunner | None = None,
) -> str:
    runner = git_runner or SubprocessGitRunner()
    cwd = Path(repo_path)

    try:
        runner.run(["git", "rev-parse", "--verify", plan.base_ref], cwd=cwd)
        runner.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{plan.pr_branch}"],
            cwd=cwd,
        )
    except ProviderAdapterError as exc:
        message = str(exc)
        # `show-ref --verify --quiet` exits non-zero when the branch is absent.
        if "show-ref" in message:
            pass
        else:
            raise BranchCreationError(f"Unable to verify base reference: {exc}") from exc
    else:
        raise BranchCreationError(f"Fix branch already exists: {plan.pr_branch}")

    try:
        runner.run(["git", "branch", plan.pr_branch, plan.base_ref], cwd=cwd)
    except ProviderAdapterError as exc:
        raise BranchCreationError(f"Unable to create fix branch '{plan.pr_branch}': {exc}") from exc

    return plan.pr_branch


def run_pr_creation(payload: dict[str, Any], repo_path: str = ".") -> dict[str, Any]:
    if not bool(payload.get("create_fix_pr", False)):
        return {
            "pr_created": False,
            "pr_url": None,
            "pr_number": None,
            "pr_branch": None,
            "failure_reason": "create_fix_pr=false",
        }

    plan = build_branch_creation_plan(payload)
    created_branch = create_fix_branch(plan=plan, repo_path=repo_path)

    return {
        "pr_created": False,
        "pr_url": None,
        "pr_number": None,
        "pr_branch": created_branch,
        "failure_reason": "Branch created; PR opening flow not implemented yet",
    }
