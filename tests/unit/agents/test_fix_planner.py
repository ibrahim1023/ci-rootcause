import pytest

from src.agents.fix_planner import run_fix_planner


def _base_payload() -> dict:
    return {
        "classification": "TYPECHECK",
        "primary_root_cause": {
            "title": "Incompatible return type in src/core/math.py",
            "evidence": [{"file": "src/core/math.py", "line": 42}],
            "confidence": 0.82,
        },
    }


def test_fix_planner_generates_evidence_backed_steps() -> None:
    output = run_fix_planner(_base_payload())

    assert len(output["fix_steps"]) == 1
    assert output["fix_steps"][0]["file"] == "src/core/math.py"
    assert len(output["patch_plan"]) == 1
    assert output["patch_plan"][0]["operation"] == "modify"


def test_fix_planner_rejects_evidence_outside_allowed_scope() -> None:
    payload = _base_payload()
    payload["allowed_files"] = ["src/other.py"]

    with pytest.raises(ValueError, match="outside allowed fix scope"):
        run_fix_planner(payload)


def test_fix_planner_rejects_empty_evidence_even_with_allowed_files() -> None:
    payload = _base_payload()
    payload["primary_root_cause"]["evidence"] = []
    payload["allowed_files"] = ["src/core/math.py"]

    with pytest.raises(ValueError, match="No evidence-backed files"):
        run_fix_planner(payload)


def test_fix_planner_rejects_speculative_candidate_file() -> None:
    payload = _base_payload()
    payload["candidate_fix_steps"] = [
        {
            "file": "src/speculative.py",
            "instruction": "Change src/speculative.py to resolve error",
            "reason": "guess",
        }
    ]

    with pytest.raises(ValueError, match="Speculative file reference rejected"):
        run_fix_planner(payload)


def test_fix_planner_rejects_hidden_speculative_reference_in_instruction() -> None:
    payload = _base_payload()
    payload["candidate_fix_steps"] = [
        {
            "file": "src/core/math.py",
            "instruction": "Also update src/secret/file.py for consistency",
            "reason": "guess",
        }
    ]

    with pytest.raises(ValueError, match="in instruction"):
        run_fix_planner(payload)


def test_fix_planner_output_contains_constrained_prompt_and_schema() -> None:
    output = run_fix_planner(_base_payload())

    assert "constrained" in output["prompt_template"].lower()
    assert output["output_schema"]["type"] == "object"
    assert "fix_steps" in output["output_schema"]["required"]


def test_fix_planner_suggests_retry_isolate_quarantine_for_flaky_tests() -> None:
    output = run_fix_planner(
        {
            "classification": "TEST",
            "primary_root_cause": {
                "title": "tests/test_api.py::test_retry failed intermittently",
                "evidence": [{"file": "tests/test_api.py", "line": 12}],
            },
            "flaky_test_detection": {
                "detected": True,
                "matched_failure_runs": 2,
                "unique_failure_signatures": 2,
            },
        }
    )

    instruction = output["fix_steps"][0]["instruction"].lower()
    assert "retry" in instruction
    assert "isolate" in instruction
    assert "quarantine" in instruction
    assert "speculative code changes" in output["fix_steps"][0]["reason"].lower()


def test_fix_planner_dependency_hint_uses_lockfile_command_when_evidence_is_strong() -> None:
    output = run_fix_planner(
        {
            "classification": "DEPENDENCY",
            "primary_root_cause": {
                "title": "npm ERR! code ERESOLVE",
                "evidence": [{"file": "package-lock.json", "line": 1}],
            },
            "dependency_change_flags": {
                "has_lockfile_change": True,
                "has_manifest_change": True,
                "changed_lockfiles": ["package-lock.json"],
                "changed_manifests": ["package.json"],
            },
        }
    )

    instruction = output["fix_steps"][0]["instruction"]
    assert "npm ci" in instruction


def test_fix_planner_post_processing_is_deterministic() -> None:
    payload = _base_payload()
    payload["candidate_fix_steps"] = [
        {
            "file": "src/core/math.py",
            "instruction": "  B step   ",
            "reason": " two  spaces ",
        },
        {
            "file": "src/core/math.py",
            "instruction": "A step",
            "reason": "one",
        },
    ]

    first = run_fix_planner(payload)
    second = run_fix_planner(payload)

    assert first == second
    assert first["fix_steps"][0]["instruction"] == "A step"
    assert first["fix_steps"][1]["instruction"] == "B step"


def test_fix_planner_patch_plan_order_is_deterministic() -> None:
    payload = _base_payload()
    payload["candidate_fix_steps"] = [
        {
            "file": "src/core/zeta.py",
            "instruction": "  Last step ",
            "reason": "r3",
        },
        {
            "file": "src/core/alpha.py",
            "instruction": " First step",
            "reason": "r1",
        },
        {
            "file": "src/core/alpha.py",
            "instruction": "Second  step",
            "reason": "r2",
        },
    ]
    payload["primary_root_cause"]["evidence"] = [
        {"file": "src/core/alpha.py", "line": 10},
        {"file": "src/core/zeta.py", "line": 20},
    ]
    payload["allowed_files"] = ["src/core/zeta.py", "src/core/alpha.py"]

    first = run_fix_planner(payload)
    second = run_fix_planner(payload)

    assert first == second
    assert [item["file"] for item in first["patch_plan"]] == [
        "src/core/alpha.py",
        "src/core/zeta.py",
    ]
    assert [item["summary"] for item in first["patch_plan"]] == [
        "First step; Second step",
        "Last step",
    ]


def test_fix_planner_patch_plan_infers_operation_types() -> None:
    payload = _base_payload()
    payload["candidate_fix_steps"] = [
        {
            "file": "src/core/new_file.py",
            "instruction": "Create file with deterministic helper implementation",
            "reason": "r1",
        }
    ]
    payload["primary_root_cause"]["evidence"] = [
        {"file": "src/core/new_file.py", "line": 1},
    ]

    output = run_fix_planner(payload)

    assert output["patch_plan"] == [
        {
            "file": "src/core/new_file.py",
            "operation": "create",
            "summary": "Create file with deterministic helper implementation",
        }
    ]


def test_fix_planner_patch_plan_rejects_conflicting_file_operations() -> None:
    payload = _base_payload()
    payload["candidate_fix_steps"] = [
        {
            "file": "src/core/math.py",
            "instruction": "Delete obsolete function implementation",
            "reason": "r1",
        },
        {
            "file": "src/core/math.py",
            "instruction": "Update callsites to use new signature",
            "reason": "r2",
        },
    ]

    with pytest.raises(ValueError, match="Conflicting patch operations for file"):
        run_fix_planner(payload)
