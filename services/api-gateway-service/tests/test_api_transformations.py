"""HTTP tests for /gateway/transformations (request/response transformation rules).

This router declares no ``caller: CurrentUserId`` parameter, so no route
needs ``Authorization`` headers, and none records an audit entry.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest import HTTP_BAD_REQUEST, HTTP_CREATED, HTTP_OK

pytestmark = pytest.mark.asyncio


class TestListTransformations:
    async def test_list_is_empty_before_any_rule_is_created(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/gateway/transformations", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_with_no_route_id_returns_only_global_rules(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        route = await make_route(service.id)
        await client.post(
            "/gateway/transformations",
            params={"organization_id": str(organization_id)},
            json={"name": "global-rule", "kind": "header", "direction": "request"},
        )
        await client.post(
            "/gateway/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "name": "route-rule",
                "kind": "header",
                "direction": "request",
                "route_id": str(route.id),
            },
        )
        resp = await client.get(
            "/gateway/transformations", params={"organization_id": str(organization_id)}
        )
        names = {row["name"] for row in resp.json()["data"]}
        assert names == {"global-rule"}

    async def test_list_with_a_route_id_returns_global_and_route_specific_rules(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        route = await make_route(service.id)
        await client.post(
            "/gateway/transformations",
            params={"organization_id": str(organization_id)},
            json={"name": "global-rule-2", "kind": "header", "direction": "request"},
        )
        await client.post(
            "/gateway/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "name": "route-rule-2",
                "kind": "header",
                "direction": "request",
                "route_id": str(route.id),
            },
        )
        resp = await client.get(
            "/gateway/transformations",
            params={"organization_id": str(organization_id), "route_id": str(route.id)},
        )
        names = {row["name"] for row in resp.json()["data"]}
        assert names == {"global-rule-2", "route-rule-2"}


class TestCreateTransformation:
    async def test_create_needs_no_auth_and_returns_defaults(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/transformations",
            params={"organization_id": str(organization_id)},
            json={"name": "default-rule", "kind": "header"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["name"] == "default-rule"
        assert data["kind"] == "header"
        assert data["direction"] == "request"
        assert data["route_id"] is None
        assert data["priority"] == 100
        assert data["enabled"] is True
        assert data["config"] == {}

    async def test_create_with_every_field_set(
        self, client: AsyncClient, make_service, make_route, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        route = await make_route(service.id)
        resp = await client.post(
            "/gateway/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "name": "full-rule",
                "kind": "url_rewrite",
                "direction": "response",
                "config": {"pattern": "^/old", "replacement": "/new"},
                "route_id": str(route.id),
                "priority": 5,
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["kind"] == "url_rewrite"
        assert data["direction"] == "response"
        assert data["config"] == {"pattern": "^/old", "replacement": "/new"}
        assert data["route_id"] == str(route.id)
        assert data["priority"] == 5

    async def test_create_with_an_invalid_kind_is_a_bad_request(
        self, app: FastAPI, organization_id: uuid.UUID
    ) -> None:
        # `kind`/`direction` are plain `str` fields on `TransformationRuleRequest`
        # (not Pydantic-enum-typed), so an invalid value is only caught
        # inside the route body by `transformation_kind_of`, which raises
        # a bare `ValueError` -- mapped to a 400 by the app's generic
        # `Exception` handler, which lives on Starlette's outermost
        # `ServerErrorMiddleware`. That middleware always re-raises after
        # sending its response (so a real ASGI server can still log the
        # traceback), which the default `client` fixture's
        # `raise_app_exceptions=True` surfaces as a raised exception
        # instead of a response -- so this test needs its own transport
        # with that switched off to observe the real 400 the wire actually
        # gets.
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as tolerant_client:
            resp = await tolerant_client.post(
                "/gateway/transformations",
                params={"organization_id": str(organization_id)},
                json={"name": "bad-kind-rule", "kind": "not-a-real-kind"},
            )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_create_with_an_invalid_direction_is_a_bad_request(
        self, app: FastAPI, organization_id: uuid.UUID
    ) -> None:
        # See `test_create_with_an_invalid_kind_is_a_bad_request` above.
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as tolerant_client:
            resp = await tolerant_client.post(
                "/gateway/transformations",
                params={"organization_id": str(organization_id)},
                json={"name": "bad-direction-rule", "kind": "header", "direction": "sideways"},
            )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_create_with_a_missing_name_is_a_bad_request(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/transformations",
            params={"organization_id": str(organization_id)},
            json={"kind": "header"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST
