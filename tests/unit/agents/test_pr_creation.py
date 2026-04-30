from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib import error
from urllib import request as urllib_request

import pytest

from src.agents.pr_creation import (
    PR_REASON_CONFIDENCE_BELOW_THRESHOLD,
    PR_REASON_CREATE_FIX_PR_DISABLED,
    PR_REASON_DRY_RUN,
    PR_REASON_MAX_FIX_FILES_EXCEEDED,
    PR_REASON_OFFLINE_ONLY,
    PR_REASON_VALIDATION_FAILED,
    BranchCreationPlan,
    GitHubAPIError,
    GitHubRateLimitError,
    GitHubRESTClient,
    GitHubTransientError,
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
    push_fix_branch,
    run_pr_creation,
)


def test_pr_reason_code_literals_remain_stable() -> None:
    assert {
        PR_REASON_CREATE_FIX_PR_DISABLED,
        PR_REASON_OFFLINE_ONLY,
        PR_REASON_CONFIDENCE_BELOW_THRESHOLD,
        PR_REASON_DRY_RUN,
        PR_REASON_MAX_FIX_FILES_EXCEEDED,
        PR_REASON_VALIDATION_FAILED,
    } == {
        "CREATE_FIX_PR_DISABLED",
        "OFFLINE_ONLY",
        "CONFIDENCE_BELOW_THRESHOLD",
        "DRY_RUN",
        "MAX_FIX_FILES_EXCEEDED",
        "VALIDATION_FAILED",
    }


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


def test_push_fix_branch_runs_expected_git_command(tmp_path: Path) -> None:
    runner = FakeGitRunner(fail_on=set(), seen=[])
    plan = BranchCreationPlan(
        base_ref="abc123deadbeef",
        head_ref="def456feedface",
        pr_branch="ci-rootcause/fix/abc123deadbe-def456feedfa",
    )

    push_fix_branch(plan=plan, repo_path=str(tmp_path), git_runner=runner)

    assert runner.seen == [["git", "push", "-u", "origin", plan.pr_branch]]


def test_run_pr_creation_returns_skip_when_disabled() -> None:
    result = run_pr_creation(payload={"create_fix_pr": False})

    assert result == {
        "pr_created": False,
        "pr_url": None,
        "pr_number": None,
        "pr_branch": None,
        "failure_reason_code": PR_REASON_CREATE_FIX_PR_DISABLED,
        "failure_reason": "create_fix_pr=false",
    }


def test_run_pr_creation_skips_when_confidence_is_below_threshold() -> None:
    result = run_pr_creation(
        payload={
            "create_fix_pr": True,
            "confidence": 0.6,
            "min_pr_confidence": 0.75,
        }
    )

    assert result["pr_created"] is False
    assert result["pr_branch"] is None
    assert result["failure_reason_code"] == PR_REASON_CONFIDENCE_BELOW_THRESHOLD
    assert result["failure_reason"] == "confidence 0.6000 is below threshold 0.7500"


def test_run_pr_creation_skips_when_offline_only_mode_is_enabled() -> None:
    result = run_pr_creation(
        payload={
            "create_fix_pr": True,
            "offline_only": True,
            "confidence": 0.95,
            "min_pr_confidence": 0.75,
        }
    )

    assert result["pr_created"] is False
    assert result["pr_branch"] is None
    assert result["failure_reason_code"] == PR_REASON_OFFLINE_ONLY
    assert result["failure_reason"] == "offline_only=true"


def test_run_pr_creation_uses_stable_max_fix_files_disabled_reason_code() -> None:
    result = run_pr_creation(
        payload={
            "create_fix_pr": False,
            "create_fix_pr_disabled_reason": "max_fix_files_exceeded",
        }
    )

    assert result["failure_reason_code"] == PR_REASON_MAX_FIX_FILES_EXCEEDED
    assert result["failure_reason"] == "validated changes exceed max_fix_files limit"


