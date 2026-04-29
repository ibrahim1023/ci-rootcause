from pathlib import Path

from src.evaluation.runner import run_eval_dataset


def test_run_eval_dataset_writes_results(tmp_path: Path) -> None:
    output_path = tmp_path / "results.json"

    result = run_eval_dataset(output_path=str(output_path))

    assert result["summary"]["passed"] is True
    assert result["summary"]["total_cases"] >= 7
    assert output_path.exists()
