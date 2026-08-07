"""Live credential resolution against the Secrets Management Service
(``app/security/credential_resolver.py``).

Against a real Starlette-backed Secrets Management Service double (via
``tests/conftest.py``'s own ``fake_backend_app`` and ``httpx.ASGITransport``)
for every reachable case, and a real closed loopback port for the
unreachable case -- never mocked, per ``tests/conftest.py``'s own
docstring.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from shared_core.exceptions.dependency import DependencyError
from starlette.applications import Starlette
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from starlette.routing import Route as StarletteRoute

from app.config.settings import IntegrationHubServiceSettings
from app.security.credential_resolver import SecretCredentialResolver
from tests.conftest import (
    KNOWN_SECRET_ID,
    KNOWN_SECRET_VALUE,
    MISSING_SECRET_ID,
    UNREACHABLE_HTTP_URL,
    fake_backend_app,
)


class TestResolve:
    async def test_resolve_returns_the_known_secrets_value(
        self, credential_resolver: SecretCredentialResolver
    ) -> None:
        value = await credential_resolver.resolve(KNOWN_SECRET_ID, caller_token="caller-token")
        assert value == KNOWN_SECRET_VALUE

    async def test_resolve_forwards_the_callers_own_bearer_token(
        self, service_settings: IntegrationHubServiceSettings
    ) -> None:
        """The Secrets Management Service's own ACL applies to *this*
        caller, not to this service itself -- so the token that reaches it
        must be the one the caller actually presented, forwarded
        unchanged.
        """
        seen_headers: dict[str, str] = {}

        async def _capture_and_resolve(request: StarletteRequest) -> JSONResponse:
            seen_headers.update(request.headers)
            return JSONResponse({"data": {"value": KNOWN_SECRET_VALUE}})

        app = Starlette(
            routes=[StarletteRoute("/secrets/{secret_id}", _capture_and_resolve, methods=["GET"])]
        )
        client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://backend.example.com"
        )
        resolver = SecretCredentialResolver(
            client, base_url=service_settings.secrets_service_base_url
        )

        await resolver.resolve(KNOWN_SECRET_ID, caller_token="a-specific-caller-token")

        assert seen_headers["authorization"] == "Bearer a-specific-caller-token"
        await client.aclose()

    async def test_resolve_raises_dependency_error_for_a_missing_secret(
        self, credential_resolver: SecretCredentialResolver
    ) -> None:
        with pytest.raises(DependencyError):
            await credential_resolver.resolve(MISSING_SECRET_ID, caller_token="caller-token")

    async def test_resolve_raises_dependency_error_when_no_auth_header_reaches_the_backend(
        self, service_settings: IntegrationHubServiceSettings
    ) -> None:
        """``fake_backend_app``'s own ``_fake_get_secret`` 401s a request
        with no ``Authorization`` header at all -- a branch unreachable
        through ``resolve()``'s own public interface, since it always
        attaches one of its own, however the caller's own token is spelled.
        A client whose own ``request`` event hook strips it back out right
        before the request leaves is still a real, complete ASGI round
        trip through the same fake backend every other test in this file
        uses; it is just how this suite reaches that one branch of its own
        documented contract.
        """

        async def _strip_authorization(request: httpx.Request) -> None:
            request.headers.pop("authorization", None)

        client = AsyncClient(
            transport=ASGITransport(app=fake_backend_app()),
            base_url="http://backend.example.com",
            event_hooks={"request": [_strip_authorization]},
        )
        resolver = SecretCredentialResolver(
            client, base_url=service_settings.secrets_service_base_url
        )

        with pytest.raises(DependencyError):
            await resolver.resolve(KNOWN_SECRET_ID, caller_token="caller-token")
        await client.aclose()

    async def test_resolve_raises_dependency_error_for_an_unexpected_status_code(
        self, service_settings: IntegrationHubServiceSettings
    ) -> None:
        async def _always_fails(request: StarletteRequest) -> JSONResponse:
            return JSONResponse({"detail": "internal error"}, status_code=500)

        app = Starlette(
            routes=[StarletteRoute("/secrets/{secret_id}", _always_fails, methods=["GET"])]
        )
        client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://backend.example.com"
        )
        resolver = SecretCredentialResolver(
            client, base_url=service_settings.secrets_service_base_url
        )

        with pytest.raises(DependencyError):
            await resolver.resolve(KNOWN_SECRET_ID, caller_token="caller-token")
        await client.aclose()

    async def test_resolve_raises_dependency_error_when_the_backend_is_unreachable(self) -> None:
        """A real closed loopback port -- genuinely unreachable, fails fast
        -- with a plain, non-ASGI ``httpx.AsyncClient``, exactly the
        precedent ``tests/conftest.py``'s own ``UNREACHABLE_HTTP_URL``
        already establishes for ``ConnectionService``'s own HTTP probe.
        """
        client = AsyncClient(timeout=httpx.Timeout(5.0))
        resolver = SecretCredentialResolver(client, base_url=UNREACHABLE_HTTP_URL)

        with pytest.raises(DependencyError) as exc_info:
            await resolver.resolve(KNOWN_SECRET_ID, caller_token="caller-token")

        assert isinstance(exc_info.value.__cause__, httpx.HTTPError)
        await client.aclose()

    async def test_base_url_with_a_trailing_slash_still_reaches_the_right_path(
        self, service_settings: IntegrationHubServiceSettings
    ) -> None:
        """``__init__`` strips a trailing slash off *base_url* so
        ``resolve()`` never builds a doubled-up ``//secrets/...`` path.
        """
        client = AsyncClient(
            transport=ASGITransport(app=fake_backend_app()), base_url="http://backend.example.com"
        )
        resolver = SecretCredentialResolver(
            client, base_url=service_settings.secrets_service_base_url + "/"
        )

        value = await resolver.resolve(KNOWN_SECRET_ID, caller_token="caller-token")

        assert value == KNOWN_SECRET_VALUE
        await client.aclose()
