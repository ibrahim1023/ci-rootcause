from __future__ import annotations

from src.core.provider_adapters import resolve_provider_defaults


def test_resolve_provider_defaults_github_actions() -> None:
    resolution = resolve_provider_defaults(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "acme/ci-rootcause",
            "GITHUB_BASE_REF": "main",
        }
    )

    assert resolution.ci_provider == "github-actions"
    assert resolution.provider_adapter == "github"
    assert resolution.repository == "acme/ci-rootcause"
    assert resolution.target_branch == "main"


def test_resolve_provider_defaults_gitlab_ci() -> None:
    resolution = resolve_provider_defaults(
        {
            "GITLAB_CI": "true",
            "CI_PROJECT_PATH": "acme/ci-rootcause",
            "CI_MERGE_REQUEST_TARGET_BRANCH_NAME": "develop",
        }
    )

    assert resolution.ci_provider == "gitlab-ci"
    assert resolution.provider_adapter == "gitlab"
    assert resolution.repository == "acme/ci-rootcause"
    assert resolution.target_branch == "develop"


def test_resolve_provider_defaults_fallback() -> None:
    resolution = resolve_provider_defaults({})

    assert resolution.ci_provider == "github-actions"
    assert resolution.provider_adapter == "github"
    assert resolution.repository == ""
    assert resolution.target_branch == "main"
