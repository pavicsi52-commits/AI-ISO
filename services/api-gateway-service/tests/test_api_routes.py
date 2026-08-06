"""HTTP tests for /gateway/routes (routing table management).

``GET`` needs no auth; ``POST``/``PUT``/``DELETE`` declare a
``caller: CurrentUserId`` parameter and need ``Authorization`` headers.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.enums import AuditAction
from app.repositories.governance import ApiAuditRepository
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NO_CONTENT,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


class TestListRoutes:
    async def test_list_is_empty_before_any_registration(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get("/gateway/routes", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_registered_route(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"service_id": str(service.id), "name": "orders-route", "path_pattern": "/orders"},
        )
        resp = await client.get("/gateway/routes", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        names = {row["name"] for row in resp.json()["data"]}
        assert "orders-route" in names

    async def test_list_filters_by_service_id(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        service_a = await make_service(name="service-a")
        service_b = await make_service(name="service-b")
        await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"service_id": str(service_a.id), "name": "route-a", "path_pattern": "/a"},
        )
        await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"service_id": str(service_b.id), "name": "route-b", "path_pattern": "/b"},
        )
        resp = await client.get(
            "/gateway/routes",
            params={"organization_id": str(organization_id), "service_id": str(service_a.id)},
        )
        names = {row["name"] for row in resp.json()["data"]}
        assert names == {"route-a"}

    async def test_list_filters_by_enabled(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        service = await make_service()
        created = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={
                "service_id": str(service.id),
                "name": "disable-route",
                "path_pattern": "/disable",
            },
        )
        route_id = created.json()["data"]["id"]
        await client.put(
            f"/gateway/routes/{route_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"enabled": False},
        )
        resp = await client.get(
            "/gateway/routes",
            params={"organization_id": str(organization_id), "enabled": "false"},
        )
        names = {row["name"] for row in resp.json()["data"]}
        assert "disable-route" in names


class TestGetRoute:
    async def test_get_finds_a_registered_route(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        created = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"service_id": str(service.id), "name": "get-route", "path_pattern": "/get"},
        )
        route_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/gateway/routes/{route_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == route_id

    async def test_get_returns_404_for_a_missing_route(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/gateway/routes/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_get_is_scoped_to_its_organization(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        created = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"service_id": str(service.id), "name": "scoped-route", "path_pattern": "/scoped"},
        )
        route_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/gateway/routes/{route_id}", params={"organization_id": str(uuid.uuid4())}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestCreateRoute:
    async def test_create_requires_auth(
        self, client: AsyncClient, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        resp = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            json={
                "service_id": str(service.id),
                "name": "no-auth-route",
                "path_pattern": "/no-auth",
            },
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_route_with_defaults(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        resp = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "service_id": str(service.id),
                "name": "default-route",
                "path_pattern": "/default",
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["name"] == "default-route"
        assert data["match_kind"] == "path"
        assert data["requires_auth"] is True
        assert data["is_fallback"] is False
        assert data["enabled"] is True

    async def test_create_with_every_field_set(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        resp = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "service_id": str(service.id),
                "name": "full-route",
                "match_kind": "path",
                "path_pattern": "/full",
                "host_pattern": "api.example.test",
                "methods": ["GET", "POST"],
                "header_match": {"x-feature": "on"},
                "weight": 50,
                "priority": 10,
                "strip_prefix": True,
                "rewrite_path": "/rewritten",
                "requires_auth": False,
                "allowed_auth_methods": ["jwt"],
                "required_scopes": ["gateway:read"],
                "required_permission": "gateway.read",
                "is_fallback": False,
                "description": "A fully configured route.",
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["methods"] == ["get", "post"]
        assert data["host_pattern"] == "api.example.test"
        assert data["header_match"] == {"x-feature": "on"}
        assert data["weight"] == 50
        assert data["priority"] == 10
        assert data["strip_prefix"] is True
        assert data["rewrite_path"] == "/rewritten"
        assert data["requires_auth"] is False
        assert data["allowed_auth_methods"] == ["jwt"]
        assert data["required_scopes"] == ["gateway:read"]
        assert data["required_permission"] == "gateway.read"
        assert data["description"] == "A fully configured route."

    async def test_create_records_an_audit_entry_with_route_created(
        self,
        client: AsyncClient,
        auth_headers,
        make_service,
        organization_id: uuid.UUID,
        db_session,
    ) -> None:
        service = await make_service()
        caller = uuid.uuid4()
        resp = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(caller),
            json={
                "service_id": str(service.id),
                "name": "audited-route",
                "path_pattern": "/audited",
            },
        )
        route_id = resp.json()["data"]["id"]
        entries = await ApiAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(route_id)]
        assert len(matching) == 1
        assert matching[0].action == AuditAction.ROUTE_CREATED
        assert matching[0].actor_id == str(caller)

    async def test_create_with_a_missing_path_pattern_is_a_bad_request(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        resp = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"service_id": str(service.id), "name": "missing-path-route"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestUpdateRoute:
    async def test_update_requires_auth(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={
                "service_id": str(service.id),
                "name": "update-noauth-route",
                "path_pattern": "/x",
            },
        )
        route_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/gateway/routes/{route_id}",
            params={"organization_id": str(organization_id)},
            json={"description": "new"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_update_edits_fields(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"service_id": str(service.id), "name": "edit-route", "path_pattern": "/edit"},
        )
        route_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/gateway/routes/{route_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"priority": 5, "description": "edited"},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["priority"] == 5
        assert data["description"] == "edited"

    async def test_update_records_an_audit_entry_with_route_updated(
        self,
        client: AsyncClient,
        auth_headers,
        make_service,
        organization_id: uuid.UUID,
        db_session,
    ) -> None:
        service = await make_service()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={
                "service_id": str(service.id),
                "name": "audit-update-route",
                "path_pattern": "/y",
            },
        )
        route_id = created.json()["data"]["id"]
        await client.put(
            f"/gateway/routes/{route_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"description": "changed"},
        )
        entries = await ApiAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(route_id)]
        assert AuditAction.ROUTE_UPDATED in {e.action for e in matching}

    async def test_update_returns_404_for_a_missing_route(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            f"/gateway/routes/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"description": "does not matter"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestDeleteRoute:
    async def test_delete_requires_auth(
        self, client: AsyncClient, auth_headers, make_service, organization_id: uuid.UUID
    ) -> None:
        service = await make_service()
        created = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "service_id": str(service.id),
                "name": "delete-noauth-route",
                "path_pattern": "/z",
            },
        )
        route_id = created.json()["data"]["id"]
        resp = await client.delete(
            f"/gateway/routes/{route_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_delete_removes_the_route_and_records_route_deleted(
        self,
        client: AsyncClient,
        auth_headers,
        make_service,
        organization_id: uuid.UUID,
        db_session,
    ) -> None:
        service = await make_service()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/routes",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"service_id": str(service.id), "name": "delete-route", "path_pattern": "/delete"},
        )
        route_id = created.json()["data"]["id"]
        resp = await client.delete(
            f"/gateway/routes/{route_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_NO_CONTENT

        confirm = await client.get(
            f"/gateway/routes/{route_id}", params={"organization_id": str(organization_id)}
        )
        assert confirm.status_code == HTTP_NOT_FOUND

        entries = await ApiAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(route_id)]
        assert AuditAction.ROUTE_DELETED in {e.action for e in matching}

    async def test_delete_returns_404_for_a_missing_route(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            f"/gateway/routes/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND
