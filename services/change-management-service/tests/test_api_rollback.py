"""HTTP tests for rollback planning, approval, and execution.

``start_rollback`` and ``complete_rollback`` declare a ``caller:
CurrentUserId`` parameter and need ``Authorization`` headers; ``plan``,
``list``, ``approve``, and ``fail`` do not.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import (
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


async def _plan(
    client: AsyncClient, organization_id: uuid.UUID, change_id: uuid.UUID, **overrides: object
) -> dict:
    payload = {
        "plan": "Restore the previous container image and re-run smoke tests.",
        "triggered_reason": "Post-deploy error rate spiked above threshold.",
        "triggered_by": "sre-1",
        **overrides,
    }
    resp = await client.post(
        f"/changes/{change_id}/rollback",
        params={"organization_id": str(organization_id)},
        json=payload,
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestPlanAndList:
    async def test_plan_returns_the_new_rollback(
        self, client: AsyncClient, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        data = await _plan(client, organization_id, change.id)
        assert data["status"] == "planned"
        assert data["change_id"] == str(change.id)
        assert data["approved_at"] is None

    async def test_plan_against_an_ineligible_change_is_refused(
        self, client: AsyncClient, organization_id: uuid.UUID, make_change
    ) -> None:
        change = await make_change()
        resp = await client.post(
            f"/changes/{change.id}/rollback",
            params={"organization_id": str(organization_id)},
            json={"plan": "Undo it.", "triggered_reason": "Because."},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_list_finds_the_planned_rollback(
        self, client: AsyncClient, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        created = await _plan(client, organization_id, change.id)
        resp = await client.get(
            f"/changes/{change.id}/rollback", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids


class TestApprove:
    async def test_approve_records_who(
        self, client: AsyncClient, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        created = await _plan(client, organization_id, change.id)
        resp = await client.post(
            f"/rollback/{created['id']}/approve",
            params={"organization_id": str(organization_id)},
            json={"approved_by": "change-manager-1"},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["approved_by"] == "change-manager-1"
        assert data["approved_at"] is not None

    async def test_approve_returns_404_for_a_missing_rollback(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/rollback/{uuid.uuid4()}/approve",
            params={"organization_id": str(organization_id)},
            json={"approved_by": "change-manager-1"},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_approving_an_in_progress_rollback_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        created = await _plan(client, organization_id, change.id)
        await client.post(
            f"/rollback/{created['id']}/approve",
            params={"organization_id": str(organization_id)},
            json={"approved_by": "change-manager-1"},
        )
        await client.post(
            f"/rollback/{created['id']}/start",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        resp = await client.post(
            f"/rollback/{created['id']}/approve",
            params={"organization_id": str(organization_id)},
            json={"approved_by": "someone-else"},
        )
        assert resp.status_code == HTTP_CONFLICT


class TestStart:
    async def test_start_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        created = await _plan(client, organization_id, change.id)
        resp = await client.post(
            f"/rollback/{created['id']}/start",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_start_without_approval_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        created = await _plan(client, organization_id, change.id)
        resp = await client.post(
            f"/rollback/{created['id']}/start",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_start_moves_the_change_to_rolled_back(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_in_progress_change,
        change_service,
    ) -> None:
        change = await make_in_progress_change()
        created = await _plan(client, organization_id, change.id)
        await client.post(
            f"/rollback/{created['id']}/approve",
            params={"organization_id": str(organization_id)},
            json={"approved_by": "change-manager-1"},
        )
        resp = await client.post(
            f"/rollback/{created['id']}/start",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK, resp.text
        assert resp.json()["data"]["status"] == "in_progress"
        reloaded = await change_service.get(organization_id, change.id)
        assert reloaded.status == "rolled_back"


class TestCompleteAndFail:
    async def _started_rollback(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> dict:
        change = await make_in_progress_change()
        created = await _plan(client, organization_id, change.id)
        await client.post(
            f"/rollback/{created['id']}/approve",
            params={"organization_id": str(organization_id)},
            json={"approved_by": "change-manager-1"},
        )
        await client.post(
            f"/rollback/{created['id']}/start",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        return created

    async def test_complete_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        started = await self._started_rollback(
            client, auth_headers, organization_id, make_in_progress_change
        )
        resp = await client.post(
            f"/rollback/{started['id']}/complete",
            params={"organization_id": str(organization_id)},
            json={"validation_summary": "Rollback validated."},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_complete_after_start_succeeds(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        started = await self._started_rollback(
            client, auth_headers, organization_id, make_in_progress_change
        )
        resp = await client.post(
            f"/rollback/{started['id']}/complete",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"validation_summary": "Rollback validated; service healthy."},
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["validation_summary"] == "Rollback validated; service healthy."

    async def test_complete_without_starting_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        created = await _plan(client, organization_id, change.id)
        resp = await client.post(
            f"/rollback/{created['id']}/complete",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_fail_marks_the_attempt_failed(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        started = await self._started_rollback(
            client, auth_headers, organization_id, make_in_progress_change
        )
        resp = await client.post(
            f"/rollback/{started['id']}/fail",
            params={"organization_id": str(organization_id)},
            json={"reason": "The restored image failed its own health check."},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "failed"

    async def test_fail_returns_404_for_a_missing_rollback(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/rollback/{uuid.uuid4()}/fail",
            params={"organization_id": str(organization_id)},
            json={"reason": "n/a"},
        )
        assert resp.status_code == HTTP_NOT_FOUND
