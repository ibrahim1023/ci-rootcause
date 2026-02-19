from pathlib import Path

from src.agents.diff_analysis import run_diff_analysis


def test_diff_analysis_extracts_changed_files_and_module_mapping() -> None:
    raw = Path("fixtures/diffs/rename-and-modify.diff").read_text()

    output = run_diff_analysis(raw)

    assert output["changed_files"] == ["src/app.py", "src/new_name.py"]
    assert output["module_mapping"]["src/app.py"] == "app"
    assert output["module_mapping"]["src/new_name.py"] == "new_name"


def test_diff_analysis_detects_lockfile_only_dependency_drift() -> None:
    raw = Path("fixtures/diffs/python-lockfile-only.diff").read_text()

    output = run_diff_analysis(raw)

    assert output["dependency_change_flags"]["has_lockfile_change"] is True
    assert output["dependency_change_flags"]["has_manifest_change"] is False
    assert output["dependency_drift_indicators"] == ["lockfile_only_change"]


def test_diff_analysis_detects_manifest_and_lockfile_change() -> None:
    raw = Path("fixtures/diffs/node-mixed-code-lock.diff").read_text()

    output = run_diff_analysis(raw)

    assert output["dependency_change_flags"]["has_lockfile_change"] is True
    assert output["dependency_change_flags"]["has_manifest_change"] is True
    assert "manifest_and_lockfile_changed" in output["dependency_drift_indicators"]
    assert "src/http/client.ts" in output["changed_files"]


def test_diff_analysis_refactor_only_has_no_dependency_flags() -> None:
    raw = Path("fixtures/diffs/refactor-only.diff").read_text()

    output = run_diff_analysis(raw)

    assert output["dependency_change_flags"]["has_lockfile_change"] is False
    assert output["dependency_change_flags"]["has_manifest_change"] is False
    assert output["dependency_drift_indicators"] == []


def test_diff_analysis_is_deterministic_for_same_input() -> None:
    raw = Path("fixtures/diffs/node-mixed-code-lock.diff").read_text()

    first = run_diff_analysis(raw)
    second = run_diff_analysis(raw)

    assert first == second
