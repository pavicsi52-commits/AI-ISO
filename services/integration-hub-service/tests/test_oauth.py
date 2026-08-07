"""Token-endpoint OAuth2 exchange: authorization-code exchange, refresh,
and the ``OAuthTokenResponse`` result type (``app/security/oauth.py``).

Against a real Starlette-backed OAuth2 provider double (``fake_backend_app``,
reached through ``http_client``'s own ``httpx.ASGITransport``) for the
success and provider-refusal paths -- never mocked, per
``tests/conftest.py``'s own docstring. The "provider unreachable" path is
the one exception: it needs a request that never reaches an ASGI app at
all, so it uses a real, freestanding ``httpx.AsyncClient`` against
``UNREACHABLE_HTTP_URL`` -- a real loopback port nothing listens on, the
same precedent conftest's own ``check_http_reachable`` tests already
establish.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import httpx
import pytest
from shared_core.exceptions.dependency import DependencyError
from starlette.applications import Starlette
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from starlette.routing import Route as StarletteRoute

from app.security.oauth import OAuthTokenResponse, exchange_authorization_code, refresh_access_token
from tests.conftest import GOOD_AUTH_CODE, GOOD_REFRESH_TOKEN, UNREACHABLE_HTTP_URL

TOKEN_URL = "/oauth/token"
REDIRECT_URI = "https://app.example.com/callback"


class TestExchangeAuthorizationCode:
    async def test_exchanges_a_good_code_for_an_access_and_refresh_token(
        self, http_client: httpx.AsyncClient
    ) -> None:
        token = await exchange_authorization_code(
            http_client,
            token_url=TOKEN_URL,
            client_id="client-id",
            client_secret="client-secret",
            code=GOOD_AUTH_CODE,
            redirect_uri=REDIRECT_URI,
        )
        assert token == OAuthTokenResponse(
            access_token="fake-access-token",
            token_type="bearer",
            refresh_token=GOOD_REFRESH_TOKEN,
            expires_in=3600,
        )

    async def test_a_wrong_code_raises_dependency_error(
        self, http_client: httpx.AsyncClient
    ) -> None:
        with pytest.raises(DependencyError) as exc_info:
            await exchange_authorization_code(
                http_client,
                token_url=TOKEN_URL,
                client_id="client-id",
                client_secret="client-secret",
                code="a-wrong-code",
                redirect_uri=REDIRECT_URI,
            )
        assert "400" in str(exc_info.value)

    async def test_an_unreachable_token_endpoint_raises_dependency_error(self) -> None:
        async with httpx.AsyncClient() as unreachable_client:
            with pytest.raises(DependencyError) as exc_info:
                await exchange_authorization_code(
                    unreachable_client,
                    token_url=UNREACHABLE_HTTP_URL,
                    client_id="client-id",
                    client_secret="client-secret",
                    code=GOOD_AUTH_CODE,
                    redirect_uri=REDIRECT_URI,
                    timeout_seconds=2.0,
                )
        assert "unreachable" in str(exc_info.value)


class TestRefreshAccessToken:
    async def test_refreshes_a_good_refresh_token_for_a_new_access_token(
        self, http_client: httpx.AsyncClient
    ) -> None:
        token = await refresh_access_token(
            http_client,
            token_url=TOKEN_URL,
            client_id="client-id",
            client_secret="client-secret",
            refresh_token=GOOD_REFRESH_TOKEN,
        )
        assert token == OAuthTokenResponse(
            access_token="refreshed-access-token",
            token_type="bearer",
            refresh_token=None,
            expires_in=3600,
        )

    async def test_a_wrong_refresh_token_raises_dependency_error(
        self, http_client: httpx.AsyncClient
    ) -> None:
        with pytest.raises(DependencyError) as exc_info:
            await refresh_access_token(
                http_client,
                token_url=TOKEN_URL,
                client_id="client-id",
                client_secret="client-secret",
                refresh_token="a-wrong-refresh-token",
            )
        assert "400" in str(exc_info.value)

    async def test_an_unreachable_token_endpoint_raises_dependency_error(self) -> None:
        async with httpx.AsyncClient() as unreachable_client:
            with pytest.raises(DependencyError) as exc_info:
                await refresh_access_token(
                    unreachable_client,
                    token_url=UNREACHABLE_HTTP_URL,
                    client_id="client-id",
                    client_secret="client-secret",
                    refresh_token=GOOD_REFRESH_TOKEN,
                    timeout_seconds=2.0,
                )
        assert "unreachable" in str(exc_info.value)


async def _missing_access_token_route(request: StarletteRequest) -> JSONResponse:
    del request
    return JSONResponse({"token_type": "bearer", "expires_in": 3600})


class TestPostTokenRequestResponseValidation:
    """Exercises the response-shape guard shared by both public functions
    above (``_post_token_request``'s own "no ``access_token`` in a
    seemingly-successful response" branch) -- reached here through
    ``exchange_authorization_code`` since either public entry point runs
    the same underlying request/response handling.

    Needs its own one-route ASGI double: :func:`~tests.conftest.fake_backend_app`
    never returns a 200 with no ``access_token``, so this is the one case
    in this module that cannot reuse the shared ``http_client`` fixture.
    """

    async def test_a_200_response_with_no_access_token_raises_dependency_error(self) -> None:
        broken_backend = Starlette(
            routes=[StarletteRoute("/oauth/token", _missing_access_token_route, methods=["POST"])]
        )
        transport = httpx.ASGITransport(app=broken_backend)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://backend.example.com"
        ) as broken_client:
            with pytest.raises(DependencyError) as exc_info:
                await exchange_authorization_code(
                    broken_client,
                    token_url=TOKEN_URL,
                    client_id="client-id",
                    client_secret="client-secret",
                    code=GOOD_AUTH_CODE,
                    redirect_uri=REDIRECT_URI,
                )
        assert "access_token" in str(exc_info.value)


class TestOAuthTokenResponse:
    def test_is_immutable(self) -> None:
        token = OAuthTokenResponse(
            access_token="a", token_type="bearer", refresh_token=None, expires_in=None
        )
        with pytest.raises(FrozenInstanceError):
            token.access_token = "b"  # type: ignore[misc]

    def test_uses_slots_with_no_instance_dict(self) -> None:
        token = OAuthTokenResponse(
            access_token="a", token_type="bearer", refresh_token=None, expires_in=None
        )
        assert not hasattr(token, "__dict__")

    def test_two_responses_with_equal_fields_compare_equal(self) -> None:
        first = OAuthTokenResponse(
            access_token="a", token_type="bearer", refresh_token="r", expires_in=3600
        )
        second = OAuthTokenResponse(
            access_token="a", token_type="bearer", refresh_token="r", expires_in=3600
        )
        assert first == second