def test_run_pr_creation_enforces_max_fix_files_on_final_changes() -> None:
    result = run_pr_creation(
        payload={
            "create_fix_pr": True,
            "confidence": 0.9,
            "min_pr_confidence": 0.75,
            "max_fix_files": 1,
            "base_ref": "abc123deadbeef",
            "head_ref": "def456feedface",
            "allowed_files": ["src/a.py", "src/b.py"],
            "validated_changes": [
                {"file": "src/a.py", "content": "print('a')\n"},
                {"file": "src/b.py", "content": "print('b')\n"},
            ],
        }
    )

    assert result["pr_created"] is False
    assert result["pr_branch"] is None
    assert result["failure_reason_code"] == PR_REASON_MAX_FIX_FILES_EXCEEDED
    assert result["failure_reason"] == "validated changes exceed max_fix_files limit"


def test_run_pr_creation_reports_app_pr_mode_not_enabled_reason() -> None:
    result = run_pr_creation(
        payload={
            "create_fix_pr": False,
            "create_fix_pr_disabled_reason": "app_pr_mode_not_enabled",
        }
    )

    assert result["failure_reason_code"] == PR_REASON_CREATE_FIX_PR_DISABLED
    assert result["failure_reason"] == "app_pr_mode_not_enabled"


def test_run_pr_creation_requires_validation_commands_in_agentic_mode() -> None:
    result = run_pr_creation(
        payload={
            "create_fix_pr": True,
            "execution_mode": "agentic_assist",
            "confidence": 0.95,
            "min_pr_confidence": 0.75,
        }
    )

    assert result["pr_created"] is False
    assert result["failure_reason_code"] == PR_REASON_VALIDATION_FAILED
    assert result["failure_reason"] == "no validation commands configured for agentic mode"


def test_run_pr_creation_prefers_typecheck_specific_validation_commands(
    tmp_path: Path, monkeypatch
) -> None:
    payload = {
        "create_fix_pr": True,
        "execution_mode": "agentic_assist",
        "validation_commands": ["pytest"],
        "typecheck_validation_commands": ["python -m mypy src/core/math.py"],
        "repository": "acme/repo",
        "target_branch": "main",
        "summary": "Type mismatch in core module",
        "classification": "TYPECHECK",
        "confidence": 0.95,
        "min_pr_confidence": 0.75,
        "primary_root_cause": {
            "title": "Invalid return type",
            "evidence": [{"file": "src/core/math.py", "line": 1, "signal": "type mismatch"}],
        },
        "meta": {
            "base_commit": "abc123deadbeef",
            "head_commit": "def456feedface",
            "run_id": "gha_validation_specific",
        },
        "allowed_files": ["src/core/math.py"],
        "validated_changes": [
            {"file": "src/core/math.py", "content": "def calc() -> int:\n    return 7\n"}
        ],
        "github_token": "token",
        "dry_run": True,
    }
    seen: list[list[str]] = []

    def _subprocess_ok(args, cwd, check, capture_output, text):  # noqa: ANN001
        del cwd, check, capture_output, text
        seen.append(args)
        return None

    monkeypatch.setattr("src.agents.pr_creation.subprocess.run", _subprocess_ok)

    result = run_pr_creation(
        payload=payload,
        repo_path=str(tmp_path),
        git_runner=FakeGitRunner(fail_on={"show-ref"}, seen=[]),
    )

    assert result["failure_reason_code"] == PR_REASON_DRY_RUN
    assert seen == [["python", "-m", "mypy", "src/core/math.py"]]


def test_run_pr_creation_returns_validation_failed_when_command_fails(
    tmp_path: Path, monkeypatch
) -> None:
    payload = {
        "create_fix_pr": True,
        "execution_mode": "agentic_assist",
        "validation_commands": ['python -c "raise SystemExit(1)"'],
        "repository": "acme/repo",
        "target_branch": "main",
        "summary": "Type mismatch in core module",
        "classification": "TYPECHECK",
        "confidence": 0.95,
        "min_pr_confidence": 0.75,
        "primary_root_cause": {
            "title": "Invalid return type",
            "evidence": [{"file": "src/core/math.py", "line": 1, "signal": "type mismatch"}],
        },
        "meta": {
            "base_commit": "abc123deadbeef",
            "head_commit": "def456feedface",
            "run_id": "gha_validation_1",
        },
        "allowed_files": ["src/core/math.py"],
        "validated_changes": [
            {"file": "src/core/math.py", "content": "def calc() -> int:\n    return 7\n"}
        ],
        "github_token": "token",
        "dry_run": True,
    }

    def _failing_subprocess(*args, **kwargs):  # noqa: ANN002, ANN003
        raise __import__("subprocess").CalledProcessError(
            returncode=1,
            cmd=args[0] if args else kwargs.get("args", []),
            output="",
            stderr="validation failed",
        )

    monkeypatch.setattr("src.agents.pr_creation.subprocess.run", _failing_subprocess)

    result = run_pr_creation(
        payload=payload,
        repo_path=str(tmp_path),
        git_runner=FakeGitRunner(fail_on={"show-ref"}, seen=[]),
    )

    assert result["pr_created"] is False
    assert result["failure_reason_code"] == PR_REASON_VALIDATION_FAILED
    assert "validation command failed" in str(result["failure_reason"])


