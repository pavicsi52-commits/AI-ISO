"""HTTP tests for implementation tasks, runs, and validation gates.

Routes whose handler declares a ``caller: CurrentUserId`` parameter
(``start_implementation``, ``move_to_validation``, ``complete_implementation``,
``record_validation``) need ``Authorization`` headers; the plain task and
validation CRUD routes do not.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


async def _add_task(
    client: AsyncClient, organization_id: uuid.UUID, change_id: uuid.UUID, **overrides: object
) -> dict:
    payload = {"title": "Apply the migration script", **overrides}
    resp = await client.post(
        f"/changes/{change_id}/tasks",
        params={"organization_id": str(organization_id)},
        json=payload,
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestTasks:
    async def test_add_task_returns_the_new_task(
        self, client: AsyncClient, organization_id: uuid.UUID, make_change
    ) -> None:
        change = await make_change()
        data = await _add_task(client, organization_id, change.id, assignee_id="alice")
        assert data["title"] == "Apply the migration script"
        assert data["assignee_id"] == "alice"
        assert data["status"] == "pending"

    async def test_list_tasks_finds_it(
        self, client: AsyncClient, organization_id: uuid.UUID, make_change
    ) -> None:
        change = await make_change()
        created = await _add_task(client, organization_id, change.id)
        resp = await client.get(
            f"/changes/{change.id}/tasks", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_complete_task_marks_it_done(
        self, client: AsyncClient, organization_id: uuid.UUID, make_change
    ) -> None:
        change = await make_change()
        created = await _add_task(client, organization_id, change.id)
        resp = await client.post(
            f"/tasks/{created['id']}/complete",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["completed_at"] is not None

    async def test_fail_task_marks_it_failed(
        self, client: AsyncClient, organization_id: uuid.UUID, make_change
    ) -> None:
        change = await make_change()
        created = await _add_task(client, organization_id, change.id)
        resp = await client.post(
            f"/tasks/{created['id']}/fail",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "failed"


class TestImplementationLifecycle:
    async def test_start_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_ready_change
    ) -> None:
        change = await make_ready_change()
        resp = await client.post(
            f"/changes/{change.id}/implementation/start",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_start_moves_a_ready_change_into_progress(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_ready_change
    ) -> None:
        change = await make_ready_change()
        caller = uuid.uuid4()
        resp = await client.post(
            f"/changes/{change.id}/implementation/start",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(caller),
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["status"] == "in_progress"
        assert data["started_by"] == str(caller)

    async def test_start_on_a_change_already_in_progress_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        resp = await client.post(
            f"/changes/{change.id}/implementation/start",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_move_to_validation_with_no_open_tasks_succeeds(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        resp = await client.post(
            f"/changes/{change.id}/implementation/validate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK, resp.text
        assert resp.json()["data"]["progress_percent"] == 100

    async def test_move_to_validation_with_unfinished_task_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        await _add_task(client, organization_id, change.id)
        resp = await client.post(
            f"/changes/{change.id}/implementation/validate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_complete_after_validation_succeeds(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        await client.post(
            f"/changes/{change.id}/implementation/validate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        resp = await client.post(
            f"/changes/{change.id}/implementation/complete",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK, resp.text
        assert resp.json()["data"]["status"] == "completed"

    async def test_complete_with_a_failed_gate_validation_is_refused(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        await client.post(
            f"/changes/{change.id}/implementation/validate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        await client.post(
            f"/changes/{change.id}/validations",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "post_change", "status": "failed", "is_gate": True},
        )
        resp = await client.post(
            f"/changes/{change.id}/implementation/complete",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_CONFLICT


class TestValidations:
    async def test_record_validation_returns_the_new_run(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        resp = await client.post(
            f"/changes/{change.id}/validations",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "kind": "pre_change",
                "status": "passed",
                "summary": "All health checks green.",
                "ran_by": "qa-1",
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["kind"] == "pre_change"
        assert data["status"] == "passed"
        assert data["ran_by"] == "qa-1"

    async def test_list_validations_finds_it(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_in_progress_change
    ) -> None:
        change = await make_in_progress_change()
        created = await client.post(
            f"/changes/{change.id}/validations",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "health", "status": "passed"},
        )
        resp = await client.get(
            f"/changes/{change.id}/validations",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created.json()["data"]["id"] in ids
