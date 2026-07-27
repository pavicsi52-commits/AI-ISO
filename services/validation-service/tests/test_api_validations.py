"""Tests for the ``/validations`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


def _create_body(organization_id: uuid.UUID) -> dict[str, object]:
    return {
        "organization_id": str(organization_id),
        "name": "Infra Profile",
        "profile_type": "infrastructure",
        "target_types": ["physical_server"],
        "check_ids": [],
    }


class TestValidationsApi:
    async def test_create_then_get(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/validations", json=_create_body(org_id), headers=headers)
        assert created.status_code == 201
        assert created.json()["data"]["current_version_number"] == "1.0.0"

        validation_id = created.json()["data"]["id"]
        fetched = await client.get(f"/validations/{validation_id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["data"]["name"] == "Infra Profile"

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post("/validations", json=_create_body(uuid.uuid4()))
        assert response.status_code == 401

    async def test_list_filters_by_org(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        await client.post("/validations", json=_create_body(org_id), headers=headers)

        response = await client.get(
            "/validations", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_update_bumps_version(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/validations", json=_create_body(uuid.uuid4()), headers=headers
        )
        validation_id = created.json()["data"]["id"]

        response = await client.put(
            f"/validations/{validation_id}",
            json={"name": "Infra Profile v2", "target_types": [], "check_ids": []},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["current_version_number"] == "1.0.1"

    async def test_delete(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/validations", json=_create_body(uuid.uuid4()), headers=headers
        )
        validation_id = created.json()["data"]["id"]

        deleted = await client.delete(f"/validations/{validation_id}", headers=headers)
        assert deleted.status_code == 200

        fetched = await client.get(f"/validations/{validation_id}", headers=headers)
        assert fetched.status_code == 404

    async def test_get_missing_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(f"/validations/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404

    async def test_execute_enqueues_instance(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/validations", json=_create_body(uuid.uuid4()), headers=headers
        )
        validation_id = created.json()["data"]["id"]

        response = await client.post(
            f"/validations/{validation_id}/execute",
            json={
                "targets": [
                    {"target_type": "physical_server", "external_id": "srv-1", "name": "Server 1"}
                ]
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["data"]["status"] == "queued"

    async def test_cancel_active_execution(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/validations", json=_create_body(uuid.uuid4()), headers=headers
        )
        validation_id = created.json()["data"]["id"]
        await client.post(
            f"/validations/{validation_id}/execute",
            json={
                "targets": [
                    {"target_type": "physical_server", "external_id": "srv-1", "name": "Server 1"}
                ]
            },
            headers=headers,
        )

        response = await client.post(f"/validations/{validation_id}/cancel", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "cancelled"

    async def test_cancel_with_no_active_execution_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/validations", json=_create_body(uuid.uuid4()), headers=headers
        )
        validation_id = created.json()["data"]["id"]

        response = await client.post(f"/validations/{validation_id}/cancel", headers=headers)
        assert response.status_code == 404
