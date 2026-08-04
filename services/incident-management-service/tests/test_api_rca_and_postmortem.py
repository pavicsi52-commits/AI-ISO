"""HTTP tests for root cause, problem, known error, and postmortem routes."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import HTTP_BAD_REQUEST, HTTP_CONFLICT, HTTP_CREATED, HTTP_OK

pytestmark = pytest.mark.asyncio


async def _open_incident(client: AsyncClient, headers: dict[str, str], organization_id) -> dict:
    resp = await client.post(
        "/incidents",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json={"title": "Database CPU spike"},
    )
    assert resp.status_code == HTTP_CREATED
    return resp.json()["data"]


async def _resolve(
    client: AsyncClient, headers: dict[str, str], organization_id, incident_id: str
) -> None:
    for target in ("assigned", "acknowledged", "investigating", "resolved"):
        resp = await client.put(
            f"/incidents/{incident_id}/transition",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"status": target},
        )
        assert resp.status_code == HTTP_OK


class TestRootCause:
    async def test_record_and_list(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        resp = await client.post(
            f"/incidents/{incident['id']}/root-cause",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"method": "manual", "summary": "Bad query plan"},
        )
        assert resp.status_code == HTTP_CREATED
        listed = await client.get(
            f"/incidents/{incident['id']}/root-cause",
            params={"organization_id": str(organization_id)},
        )
        assert len(listed.json()["data"]) == 1

    async def test_confirm(self, client: AsyncClient, auth_headers, organization_id) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        created = await client.post(
            f"/incidents/{incident['id']}/root-cause",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"method": "manual", "summary": "Bad query plan"},
        )
        root_cause_id = created.json()["data"]["id"]
        resp = await client.post(
            f"/root-cause/{root_cause_id}/confirm",
            params={"organization_id": str(organization_id)},
            json={"confirmed_by": "alice"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["is_confirmed"] is True


class TestProblemsAndKnownErrors:
    async def test_create_and_list(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        resp = await client.post(
            "/problems",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"title": "Recurring OOM"},
        )
        assert resp.status_code == HTTP_CREATED
        problem_id = resp.json()["data"]["id"]
        listed = await client.get("/problems", params={"organization_id": str(organization_id)})
        assert problem_id in {one["id"] for one in listed.json()["data"]}

    async def test_get_problem(self, client: AsyncClient, auth_headers, organization_id) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/problems",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"title": "Recurring OOM"},
        )
        problem_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/problems/{problem_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK

    async def test_link_incident(self, client: AsyncClient, auth_headers, organization_id) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        problem = await client.post(
            "/problems",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"title": "Recurring OOM"},
        )
        problem_id = problem.json()["data"]["id"]
        resp = await client.post(
            f"/problems/{problem_id}/link-incident",
            params={"organization_id": str(organization_id)},
            json={"incident_id": incident["id"]},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["incident_count"] == 1

    async def test_transition_to_resolved_without_a_fix_returns_409(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/problems",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"title": "Recurring OOM"},
        )
        problem_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/problems/{problem_id}/transition",
            params={"organization_id": str(organization_id)},
            json={"status": "resolved"},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_record_and_retire_known_error(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        problem = await client.post(
            "/problems",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"title": "Recurring OOM"},
        )
        problem_id = problem.json()["data"]["id"]
        known_error = await client.post(
            f"/problems/{problem_id}/known-errors",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"title": "OOM under load", "root_cause_summary": "Leaky cache"},
        )
        assert known_error.status_code == HTTP_CREATED
        known_error_id = known_error.json()["data"]["id"]
        active = await client.get("/known-errors", params={"organization_id": str(organization_id)})
        assert known_error_id in {one["id"] for one in active.json()["data"]}
        retired = await client.post(
            f"/known-errors/{known_error_id}/retire",
            params={"organization_id": str(organization_id)},
        )
        assert retired.status_code == HTTP_OK
        assert retired.json()["data"]["is_active"] is False


class TestPostmortem:
    async def test_start_before_resolution_returns_400(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        resp = await client.post(
            f"/incidents/{incident['id']}/postmortem",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_start_after_resolution_succeeds(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _resolve(client, headers, organization_id, incident["id"])
        resp = await client.post(
            f"/incidents/{incident['id']}/postmortem",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"author_id": "alice"},
        )
        assert resp.status_code == HTTP_CREATED
        assert resp.json()["data"]["status"] == "draft"

    async def test_get_for_incident_before_starting_is_null(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        resp = await client.get(
            f"/incidents/{incident['id']}/postmortem",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] is None

    async def test_update_content(self, client: AsyncClient, auth_headers, organization_id) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _resolve(client, headers, organization_id, incident["id"])
        created = await client.post(
            f"/incidents/{incident['id']}/postmortem",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={},
        )
        postmortem_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/postmortems/{postmortem_id}",
            params={"organization_id": str(organization_id)},
            json={"executive_summary": "A summary."},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["executive_summary"] == "A summary."

    async def test_action_items_and_completion(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _resolve(client, headers, organization_id, incident["id"])
        created = await client.post(
            f"/incidents/{incident['id']}/postmortem",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={},
        )
        postmortem_id = created.json()["data"]["id"]
        item = await client.post(
            f"/postmortems/{postmortem_id}/action-items",
            params={"organization_id": str(organization_id)},
            json={"title": "Add alert"},
        )
        assert item.status_code == HTTP_CREATED
        item_id = item.json()["data"]["id"]
        listed = await client.get(
            f"/postmortems/{postmortem_id}/action-items",
            params={"organization_id": str(organization_id)},
        )
        assert len(listed.json()["data"]) == 1
        done = await client.post(
            f"/action-items/{item_id}/complete",
            params={"organization_id": str(organization_id)},
        )
        assert done.status_code == HTTP_OK
        assert done.json()["data"]["status"] == "done"

    async def test_transition_approval_refuses_unowned_action_items(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _resolve(client, headers, organization_id, incident["id"])
        created = await client.post(
            f"/incidents/{incident['id']}/postmortem",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={},
        )
        postmortem_id = created.json()["data"]["id"]
        await client.post(
            f"/postmortems/{postmortem_id}/action-items",
            params={"organization_id": str(organization_id)},
            json={"title": "Unowned"},
        )
        await client.put(
            f"/postmortems/{postmortem_id}/transition",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"status": "in_review"},
        )
        resp = await client.put(
            f"/postmortems/{postmortem_id}/transition",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"status": "approved"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_full_lifecycle_to_published(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _resolve(client, headers, organization_id, incident["id"])
        created = await client.post(
            f"/incidents/{incident['id']}/postmortem",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={},
        )
        postmortem_id = created.json()["data"]["id"]
        await client.post(
            f"/postmortems/{postmortem_id}/action-items",
            params={"organization_id": str(organization_id)},
            json={"title": "Owned", "owner_id": "alice"},
        )
        await client.put(
            f"/postmortems/{postmortem_id}/transition",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"status": "in_review"},
        )
        await client.put(
            f"/postmortems/{postmortem_id}/transition",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"status": "approved", "actor_id": "bob"},
        )
        published = await client.put(
            f"/postmortems/{postmortem_id}/transition",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"status": "published"},
        )
        assert published.status_code == HTTP_OK
        assert published.json()["data"]["status"] == "published"

    async def test_get_one_postmortem(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        incident = await _open_incident(client, headers, organization_id)
        await _resolve(client, headers, organization_id, incident["id"])
        created = await client.post(
            f"/incidents/{incident['id']}/postmortem",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={},
        )
        postmortem_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/postmortems/{postmortem_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == postmortem_id
