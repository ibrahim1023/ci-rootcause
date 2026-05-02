from __future__ import annotations

from src.benchmark.ollama_comparison import build_live_ollama_suite

SUITE_PATH = "fixtures/benchmarks/mvp-suite.json"


def test_build_live_ollama_suite_filters_to_agentic_cases() -> None:
    suite = build_live_ollama_suite(
        suite_path=SUITE_PATH,
        llm_model="qwen2.5-coder:7b",
        llm_base_url="http://localhost:11434",
    )

    assert suite["suite_name"] == "mvp-curated-v3-live-ollama"
    cases = suite["cases"]
    assert len(cases) == 6
    assert all(case["execution_mode"] == "agentic_assist" for case in cases)
    assert all(case["llm_provider"] == "local" for case in cases)
    assert all(case["llm_model"] == "qwen2.5-coder:7b" for case in cases)
    assert all(case["llm_base_url"] == "http://localhost:11434" for case in cases)
    assert all("mocked_agentic_proposal_path" not in case for case in cases)
