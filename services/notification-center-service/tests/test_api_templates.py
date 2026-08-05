"""HTTP tests for /notifications/templates -- CRUD, versioning, and preview.

Only ``create``/``update`` declare a ``caller: CurrentUserId`` parameter
and need ``Authorization`` headers; every read (list, get, versions,
preview) does not.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


async def _create_template(
    client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID, **overrides: object
) -> dict:
    payload = {
        "template_key": "job.failed",
        "name": "Job Failed",
        "body_template": "Hello {{ name }}, your job failed.",
        **overrides,
    }
    resp = await client.post(
        "/notifications/templates",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json=payload,
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestCreate:
    async def test_create_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/templates",
            params={"organization_id": str(organization_id)},
            json={"template_key": "x", "name": "X", "body_template": "Hi"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_template(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        data = await _create_template(client, auth_headers(uuid.uuid4()), organization_id)
        assert data["template_key"] == "job.failed"
        assert data["name"] == "Job Failed"
        assert data["current_version"] == 1
        assert data["is_active"] is True
        assert data["format"] == "plain_text"
        assert data["locale"] == "en"

    async def test_create_with_invalid_jinja_syntax_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/templates",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "template_key": "broken",
                "name": "Broken",
                "body_template": "Hello {{ name",
            },
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_create_missing_required_field_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/templates",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"template_key": "x"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestGetAndList:
    async def test_get_returns_the_template(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_template(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            f"/notifications/templates/{created['id']}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]

    async def test_get_returns_404_for_a_missing_template(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/notifications/templates/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_finds_the_created_template(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_template(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            "/notifications/templates", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_list_filters_by_is_active(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_template(client, auth_headers(uuid.uuid4()), organization_id)
        active = await client.get(
            "/notifications/templates",
            params={"organization_id": str(organization_id), "is_active": "true"},
        )
        assert created["id"] in {one["id"] for one in active.json()["data"]}
        inactive = await client.get(
            "/notifications/templates",
            params={"organization_id": str(organization_id), "is_active": "false"},
        )
        assert created["id"] not in {one["id"] for one in inactive.json()["data"]}


class TestUpdate:
    async def test_update_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_template(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.put(
            f"/notifications/templates/{created['id']}",
            params={"organization_id": str(organization_id)},
            json={"name": "Renamed"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_update_edits_the_name_without_versioning(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_template(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.put(
            f"/notifications/templates/{created['id']}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "Renamed"},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["name"] == "Renamed"
        assert data["current_version"] == 1

    async def test_update_changing_body_bumps_the_version_and_records_one(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_template(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.put(
            f"/notifications/templates/{created['id']}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"body_template": "Hi {{ name }}, it failed again.", "change_note": "Reworded."},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["current_version"] == 2
        assert data["body_template"] == "Hi {{ name }}, it failed again."

        versions = await client.get(
            f"/notifications/templates/{created['id']}/versions",
            params={"organization_id": str(organization_id)},
        )
        assert versions.status_code == HTTP_OK
        rows = versions.json()["data"]
        assert len(rows) == 1
        assert rows[0]["version"] == 1
        assert rows[0]["body_template"] == created["body_template"]
        assert rows[0]["change_note"] == "Reworded."

    async def test_update_returns_404_for_a_missing_template(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            f"/notifications/templates/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "Renamed"},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_update_with_invalid_jinja_syntax_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_template(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.put(
            f"/notifications/templates/{created['id']}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"body_template": "Hi {{ name"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestVersions:
    async def test_versions_is_empty_before_any_content_change(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_template(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            f"/notifications/templates/{created['id']}/versions",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_versions_for_a_missing_template_is_empty_not_404(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        # `list_versions` queries by `template_id` directly, with no
        # existence check first -- the same "list routes return empty
        # rather than 404 for a nonexistent parent" convention already
        # established by `/notifications/{id}/deliveries`.
        resp = await client.get(
            f"/notifications/templates/{uuid.uuid4()}/versions",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []


class TestPreview:
    async def test_preview_renders_variables(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_template(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/notifications/templates/{created['id']}/preview",
            params={"organization_id": str(organization_id)},
            json={"variables": {"name": "Ada"}},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert "Ada" in data["body"]
        assert data["format"] == "plain_text"

    async def test_preview_returns_404_for_a_missing_template(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/notifications/templates/{uuid.uuid4()}/preview",
            params={"organization_id": str(organization_id)},
            json={"variables": {}},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_preview_with_no_variables_body_defaults_to_empty_dict(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_template(
            client, auth_headers(uuid.uuid4()), organization_id, body_template="Static text."
        )
        resp = await client.post(
            f"/notifications/templates/{created['id']}/preview",
            params={"organization_id": str(organization_id)},
            json={},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["body"] == "Static text."
