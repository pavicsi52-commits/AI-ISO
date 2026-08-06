"""The reverse-proxy catch-all's own route handler (docs/056).

`app/services/proxy.py` (`ProxyService` itself) is a different agent's
scope; this file is HTTP-level only -- auth resolution from
`X-API-Key`/`Authorization: Bearer`/`X-Organization-Id`, route-level auth
enforcement, and error-to-HTTP-response mapping, per
`app/api/proxy.py`'s own docstring.

Error bodies for `AIIOSException` subclasses go through
`shared_core.exceptions.register_exception_handlers`, which -- per its
own "SECURITY" docstring -- masks the original diagnostic message and
returns only a generic, localized `user_message`. So assertions below
check `response.status_code` and `response.json()["error"]["code"]`
(the one stable, class-level signal: `AuthenticationError.error_code`
etc.), never the specific reason string passed to the exception's own
constructor. `ProxyError` is different: it is caught directly inside the
route handler and turned into a *plain-text* response, bypassing that
envelope entirely -- see `test_a_proxy_error_maps_to_its_own_status_code`.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.api import deps
from app.services.proxy import ProxyError
from tests.conftest import (
    HTTP_FORBIDDEN,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio

AUTHENTICATION_ERROR_CODE = "AIIOS-AUTH-0001"
AUTHORIZATION_ERROR_CODE = "AIIOS-AUTHZ-0001"
NOT_FOUND_ERROR_CODE = "AIIOS-NF-0001"


class TestOrganizationResolution:
    async def test_anonymous_with_an_org_header_reaches_a_public_route(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        await make_route(service.id, requires_auth=False)

        response = await client.get("/echo", headers={"X-Organization-Id": str(organization_id)})
        assert response.status_code == HTTP_OK
        assert response.json()["method"] == "GET"

    async def test_anonymous_with_no_org_header_and_no_jwt_cannot_resolve_an_organization(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/echo")
        assert response.status_code == HTTP_UNAUTHORIZED
        assert response.json()["error"]["code"] == AUTHENTICATION_ERROR_CODE

    async def test_a_jwt_caller_never_needs_the_org_header(
        self,
        client: AsyncClient,
        make_service,
        make_route,
        auth_headers,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service()
        await make_route(service.id, requires_auth=True)
        headers = auth_headers(uuid.uuid4(), organization_id=organization_id, role="super_admin")

        response = await client.get("/echo", headers=headers)
        assert response.status_code == HTTP_OK

    async def test_an_api_key_caller_never_needs_the_org_header(
        self,
        client: AsyncClient,
        make_service,
        make_route,
        make_api_key,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service()
        await make_route(service.id, requires_auth=True)
        raw_key, _created = await make_api_key(scopes=["gateway:read"])

        response = await client.get("/echo", headers={"X-API-Key": raw_key})
        assert response.status_code == HTTP_OK


class TestRouteLevelAuthEnforcement:
    async def test_a_route_requiring_auth_refuses_an_anonymous_caller(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        await make_route(service.id, requires_auth=True)

        response = await client.get("/echo", headers={"X-Organization-Id": str(organization_id)})
        assert response.status_code == HTTP_UNAUTHORIZED
        assert response.json()["error"]["code"] == AUTHENTICATION_ERROR_CODE

    async def test_a_route_restricting_auth_methods_refuses_a_disallowed_one(
        self,
        client: AsyncClient,
        make_service,
        make_route,
        auth_headers,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service()
        await make_route(service.id, requires_auth=True, allowed_auth_methods=["api_key"])
        headers = auth_headers(uuid.uuid4(), organization_id=organization_id)

        response = await client.get("/echo", headers=headers)
        assert response.status_code == HTTP_UNAUTHORIZED
        assert response.json()["error"]["code"] == AUTHENTICATION_ERROR_CODE

    async def test_a_route_restricting_auth_methods_allows_a_permitted_one(
        self,
        client: AsyncClient,
        make_service,
        make_route,
        auth_headers,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service()
        await make_route(service.id, requires_auth=True, allowed_auth_methods=["jwt"])
        headers = auth_headers(uuid.uuid4(), organization_id=organization_id)

        response = await client.get("/echo", headers=headers)
        assert response.status_code == HTTP_OK

    async def test_a_route_requiring_scopes_the_caller_lacks_is_forbidden(
        self,
        client: AsyncClient,
        make_service,
        make_route,
        make_api_key,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service()
        await make_route(service.id, requires_auth=True, required_scopes=["gateway:admin"])
        raw_key, _created = await make_api_key(scopes=["gateway:read"])

        response = await client.get("/echo", headers={"X-API-Key": raw_key})
        assert response.status_code == HTTP_FORBIDDEN
        assert response.json()["error"]["code"] == AUTHORIZATION_ERROR_CODE

    async def test_a_route_requiring_a_permission_the_callers_role_lacks_is_forbidden(
        self,
        client: AsyncClient,
        make_service,
        make_route,
        auth_headers,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service()
        await make_route(service.id, requires_auth=True, required_permission="admin")
        headers = auth_headers(uuid.uuid4(), organization_id=organization_id, role="viewer")

        response = await client.get("/echo", headers=headers)
        assert response.status_code == HTTP_FORBIDDEN
        assert response.json()["error"]["code"] == AUTHORIZATION_ERROR_CODE

    async def test_no_matching_route_is_a_not_found(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/there-is-no-such-route", headers={"X-Organization-Id": str(organization_id)}
        )
        assert response.status_code == HTTP_NOT_FOUND
        assert response.json()["error"]["code"] == NOT_FOUND_ERROR_CODE


class TestForwarding:
    async def test_a_post_body_is_forwarded_to_the_upstream(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        await make_route(service.id, requires_auth=False)

        response = await client.post(
            "/echo",
            content=b'{"hello": "world"}',
            headers={"X-Organization-Id": str(organization_id), "Content-Type": "application/json"},
        )
        assert response.status_code == HTTP_OK
        assert response.json()["body"] == '{"hello": "world"}'

    async def test_hop_by_hop_request_headers_are_stripped_before_forwarding(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        # `Connection` itself is a poor probe here: the *outbound* httpx
        # client `ProxyService` forwards through sets its own default
        # `Connection` header regardless of what this route stripped, so
        # its presence proves nothing either way. `Proxy-Authorization`
        # is hop-by-hop too (per `_HOP_BY_HOP_HEADERS`) and no HTTP
        # client sets it unprompted, so it isolates this route's own
        # stripping behaviour cleanly.
        service = await make_service()
        await make_route(service.id, requires_auth=False)

        response = await client.get(
            "/echo",
            headers={
                "X-Organization-Id": str(organization_id),
                "Proxy-Authorization": "Basic secret",
                "X-Test-Marker": "present",
            },
        )
        assert response.status_code == HTTP_OK
        upstream_headers = {k.lower() for k in response.json()["headers"]}
        assert "proxy-authorization" not in upstream_headers
        assert "x-test-marker" in upstream_headers
        assert "x-test-marker" in upstream_headers

    async def test_an_upstream_error_status_passes_through_unchanged(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        # `/error` (from `fake_backend_app`) collides with none of this
        # service's own literal management routes, so it is a route the
        # catch-all genuinely reaches -- unlike `/health`, which this
        # service's *own* liveness endpoint shadows by router-ordering
        # design (`app/core/factory.py`'s own docstring).
        service = await make_service()
        await make_route(service.id, path_pattern="/error", methods=["get"], requires_auth=False)

        response = await client.get("/error", headers={"X-Organization-Id": str(organization_id)})
        assert response.status_code == 500
        assert response.json() == {"detail": "backend failure"}


class _RaisingProxyService:
    """A stand-in for `ProxySvc` that always refuses, to force the one
    branch a real upstream call cannot deterministically reach."""

    def __init__(self, status_code: int, detail: str) -> None:
        self._status_code = status_code
        self._detail = detail

    async def proxy(self, *_args: Any, **_kwargs: Any) -> Any:
        raise ProxyError(self._status_code, self._detail)


class TestProxyErrorMapping:
    async def test_a_proxy_error_maps_to_its_own_status_code_as_plain_text(
        self, client: AsyncClient, app, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        await make_route(service.id, requires_auth=False)
        app.dependency_overrides[deps.get_proxy_service] = lambda: _RaisingProxyService(
            503, "backend offline"
        )

        response = await client.get("/echo", headers={"X-Organization-Id": str(organization_id)})
        assert response.status_code == 503
        assert response.text == "backend offline"
        assert response.headers["content-type"].startswith("text/plain")
