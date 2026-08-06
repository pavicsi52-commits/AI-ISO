"""HTTP tests for /gateway/services (backend service registration + versions).

``GET`` needs no auth; ``POST``/``PUT``/``DELETE`` on a service declare a
``caller: CurrentUserId`` parameter and need ``Authorization`` headers.
The nested ``/versions`` sub-routes declare no such parameter and need no
auth at all.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.enums import AuditAction
from app.repositories.governance import ApiAuditRepository
from tests.conftest import (
    FAKE_BACKEND_URL,
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NO_CONTENT,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


def _instance(url: str = FAKE_BACKEND_URL, weight: int = 100) -> dict:
    return {"url": url, "weight": weight}


class TestListServices:
    async def test_list_is_empty_before_any_registration(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/gateway/services", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_registered_service(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "orders-service", "instances": [_instance()]},
        )
        resp = await client.get(
            "/gateway/services", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        names = {row["name"] for row in resp.json()["data"]}
        assert "orders-service" in names

    async def test_list_filters_by_enabled(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "disabled-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        await client.put(
            f"/gateway/services/{service_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"enabled": False},
        )
        resp = await client.get(
            "/gateway/services",
            params={"organization_id": str(organization_id), "enabled": "false"},
        )
        assert resp.status_code == HTTP_OK
        names = {row["name"] for row in resp.json()["data"]}
        assert "disabled-service" in names

        resp_enabled = await client.get(
            "/gateway/services",
            params={"organization_id": str(organization_id), "enabled": "true"},
        )
        names_enabled = {row["name"] for row in resp_enabled.json()["data"]}
        assert "disabled-service" not in names_enabled


class TestGetService:
    async def test_get_finds_a_registered_service(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "get-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/gateway/services/{service_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == service_id

    async def test_get_returns_404_for_a_missing_service(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/gateway/services/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_get_is_scoped_to_its_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "scoped-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/gateway/services/{service_id}", params={"organization_id": str(uuid.uuid4())}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestCreateService:
    async def test_create_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            json={"name": "no-auth-service", "instances": [_instance()]},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_service(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "name": "billing-service",
                "instances": [_instance()],
                "description": "Billing backend.",
                "health_check_path": "/health",
                "timeout_seconds": 5.0,
                "circuit_breaker_enabled": True,
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["name"] == "billing-service"
        assert data["description"] == "Billing backend."
        assert data["instances"][0]["url"] == FAKE_BACKEND_URL
        assert data["load_balancing_strategy"] == "round_robin"
        assert data["enabled"] is True

    async def test_create_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        caller = uuid.uuid4()
        resp = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(caller),
            json={"name": "audited-service", "instances": [_instance()]},
        )
        service_id = resp.json()["data"]["id"]
        entries = await ApiAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(service_id)]
        assert len(matching) == 1
        assert matching[0].action == AuditAction.SERVICE_REGISTERED
        assert matching[0].actor_id == str(caller)

    async def test_create_with_a_missing_name_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"instances": [_instance()]},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestUpdateService:
    async def test_update_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "update-noauth-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/gateway/services/{service_id}",
            params={"organization_id": str(organization_id)},
            json={"description": "new description"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_update_edits_fields(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "edit-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/gateway/services/{service_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"description": "updated description", "circuit_breaker_enabled": False},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["description"] == "updated description"
        assert data["circuit_breaker_enabled"] is False

    async def test_update_replaces_instances(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "reinstance-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/gateway/services/{service_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"instances": [_instance("http://second.test", 50)]},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["instances"] == [{"url": "http://second.test", "weight": 50}]

    async def test_update_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "audit-update-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        await client.put(
            f"/gateway/services/{service_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"description": "changed"},
        )
        entries = await ApiAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(service_id)]
        assert AuditAction.SERVICE_UPDATED in {e.action for e in matching}

    async def test_update_returns_404_for_a_missing_service(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            f"/gateway/services/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"description": "does not matter"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestDeleteService:
    async def test_delete_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "delete-noauth-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        resp = await client.delete(
            f"/gateway/services/{service_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_delete_removes_the_service(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "delete-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        resp = await client.delete(
            f"/gateway/services/{service_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_NO_CONTENT

        confirm = await client.get(
            f"/gateway/services/{service_id}", params={"organization_id": str(organization_id)}
        )
        assert confirm.status_code == HTTP_NOT_FOUND

    async def test_delete_returns_404_for_a_missing_service(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            f"/gateway/services/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestListVersions:
    async def test_list_is_empty_before_any_version_is_registered(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "no-versions-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/gateway/services/{service_id}/versions",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_registered_version(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "versioned-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        await client.post(
            f"/gateway/services/{service_id}/versions",
            params={"organization_id": str(organization_id)},
            json={"service_id": service_id, "version": "v1"},
        )
        resp = await client.get(
            f"/gateway/services/{service_id}/versions",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        versions = {row["version"] for row in resp.json()["data"]}
        assert "v1" in versions


class TestCreateVersion:
    async def test_create_needs_no_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "create-version-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        resp = await client.post(
            f"/gateway/services/{service_id}/versions",
            params={"organization_id": str(organization_id)},
            json={"service_id": service_id, "version": "v2"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["version"] == "v2"
        assert data["is_default"] is False
        assert data["is_deprecated"] is False

    async def test_setting_a_new_default_demotes_the_previous_one(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "default-version-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        first = await client.post(
            f"/gateway/services/{service_id}/versions",
            params={"organization_id": str(organization_id)},
            json={"service_id": service_id, "version": "v1", "is_default": True},
        )
        assert first.json()["data"]["is_default"] is True

        second = await client.post(
            f"/gateway/services/{service_id}/versions",
            params={"organization_id": str(organization_id)},
            json={"service_id": service_id, "version": "v2", "is_default": True},
        )
        assert second.json()["data"]["is_default"] is True

        listing = await client.get(
            f"/gateway/services/{service_id}/versions",
            params={"organization_id": str(organization_id)},
        )
        by_version = {row["version"]: row for row in listing.json()["data"]}
        assert by_version["v1"]["is_default"] is False
        assert by_version["v2"]["is_default"] is True


class TestDeprecateVersion:
    async def test_deprecate_marks_the_version_deprecated(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "deprecate-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        version = await client.post(
            f"/gateway/services/{service_id}/versions",
            params={"organization_id": str(organization_id)},
            json={"service_id": service_id, "version": "v1"},
        )
        version_id = version.json()["data"]["id"]

        resp = await client.post(
            f"/gateway/services/{service_id}/versions/{version_id}/deprecate",
            params={"organization_id": str(organization_id)},
            json={"message": "Use v2 instead.", "sunset_at": "2030-01-01T00:00:00Z"},
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["is_deprecated"] is True
        assert data["deprecation_message"] == "Use v2 instead."
        assert data["sunset_at"] is not None

    async def test_deprecate_with_no_body_fields_still_marks_deprecated(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "deprecate-bare-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        version = await client.post(
            f"/gateway/services/{service_id}/versions",
            params={"organization_id": str(organization_id)},
            json={"service_id": service_id, "version": "v1"},
        )
        version_id = version.json()["data"]["id"]

        resp = await client.post(
            f"/gateway/services/{service_id}/versions/{version_id}/deprecate",
            params={"organization_id": str(organization_id)},
            json={},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["is_deprecated"] is True

    async def test_deprecate_is_scoped_to_its_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        # Regression test for a genuine tenant-isolation bug:
        # `VersionService.deprecate` used to call the generic,
        # organization-unscoped `require_by_id` instead of an
        # organization-scoped lookup, so any organization could deprecate
        # any other organization's version by id.
        created = await client.post(
            "/gateway/services",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "cross-org-service", "instances": [_instance()]},
        )
        service_id = created.json()["data"]["id"]
        version = await client.post(
            f"/gateway/services/{service_id}/versions",
            params={"organization_id": str(organization_id)},
            json={"service_id": service_id, "version": "v1"},
        )
        version_id = version.json()["data"]["id"]

        other_org = uuid.uuid4()
        resp = await client.post(
            f"/gateway/services/{service_id}/versions/{version_id}/deprecate",
            params={"organization_id": str(other_org)},
            json={"message": "Should not apply."},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_deprecate_returns_404_for_a_missing_version(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/gateway/services/{uuid.uuid4()}/versions/{uuid.uuid4()}/deprecate",
            params={"organization_id": str(organization_id)},
            json={},
        )
        assert resp.status_code == HTTP_NOT_FOUND
