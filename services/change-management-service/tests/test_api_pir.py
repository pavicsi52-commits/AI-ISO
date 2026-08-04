"""HTTP tests for post-implementation reviews and their action items.

``start_review`` and ``transition_review`` declare a ``caller:
CurrentUserId`` parameter and need ``Authorization`` headers; everything
else does not.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


async def _start_review(
    client: AsyncClient, auth_headers, organization_id: uuid.UUID, change_id: uuid.UUID
) -> dict:
    resp = await client.post(
        f"/changes/{change_id}/pir",
        params={"organization_id": str(organization_id)},
        headers=auth_headers(uuid.uuid4()),
        json={"owner_id": "reviewer-1"},
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestStartAndGet:
    async def test_start_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        resp = await client.post(
            f"/changes/{change.id}/pir",
            params={"organization_id": str(organization_id)},
            json={},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_start_returns_the_new_review(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        data = await _start_review(client, auth_headers, organization_id, change.id)
        assert data["status"] == "draft"
        assert data["change_id"] == str(change.id)
        assert data["owner_id"] == "reviewer-1"

    async def test_start_before_the_change_completes_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_change
    ) -> None:
        change = await make_change()
        resp = await client.post(
            f"/changes/{change.id}/pir",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_starting_twice_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        await _start_review(client, auth_headers, organization_id, change.id)
        resp = await client.post(
            f"/changes/{change.id}/pir",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_get_for_change_is_null_when_never_started(
        self, client: AsyncClient, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        resp = await client.get(
            f"/changes/{change.id}/pir", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] is None

    async def test_get_for_change_finds_it(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        resp = await client.get(
            f"/changes/{change.id}/pir", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]

    async def test_get_by_id_returns_404_for_a_missing_review(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/pir/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_get_by_id_finds_it(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        resp = await client.get(
            f"/pir/{created['id']}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]


class TestUpdate:
    async def test_update_edits_content(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        resp = await client.put(
            f"/pir/{created['id']}",
            params={"organization_id": str(organization_id)},
            json={
                "implementation_summary": "Went to plan.",
                "lessons_learned": "Automate the manual smoke test next time.",
            },
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["implementation_summary"] == "Went to plan."
        assert data["lessons_learned"] == "Automate the manual smoke test next time."

    async def test_update_after_approval_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        await client.put(
            f"/pir/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"status": "in_review"},
        )
        await client.put(
            f"/pir/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"status": "approved", "actor_id": "reviewer-1"},
        )
        resp = await client.put(
            f"/pir/{created['id']}",
            params={"organization_id": str(organization_id)},
            json={"implementation_summary": "Too late."},
        )
        assert resp.status_code == HTTP_CONFLICT


class TestTransition:
    async def test_transition_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        resp = await client.put(
            f"/pir/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            json={"status": "in_review"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_draft_to_in_review_succeeds(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        resp = await client.put(
            f"/pir/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"status": "in_review"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "in_review"

    async def test_an_illegal_move_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        resp = await client.put(
            f"/pir/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"status": "approved"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_approval_with_no_unowned_action_items_succeeds(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        await client.put(
            f"/pir/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"status": "in_review"},
        )
        resp = await client.put(
            f"/pir/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"status": "approved", "actor_id": "reviewer-1"},
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["status"] == "approved"
        assert data["approved_by"] == "reviewer-1"

    async def test_approval_blocked_by_an_unowned_action_item(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        await client.put(
            f"/pir/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"status": "in_review"},
        )
        await client.post(
            f"/pir/{created['id']}/action-items",
            params={"organization_id": str(organization_id)},
            json={"title": "Automate the rollback drill."},
        )
        resp = await client.put(
            f"/pir/{created['id']}/transition",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"status": "approved", "actor_id": "reviewer-1"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestActionItems:
    async def test_add_action_item_returns_the_new_item(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        resp = await client.post(
            f"/pir/{created['id']}/action-items",
            params={"organization_id": str(organization_id)},
            json={"title": "Add a missing alert.", "owner_id": "sre-2"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["title"] == "Add a missing alert."
        assert data["owner_id"] == "sre-2"
        assert data["status"] == "pending"

    async def test_list_action_items_finds_it(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        item = await client.post(
            f"/pir/{created['id']}/action-items",
            params={"organization_id": str(organization_id)},
            json={"title": "Add a missing alert."},
        )
        resp = await client.get(
            f"/pir/{created['id']}/action-items", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert item.json()["data"]["id"] in ids

    async def test_complete_action_item_marks_it_done(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_completed_change
    ) -> None:
        change = await make_completed_change()
        created = await _start_review(client, auth_headers, organization_id, change.id)
        item = await client.post(
            f"/pir/{created['id']}/action-items",
            params={"organization_id": str(organization_id)},
            json={"title": "Add a missing alert."},
        )
        item_id = item.json()["data"]["id"]
        resp = await client.post(
            f"/pir-action-items/{item_id}/complete",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["completed_at"] is not None

    async def test_complete_action_item_returns_404_for_a_missing_item(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/pir-action-items/{uuid.uuid4()}/complete",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND
