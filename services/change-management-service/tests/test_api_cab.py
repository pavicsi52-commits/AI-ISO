"""HTTP tests for Change Advisory Board scheduling, voting, and closure.

``schedule_review`` and ``close_meeting`` declare a ``caller:
CurrentUserId`` parameter and need ``Authorization`` headers; casting and
listing votes do not.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import (
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    soon,
)

pytestmark = pytest.mark.asyncio


async def _schedule_review(
    client: AsyncClient, auth_headers, organization_id: uuid.UUID, change_id: uuid.UUID
) -> dict:
    resp = await client.post(
        f"/changes/{change_id}/cab",
        params={"organization_id": str(organization_id)},
        headers=auth_headers(uuid.uuid4()),
        json={
            "scheduled_at": soon(2).isoformat(),
            "chair_id": "cab-chair-1",
            "invited": ["alice", "bob"],
            "agenda": "Review the payments gateway change.",
        },
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestScheduleAndGet:
    async def test_schedule_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        resp = await client.post(
            f"/changes/{change.id}/cab",
            params={"organization_id": str(organization_id)},
            json={"scheduled_at": soon(2).isoformat(), "invited": ["alice"]},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_schedule_returns_the_new_review(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        data = await _schedule_review(client, auth_headers, organization_id, change.id)
        assert data["change_id"] == str(change.id)
        assert data["status"] == "scheduled"
        assert data["invited_count"] == 2
        assert data["chair_id"] == "cab-chair-1"

    async def test_schedule_when_no_review_is_due_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_change
    ) -> None:
        change = await make_change()
        resp = await client.post(
            f"/changes/{change.id}/cab",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"scheduled_at": soon(2).isoformat(), "invited": ["alice"]},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_scheduling_twice_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        await _schedule_review(client, auth_headers, organization_id, change.id)
        resp = await client.post(
            f"/changes/{change.id}/cab",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"scheduled_at": soon(2).isoformat(), "invited": ["alice"]},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_get_for_change_is_null_when_none_scheduled(
        self, client: AsyncClient, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        resp = await client.get(
            f"/changes/{change.id}/cab", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] is None

    async def test_get_for_change_finds_it(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        created = await _schedule_review(client, auth_headers, organization_id, change.id)
        resp = await client.get(
            f"/changes/{change.id}/cab", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]


class TestVotesAndClose:
    async def test_cast_vote_returns_the_new_vote(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await _schedule_review(client, auth_headers, organization_id, change.id)
        resp = await client.post(
            f"/cab/{review['id']}/votes",
            params={"organization_id": str(organization_id)},
            json={"voter_id": "alice", "vote": "approve", "comment": "Looks safe."},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["voter_id"] == "alice"
        assert data["vote"] == "approve"

    async def test_the_same_voter_cannot_vote_twice(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await _schedule_review(client, auth_headers, organization_id, change.id)
        await client.post(
            f"/cab/{review['id']}/votes",
            params={"organization_id": str(organization_id)},
            json={"voter_id": "alice", "vote": "approve"},
        )
        resp = await client.post(
            f"/cab/{review['id']}/votes",
            params={"organization_id": str(organization_id)},
            json={"voter_id": "alice", "vote": "reject"},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_list_votes_finds_it(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await _schedule_review(client, auth_headers, organization_id, change.id)
        await client.post(
            f"/cab/{review['id']}/votes",
            params={"organization_id": str(organization_id)},
            json={"voter_id": "alice", "vote": "approve"},
        )
        resp = await client.get(
            f"/cab/{review['id']}/votes", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert len(resp.json()["data"]) == 1

    async def test_close_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await _schedule_review(client, auth_headers, organization_id, change.id)
        resp = await client.post(
            f"/cab/{review['id']}/close", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_close_tallies_quorum_and_approves(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await _schedule_review(client, auth_headers, organization_id, change.id)
        # invited_count=2, quorum_fraction=0.5 -- one vote already meets quorum.
        await client.post(
            f"/cab/{review['id']}/votes",
            params={"organization_id": str(organization_id)},
            json={"voter_id": "alice", "vote": "approve"},
        )
        resp = await client.post(
            f"/cab/{review['id']}/close",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["quorum_met"] is True
        assert data["outcome"] == "approve"
        assert data["status"] == "completed"

    async def test_closing_twice_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await _schedule_review(client, auth_headers, organization_id, change.id)
        await client.post(
            f"/cab/{review['id']}/votes",
            params={"organization_id": str(organization_id)},
            json={"voter_id": "alice", "vote": "approve"},
        )
        await client.post(
            f"/cab/{review['id']}/close",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        resp = await client.post(
            f"/cab/{review['id']}/close",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_CONFLICT