def test_run_pr_creation_infers_targeted_test_validation_command(
    tmp_path: Path, monkeypatch
) -> None:
    test_file = tmp_path / "tests" / "test_math.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    payload = {
        "create_fix_pr": True,
        "execution_mode": "agentic_assist",
        "repository": "acme/repo",
        "target_branch": "main",
        "summary": "Failing pytest assertion",
        "classification": "TEST",
        "confidence": 0.95,
        "min_pr_confidence": 0.75,
        "primary_root_cause": {
            "title": "Assertion failed",
            "evidence": [{"file": "tests/test_math.py", "line": 1, "signal": "assertion"}],
        },
        "meta": {
            "base_commit": "abc123deadbeef",
            "head_commit": "def456feedface",
            "run_id": "gha_validation_test",
        },
        "allowed_files": ["tests/test_math.py"],
        "validated_changes": [
            {"file": "tests/test_math.py", "content": "def test_ok():\n    assert True\n"}
        ],
        "github_token": "token",
        "dry_run": True,
    }
    seen: list[list[str]] = []

    def _subprocess_ok(args, cwd, check, capture_output, text):  # noqa: ANN001
        del cwd, check, capture_output, text
        seen.append(args)
        return None

    monkeypatch.setattr("src.agents.pr_creation.subprocess.run", _subprocess_ok)

    result = run_pr_creation(
        payload=payload,
        repo_path=str(tmp_path),
        git_runner=FakeGitRunner(fail_on={"show-ref"}, seen=[]),
    )

    assert result["failure_reason_code"] == PR_REASON_DRY_RUN
    assert seen == [["pytest", "tests/test_math.py"]]


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


def test_run_pr_creation_rejects_out_of_range_confidence_threshold() -> None:
    with pytest.raises(
        GuardrailViolationError,
        match="min_pr_confidence must be between 0.0 and 1.0",
    ):
        run_pr_creation(
            payload={
                "create_fix_pr": True,
                "confidence": 0.9,
                "min_pr_confidence": 1.2,
            }
        )


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
        "confidence": 0.9,
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


def test_run_pr_creation_rejects_change_outside_fix_plan_scope(tmp_path: Path) -> None:
    payload = {
        "create_fix_pr": True,
        "confidence": 0.9,
        "base_ref": "abc123deadbeef",
        "head_ref": "def456feedface",
        "allowed_files": ["src/evidence.py", "src/other.py"],
        "fix_steps": [
            {
                "file": "src/evidence.py",
                "instruction": "adjust behavior",
                "reason": "root cause evidence",
            }
        ],
        "patch_plan": [
            {
                "file": "src/evidence.py",
                "operation": "modify",
                "summary": "adjust behavior",
            }
        ],
        "validated_changes": [{"file": "src/other.py", "content": "print('x')\n"}],
    }

    with pytest.raises(PatchApplicationError, match="outside fix plan scope"):
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
        "confidence": 0.9,
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


