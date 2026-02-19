import json

import pytest

from src.contracts.models import (
    Evidence,
    FailureClass,
    FailureGraph,
    FailureNode,
    PRCreationResult,
    PrimaryRootCause,
    RankedCause,
    RCAMeta,
    RCAOutput,
)


def _valid_graph() -> FailureGraph:
    return FailureGraph(
        nodes=[
            FailureNode(
                stage="build",
                timestamp="2026-02-19T12:00:00Z",
                error_signature="ModuleNotFoundError",
                file="src/main.py",
                line=7,
                stack_frames=["src/main.py:7"],
                log_excerpt="ModuleNotFoundError: x",
                is_first_failure=True,
            )
        ]
    )


def test_failure_graph_validates() -> None:
    graph = _valid_graph()
    graph.validate()


def test_failure_graph_requires_exactly_one_first_failure() -> None:
    graph = FailureGraph(
        nodes=[
            FailureNode(
                stage="build",
                timestamp="t1",
                error_signature="E1",
                is_first_failure=False,
            )
        ]
    )

    with pytest.raises(ValueError, match="exactly one node"):
        graph.validate()


def test_failure_graph_rejects_invalid_line() -> None:
    graph = FailureGraph(
        nodes=[
            FailureNode(
                stage="build",
                timestamp="t1",
                error_signature="E1",
                line=0,
                is_first_failure=True,
            )
        ]
    )

    with pytest.raises(ValueError, match="line must be > 0"):
        graph.validate()


def test_rca_output_serialization_is_deterministic() -> None:
    output = RCAOutput(
        summary="Typecheck failure",
        classification=FailureClass.TYPECHECK,
        primary_root_cause=PrimaryRootCause(
            title="Bad return type",
            evidence=[Evidence(file="src/app.py", line=10)],
            confidence=0.8,
        ),
        ranked_alternatives=[
            RankedCause(
                title="Dependency mismatch",
                evidence=[Evidence(file="poetry.lock")],
                score=0.2,
            )
        ],
        suggested_fix=["Fix return annotation"],
        meta=RCAMeta(commit="abc", run_id="run_1"),
    )

    serialized_once = output.to_json()
    serialized_twice = output.to_json()
    assert serialized_once == serialized_twice

    data = json.loads(serialized_once)
    assert data["classification"] == "TYPECHECK"


def test_rca_output_rejects_invalid_confidence() -> None:
    output = RCAOutput(
        summary="Typecheck failure",
        classification=FailureClass.TYPECHECK,
        primary_root_cause=PrimaryRootCause(
            title="Bad return type",
            evidence=[Evidence(file="src/app.py")],
            confidence=1.2,
        ),
        ranked_alternatives=[],
        suggested_fix=[],
        meta=RCAMeta(commit="abc", run_id="run_1"),
    )

    with pytest.raises(ValueError, match="between 0 and 1"):
        output.validate()


def test_pr_creation_result_contract() -> None:
    created = PRCreationResult(
        pr_created=True,
        pr_url="https://github.com/acme/repo/pull/1",
        pr_number=1,
        pr_branch="ci-rootcause/fix/1",
    )
    created.validate()

    skipped = PRCreationResult(
        pr_created=False,
        failure_reason="create_fix_pr=false",
    )
    skipped.validate()


def test_pr_creation_result_requires_failure_reason_when_not_created() -> None:
    skipped = PRCreationResult(pr_created=False)

    with pytest.raises(ValueError, match="failure_reason"):
        skipped.validate()
