"""Tests for the ``/playbooks`` router, including the live route-
registration-order fix (literal sibling paths like ``/playbooks/search``
must never be swallowed by the ``GET /playbooks/{id}`` catch-all).
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


def _create_body(organization_id: uuid.UUID, name: str = "deploy-app") -> dict[str, object]:
    return {
        "organization_id": str(organization_id),
        "name": name,
        "display_name": "Deploy App",
        "description": "Deploys the app.",
        "content_type": "shell_script",
        "initial_content": "echo deploying",
    }


class TestPlaybooksApi:
    async def test_create_then_get_playbook(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        create_response = await client.post(
            "/playbooks", json=_create_body(org_id), headers=headers
        )
        assert create_response.status_code == 201
        playbook_id = create_response.json()["data"]["id"]

        get_response = await client.get(f"/playbooks/{playbook_id}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["data"]["name"] == "deploy-app"
        assert get_response.json()["data"]["current_version"] == "1.0.0"

    async def test_create_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post("/playbooks", json=_create_body(uuid.uuid4()))
        assert response.status_code == 401

    async def test_list_playbooks_filters_by_org(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        await client.post("/playbooks", json=_create_body(org_id), headers=headers)

        response = await client.get(
            "/playbooks", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_update_playbook(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/playbooks", json=_create_body(org_id), headers=headers)
        playbook_id = created.json()["data"]["id"]

        response = await client.put(
            f"/playbooks/{playbook_id}",
            json={
                "name": "renamed",
                "display_name": "Renamed",
                "status": "published",
                "metadata": {},
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "renamed"
        assert response.json()["data"]["status"] == "published"

    async def test_delete_playbook(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/playbooks", json=_create_body(org_id), headers=headers)
        playbook_id = created.json()["data"]["id"]

        delete_response = await client.delete(f"/playbooks/{playbook_id}", headers=headers)
        assert delete_response.status_code == 200

        get_response = await client.get(f"/playbooks/{playbook_id}", headers=headers)
        assert get_response.status_code == 404

    async def test_list_playbook_versions(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/playbooks", json=_create_body(org_id), headers=headers)
        playbook_id = created.json()["data"]["id"]

        response = await client.get(f"/playbooks/{playbook_id}/versions", headers=headers)
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1
        assert response.json()["data"][0]["version_number"] == "1.0.0"

    async def test_approve_playbook(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/playbooks", json=_create_body(org_id), headers=headers)
        playbook_id = created.json()["data"]["id"]

        response = await client.post(
            f"/playbooks/{playbook_id}/approve",
            json={"approval_type": "technical", "comments": "LGTM"},
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["data"]["status"] == "approved"

    async def test_publish_playbook(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/playbooks", json=_create_body(org_id), headers=headers)
        playbook_id = created.json()["data"]["id"]

        response = await client.post(f"/playbooks/{playbook_id}/publish", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "published"

    async def test_import_playbook_creates_tags_and_labels(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        response = await client.post(
            "/playbooks/import",
            json={
                "playbook": _create_body(org_id, name="imported"),
                "tags": ["prod", "nginx"],
                "labels": {"team": "platform"},
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["data"]["name"] == "imported"

    async def test_export_playbook_round_trips_content(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        created = await client.post("/playbooks", json=_create_body(org_id), headers=headers)
        playbook_id = created.json()["data"]["id"]

        response = await client.post(
            "/playbooks/export", params={"playbook_id": playbook_id}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["content"] == "echo deploying"

    async def test_search_route_not_swallowed_by_playbook_id_catch_all(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        """Live proof of the route-registration-order fix: a request to
        the literal ``/playbooks/search`` path must reach the search
        router, not be matched by ``GET /playbooks/{playbook_id}`` and
        fail UUID parsing on the literal string ``"search"``.
        """
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/playbooks/search", params={"organization_id": str(uuid.uuid4())}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_get_missing_playbook_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(f"/playbooks/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404
