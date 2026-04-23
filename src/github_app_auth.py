from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib import error
from urllib import request as urllib_request


class GitHubAppAuthError(RuntimeError):
    """Raised when GitHub App authentication cannot be completed."""


class GitHubAppTokenError(RuntimeError):
    """Raised when GitHub App installation token exchange fails."""


@dataclass(frozen=True)
class GitHubAppInstallationToken:
    token: str
    expires_at: str


def build_github_app_jwt(
    app_id: str,
    private_key_pem: str,
    *,
    now_epoch: int | None = None,
    ttl_seconds: int = 540,
) -> str:
    app_id_value = str(app_id).strip()
    if not app_id_value:
        raise GitHubAppAuthError("app_id is required")
    if not private_key_pem.strip():
        raise GitHubAppAuthError("private_key_pem is required")
    if ttl_seconds <= 0:
        raise GitHubAppAuthError("ttl_seconds must be > 0")

    try:
        import jwt  # type: ignore[import-not-found]
    except ImportError as exc:
        raise GitHubAppAuthError(
            "PyJWT is required to build GitHub App JWTs. Install dependency: pyjwt[crypto]"
        ) from exc

    issued_at = int(now_epoch if now_epoch is not None else time.time())
    payload = {
        "iat": issued_at - 60,
        "exp": issued_at + ttl_seconds,
        "iss": app_id_value,
    }
    encoded = jwt.encode(payload, private_key_pem, algorithm="RS256")
    if isinstance(encoded, bytes):
        return encoded.decode("utf-8")
    return str(encoded)


def request_github_app_installation_token(
    *,
    app_jwt: str,
    installation_id: int,
    api_base: str = "https://api.github.com",
) -> GitHubAppInstallationToken:
    jwt_value = app_jwt.strip()
    if not jwt_value:
        raise GitHubAppTokenError("app_jwt is required")
    if installation_id <= 0:
        raise GitHubAppTokenError("installation_id must be > 0")

    url = f"{api_base.rstrip('/')}/app/installations/{installation_id}/access_tokens"
    req = urllib_request.Request(
        url=url,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {jwt_value}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        data=b"{}",
    )
    try:
        with urllib_request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise GitHubAppTokenError(
            f"GitHub installation token request failed: {exc.code}: {message}"
        ) from exc
    except error.URLError as exc:
        raise GitHubAppTokenError(f"GitHub installation token network error: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GitHubAppTokenError(f"GitHub installation token response is not JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise GitHubAppTokenError("GitHub installation token response must be a JSON object")
    token = str(payload.get("token", "")).strip()
    expires_at = str(payload.get("expires_at", "")).strip()
    if not token or not expires_at:
        raise GitHubAppTokenError(
            "GitHub installation token response missing required token/expires_at fields"
        )
    return GitHubAppInstallationToken(token=token, expires_at=expires_at)


def mint_github_app_installation_token(
    *,
    app_id: str,
    private_key_pem: str,
    installation_id: int,
    api_base: str = "https://api.github.com",
) -> GitHubAppInstallationToken:
    app_jwt = build_github_app_jwt(
        app_id=app_id,
        private_key_pem=private_key_pem,
    )
    return request_github_app_installation_token(
        app_jwt=app_jwt,
        installation_id=installation_id,
        api_base=api_base,
    )
