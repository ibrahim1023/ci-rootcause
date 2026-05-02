from pathlib import Path

from src.evaluation.runner import run_eval_dataset


def test_run_eval_dataset_writes_results(tmp_path: Path) -> None:
    output_path = tmp_path / "results.json"

    result = run_eval_dataset(output_path=str(output_path))

    assert result["summary"]["passed"] is True
    assert result["summary"]["total_cases"] >= 7
    assert output_path.exists()


def test_run_harness_eval_dataset_writes_results(tmp_path: Path) -> None:
    output_path = tmp_path / "harness-results.json"

    result = run_eval_dataset(
        dataset_path="evals/datasets/harness-quality.json",
        output_path=str(output_path),
    )

    assert result["summary"]["passed"] is True
    assert result["summary"]["total_cases"] == 4
    assert result["summary"]["metrics"]["compression_signal_preservation_rate"] == 1.0
    assert result["summary"]["metrics"]["compression_noise_pruning_rate"] == 1.0
    assert result["summary"]["metrics"]["contradiction_documented_rate"] == 1.0
    assert result["summary"]["metrics"]["contradiction_resolution_basis_rate"] == 1.0
    assert output_path.exists()
