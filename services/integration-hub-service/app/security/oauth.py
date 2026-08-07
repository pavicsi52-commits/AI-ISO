"""OAuth2 token exchange (docs/058 "AUTHENTICATION": OAuth2).

A genuine gap -- `shared_core.security.providers.AuthenticationProvider`
is a bare structural `Protocol`, and
`shared_core.connectors.credentials.CredentialType.OAUTH2` is only a
typed holder for a token this service already has; nothing anywhere
performs the actual RFC 6749 token-endpoint exchange. Only the
*token-endpoint* legs are implemented here (authorization-code exchange
and refresh) -- the *authorization* leg (redirecting a user's browser to
a provider's consent screen and catching the callback) has no meaning
for a backend-only service with no UI of its own, and is out of scope
the same way docs/058's own "DO NOT IMPLEMENT: Commercial iPaaS
Platforms" excludes building a full end-user consent flow. A caller
(whatever obtained the redirect and its own ``code`` query parameter)
supplies *code* here; this module only ever talks to the provider's own
token endpoint, a plain server-to-server HTTP POST.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from shared_core.exceptions.dependency import DependencyError


@dataclass(frozen=True, slots=True)
class OAuthTokenResponse:
    """One token-endpoint response, per RFC 6749 section 5.1."""

    access_token: str
    token_type: str
    refresh_token: str | None
    expires_in: int | None


async def _post_token_request(
    client: httpx.AsyncClient, *, token_url: str, data: dict[str, str], timeout_seconds: float
) -> OAuthTokenResponse:
    try:
        response = await client.post(token_url, data=data, timeout=timeout_seconds)
    except httpx.HTTPError as exc:
        raise DependencyError(f"OAuth2 token endpoint unreachable: {exc}") from exc
    if response.status_code != httpx.codes.OK:
        raise DependencyError(
            f"OAuth2 token endpoint returned HTTP {response.status_code}: {response.text[:500]}"
        )
    body = response.json()
    if "access_token" not in body:
        raise DependencyError("OAuth2 token endpoint response has no access_token.")
    return OAuthTokenResponse(
        access_token=str(body["access_token"]),
        token_type=str(body.get("token_type", "bearer")),
        refresh_token=body.get("refresh_token"),
        expires_in=body.get("expires_in"),
    )


async def exchange_authorization_code(
    client: httpx.AsyncClient,
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    timeout_seconds: float = 10.0,
) -> OAuthTokenResponse:
    """Exchange an authorization *code* for an access/refresh token pair.

    Raises:
        DependencyError: If the provider's token endpoint is
            unreachable or refuses the exchange.
    """
    return await _post_token_request(
        client,
        token_url=token_url,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout_seconds=timeout_seconds,
    )


async def refresh_access_token(
    client: httpx.AsyncClient,
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    timeout_seconds: float = 10.0,
) -> OAuthTokenResponse:
    """Exchange a still-valid *refresh_token* for a new access token.

    Raises:
        DependencyError: If the provider's token endpoint is
            unreachable or refuses the exchange.
    """
    return await _post_token_request(
        client,
        token_url=token_url,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout_seconds=timeout_seconds,
    )


__all__ = ["OAuthTokenResponse", "exchange_authorization_code", "refresh_access_token"]