@pytest.mark.parametrize(
    ("bad_path", "error_message"),
    [
        ("/tmp/abs.py", "Absolute paths are not allowed"),
        ("../escape.py", "Parent directory traversal is not allowed"),
        ("./src/file.py", "Dot-segment path syntax is not allowed"),
        ("src//file.py", "Duplicate path separators are not allowed"),
        ("src\\file.py", "Backslashes are not allowed in file paths"),
    ],
)
def test_run_pr_creation_rejects_ambiguous_change_paths(
    tmp_path: Path, bad_path: str, error_message: str
) -> None:
    payload = {
        "create_fix_pr": True,
        "confidence": 0.9,
        "base_ref": "abc123deadbeef",
        "head_ref": "def456feedface",
        "allowed_files": [bad_path],
        "validated_changes": [{"file": bad_path, "content": "print('x')\n"}],
    }

    with pytest.raises(PatchApplicationError, match=error_message):
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
        "confidence": 0.9,
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
    assert result["failure_reason_code"] == PR_REASON_DRY_RUN
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
        "confidence": 0.9,
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
    assert result["failure_reason_code"] == ""
    assert result["failure_reason"] is None
    assert [
        "git",
        "push",
        "-u",
        "origin",
        "ci-rootcause/fix/abc123deadbe-def456feedfa",
    ] in runner.seen


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
        "confidence": 0.9,
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
    assert result["failure_reason_code"] == ""
    assert result["commit_message"] is None
    assert runner.seen == []


class _HTTPResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None

    def read(self) -> bytes:
        return self._payload


def _http_error(
    *,
    code: int,
    message: str,
    body: str,
    headers: dict[str, str] | None = None,
) -> error.HTTPError:
    return error.HTTPError(
        url="https://api.github.test/failure",
        code=code,
        msg=message,
        hdrs=headers or {},
        fp=BytesIO(body.encode("utf-8")),
    )


def test_github_rest_client_retries_transient_http_errors(monkeypatch) -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    def fake_urlopen(req: urllib_request.Request, timeout: int):
        del req, timeout
        calls["count"] += 1
        if calls["count"] < 3:
            raise _http_error(code=503, message="Service Unavailable", body='{"message":"retry"}')
        return _HTTPResponse(b"[]")

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)
    monkeypatch.setattr("src.agents.pr_creation.time.sleep", fake_sleep)

    client = GitHubRESTClient(token="token", api_base="https://api.github.test", max_retries=3)
    payload = client.find_open_pull_request(
        owner="acme",
        repo="repo",
        head_branch="feature/x",
        base_branch="main",
    )

    assert payload is None
    assert calls["count"] == 3
    assert sleeps == [0.5, 1.0]


def test_github_rest_client_raises_typed_rate_limit_after_retries(monkeypatch) -> None:
    sleeps: list[float] = []

    def fake_urlopen(req: urllib_request.Request, timeout: int):
        del req, timeout
        raise _http_error(
            code=429,
            message="Too Many Requests",
            body='{"message":"rate limit"}',
            headers={"Retry-After": "2"},
        )

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)
    monkeypatch.setattr("src.agents.pr_creation.time.sleep", fake_sleep)

    client = GitHubRESTClient(
        token="token",
        api_base="https://api.github.test",
        max_retries=2,
        backoff_seconds=0.25,
    )
    with pytest.raises(GitHubRateLimitError):
        client.find_open_pull_request(
            owner="acme",
            repo="repo",
            head_branch="feature/x",
            base_branch="main",
        )

    assert sleeps == [2.0, 2.0]


def test_github_rest_client_raises_typed_transient_on_network_exhaustion(monkeypatch) -> None:
    sleeps: list[float] = []

    def fake_urlopen(req: urllib_request.Request, timeout: int):
        del req, timeout
        raise error.URLError("temporary failure")

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)
    monkeypatch.setattr("src.agents.pr_creation.time.sleep", fake_sleep)

    client = GitHubRESTClient(
        token="token",
        api_base="https://api.github.test",
        max_retries=1,
        backoff_seconds=0.2,
    )
    with pytest.raises(GitHubTransientError):
        client.find_open_pull_request(
            owner="acme",
            repo="repo",
            head_branch="feature/x",
            base_branch="main",
        )

    assert sleeps == [0.2]


def test_github_rest_client_raises_non_retryable_api_error(monkeypatch) -> None:
    def fake_urlopen(req: urllib_request.Request, timeout: int):
        del req, timeout
        raise _http_error(code=422, message="Unprocessable Entity", body='{"message":"invalid"}')

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)

    client = GitHubRESTClient(token="token", api_base="https://api.github.test", max_retries=3)
    with pytest.raises(GitHubAPIError):
        client.find_open_pull_request(
            owner="acme",
            repo="repo",
            head_branch="feature/x",
            base_branch="main",
        )
