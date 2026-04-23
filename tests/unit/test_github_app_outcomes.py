from __future__ import annotations

import pytest

from src.github_app_outcomes import (
    STATUS_ERROR,
    STATUS_OK,
    build_outcome,
    ensure_known_reason_code,
)


def test_build_outcome_accepts_known_status_and_reason_code() -> None:
    outcome = build_outcome(status=STATUS_OK, reason_code="", reason="")
    assert outcome.status == "ok"
    assert outcome.reason_code == ""


def test_ensure_known_reason_code_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="Unknown app outcome reason code"):
        ensure_known_reason_code("NOT_A_REAL_CODE")


def test_build_outcome_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="Unknown app outcome status"):
        build_outcome(status="done", reason_code="", reason="")


def test_build_outcome_normalizes_reason_code_case() -> None:
    outcome = build_outcome(
        status=STATUS_ERROR,
        reason_code="workflow_not_failed",
        reason="ignored",
    )
    assert outcome.reason_code == "WORKFLOW_NOT_FAILED"
