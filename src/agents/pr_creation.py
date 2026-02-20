from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol


class ProviderAdapterError(RuntimeError):
    """Raised when git provider command execution fails."""


class BranchCreationError(RuntimeError):
    """Raised when the fix branch cannot be created."""


class PatchApplicationError(RuntimeError):
    """Raised when validated file changes cannot be applied safely."""


class GitCommandRunner(Protocol):
    def run(self, args: list[str], cwd: Path) -> None:
        """Execute a git command."""


@dataclass(frozen=True)
class BranchCreationPlan:
    base_ref: str
    head_ref: str
    pr_branch: str


@dataclass(frozen=True)
class ValidatedFileChange:
    file: str
    content: str


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


def _normalize_repo_relative_path(file_path: str) -> str:
    normalized_input = file_path.strip()
    if not normalized_input:
        raise PatchApplicationError("Change file path must not be empty")
    candidate = Path(normalized_input)
    if candidate == Path("."):
        raise PatchApplicationError("Change file path must not be empty")
    if candidate.is_absolute():
        raise PatchApplicationError(f"Absolute paths are not allowed: {file_path}")
    if ".." in candidate.parts:
        raise PatchApplicationError(f"Parent directory traversal is not allowed: {file_path}")
    return candidate.as_posix()


def _extract_evidence_files(payload: dict[str, Any]) -> set[str]:
    explicit = payload.get("allowed_files")
    if explicit is not None:
        return {_normalize_repo_relative_path(str(item)) for item in explicit}

    primary = payload.get("primary_root_cause", {})
    evidence = primary.get("evidence", [])
    files = set()
    for item in evidence:
        file_path = str(item.get("file", "")).strip()
        if file_path:
            files.add(_normalize_repo_relative_path(file_path))
    return files


def _extract_validated_changes(payload: dict[str, Any]) -> list[ValidatedFileChange]:
    raw_changes = payload.get("validated_changes", [])
    changes: list[ValidatedFileChange] = []
    for change in raw_changes:
        file_path = _normalize_repo_relative_path(str(change["file"]))
        content = str(change["content"])
        changes.append(ValidatedFileChange(file=file_path, content=content))
    return sorted(changes, key=lambda item: item.file)


def _validate_changes_against_evidence(
    changes: list[ValidatedFileChange],
    evidence_files: set[str],
) -> None:
    if not evidence_files:
        raise PatchApplicationError("No evidence-backed files available for PR creation")
    if not changes:
        raise PatchApplicationError("No validated_changes provided for PR creation")

    for change in changes:
        if change.file not in evidence_files:
            raise PatchApplicationError(
                f"Validated change file is outside evidence scope: {change.file}"
            )


def apply_validated_changes(
    changes: list[ValidatedFileChange],
    repo_path: str,
) -> list[str]:
    repo_root = Path(repo_path)
    applied_files: list[str] = []
    for change in changes:
        target = repo_root / change.file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.content, encoding="utf-8")
        applied_files.append(change.file)
    return sorted(applied_files)


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


def _build_commit_message(payload: dict[str, Any], changed_files: Iterable[str]) -> str:
    run_id = str(payload.get("meta", {}).get("run_id", "")).strip() or "unknown-run"
    file_count = len(list(changed_files))
    return f"ci-rootcause: apply evidence-backed fix plan ({run_id}, files={file_count})"


def checkout_fix_branch(
    plan: BranchCreationPlan,
    repo_path: str,
    git_runner: GitCommandRunner | None = None,
) -> None:
    runner = git_runner or SubprocessGitRunner()
    cwd = Path(repo_path)
    try:
        runner.run(["git", "checkout", plan.pr_branch], cwd=cwd)
    except ProviderAdapterError as exc:
        raise BranchCreationError(
            f"Unable to checkout fix branch '{plan.pr_branch}': {exc}"
        ) from exc


def commit_evidence_backed_changes(
    plan: BranchCreationPlan,
    payload: dict[str, Any],
    changed_files: list[str],
    repo_path: str,
    git_runner: GitCommandRunner | None = None,
) -> str:
    runner = git_runner or SubprocessGitRunner()
    cwd = Path(repo_path)
    commit_message = _build_commit_message(payload=payload, changed_files=changed_files)
    sorted_files = sorted(changed_files)

    try:
        runner.run(["git", "add", "--", *sorted_files], cwd=cwd)
        runner.run(["git", "commit", "-m", commit_message], cwd=cwd)
    except ProviderAdapterError as exc:
        raise BranchCreationError(
            f"Unable to commit evidence-backed changes on '{plan.pr_branch}': {exc}"
        ) from exc

    return commit_message


def run_pr_creation(
    payload: dict[str, Any],
    repo_path: str = ".",
    git_runner: GitCommandRunner | None = None,
) -> dict[str, Any]:
    if not bool(payload.get("create_fix_pr", False)):
        return {
            "pr_created": False,
            "pr_url": None,
            "pr_number": None,
            "pr_branch": None,
            "failure_reason": "create_fix_pr=false",
        }

    evidence_files = _extract_evidence_files(payload)
    changes = _extract_validated_changes(payload)
    _validate_changes_against_evidence(changes=changes, evidence_files=evidence_files)

    plan = build_branch_creation_plan(payload)
    created_branch = create_fix_branch(plan=plan, repo_path=repo_path, git_runner=git_runner)
    checkout_fix_branch(plan=plan, repo_path=repo_path, git_runner=git_runner)
    changed_files = apply_validated_changes(changes=changes, repo_path=repo_path)
    commit_message = commit_evidence_backed_changes(
        plan=plan,
        payload=payload,
        changed_files=changed_files,
        repo_path=repo_path,
        git_runner=git_runner,
    )

    return {
        "pr_created": False,
        "pr_url": None,
        "pr_number": None,
        "pr_branch": created_branch,
        "failure_reason": "Branch and commit created; PR opening flow not implemented yet",
        "commit_message": commit_message,
    }
