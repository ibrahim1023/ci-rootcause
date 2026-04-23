from __future__ import annotations

import io
import json
import types
from urllib import error

import pytest

from src.github_app_auth import (
    GitHubAppAuthError,
    GitHubAppTokenError,
    build_github_app_jwt,
    mint_github_app_installation_token,
    request_github_app_installation_token,
)


def test_build_github_app_jwt_uses_expected_claims(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_encode(payload: dict[str, object], key: str, algorithm: str) -> str:
        captured["payload"] = payload
        captured["key"] = key
        captured["algorithm"] = algorithm
        return "signed-token"

    monkeypatch.setitem(
        __import__("sys").modules,
        "jwt",
        types.SimpleNamespace(encode=fake_encode),
    )

    token = build_github_app_jwt(
        app_id="1234",
        private_key_pem="-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
        now_epoch=1_700_000_000,
        ttl_seconds=600,
    )

    assert token == "signed-token"
    assert captured["algorithm"] == "RS256"
    assert captured["key"]
    assert captured["payload"] == {
        "iat": 1_699_999_940,
        "exp": 1_700_000_600,
        "iss": "1234",
    }


def test_build_github_app_jwt_rejects_invalid_inputs() -> None:
    with pytest.raises(GitHubAppAuthError, match="app_id is required"):
        build_github_app_jwt(app_id="", private_key_pem="key")
    with pytest.raises(GitHubAppAuthError, match="private_key_pem is required"):
        build_github_app_jwt(app_id="1234", private_key_pem=" ")
    with pytest.raises(GitHubAppAuthError, match="ttl_seconds must be > 0"):
        build_github_app_jwt(app_id="1234", private_key_pem="key", ttl_seconds=0)


def test_request_installation_token_success(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps({"token": "ghs_123", "expires_at": "2026-03-01T00:00:00Z"}).encode(
                "utf-8"
            )

    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        assert timeout == 15
        assert req.method == "POST"
        assert req.get_header("Authorization") == "Bearer app-jwt"
        return FakeResponse()

    monkeypatch.setattr("src.github_app_auth.urllib_request.urlopen", fake_urlopen)

    token = request_github_app_installation_token(app_jwt="app-jwt", installation_id=99)
    assert token.token == "ghs_123"
    assert token.expires_at == "2026-03-01T00:00:00Z"


def test_request_installation_token_http_error(monkeypatch) -> None:
    def fake_urlopen(req, timeout: int):  # noqa: ANN001
        del req, timeout
        raise error.HTTPError(
            url="https://api.github.com/app/installations/1/access_tokens",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"bad credentials"}'),
        )

    monkeypatch.setattr("src.github_app_auth.urllib_request.urlopen", fake_urlopen)

    with pytest.raises(GitHubAppTokenError, match="failed: 401"):
        request_github_app_installation_token(app_jwt="app-jwt", installation_id=1)


def test_request_installation_token_invalid_shape(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return b'{"missing":"fields"}'

    monkeypatch.setattr(
        "src.github_app_auth.urllib_request.urlopen",
        lambda req, timeout: FakeResponse(),  # noqa: ARG005, ANN001
    )

    with pytest.raises(GitHubAppTokenError, match="missing required token/expires_at"):
        request_github_app_installation_token(app_jwt="app-jwt", installation_id=1)


def test_mint_github_app_installation_token_chains_helpers(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.github_app_auth.build_github_app_jwt",
        lambda app_id, private_key_pem: "signed-jwt",  # noqa: ARG005
    )
    monkeypatch.setattr(
        "src.github_app_auth.request_github_app_installation_token",
        lambda app_jwt, installation_id, api_base: types.SimpleNamespace(  # noqa: ARG005
            token="ghs_abc",
            expires_at="2026-03-01T00:00:00Z",
        ),
    )

    token = mint_github_app_installation_token(
        app_id="1",
        private_key_pem="key",
        installation_id=2,
    )
    assert token.token == "ghs_abc"
