"""HTTP tests for /scheduler/jobs -- CRUD, lifecycle, triggers, dependencies, retry policy.

Routes whose handler declares a ``caller: CurrentUserId`` parameter (create,
update, delete, run, pause, resume, cancel) need ``Authorization`` headers;
schedule/history reads and every trigger/dependency/retry-policy route do
not.
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


async def _create_job(
    client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID, **overrides: object
) -> dict:
    payload = {"name": "Nightly inventory sync", "job_type": "custom_job", **overrides}
    resp = await client.post(
        "/scheduler/jobs",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json=payload,
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestCreateGetListUpdateDelete:
    async def test_create_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/scheduler/jobs",
            params={"organization_id": str(organization_id)},
            json={"name": "x", "job_type": "custom_job"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_job(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        data = await _create_job(client, auth_headers(uuid.uuid4()), organization_id)
        assert data["name"] == "Nightly inventory sync"
        assert data["job_type"] == "custom_job"
        assert data["status"] == "active"
        assert data["priority"] == "normal"
        assert data["run_count"] == 0

    async def test_create_missing_name_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/scheduler/jobs",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"job_type": "custom_job"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_get_returns_the_job(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_job(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            f"/scheduler/jobs/{created['id']}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]

    async def test_get_returns_404_for_a_missing_job(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/scheduler/jobs/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_finds_the_created_job(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_job(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get("/scheduler/jobs", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_list_filters_by_status(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_job(client, auth_headers(uuid.uuid4()), organization_id)
        matching = await client.get(
            "/scheduler/jobs",
            params={"organization_id": str(organization_id), "status": "active"},
        )
        assert created["id"] in {one["id"] for one in matching.json()["data"]}
        non_matching = await client.get(
            "/scheduler/jobs",
            params={"organization_id": str(organization_id), "status": "paused"},
        )
        assert created["id"] not in {one["id"] for one in non_matching.json()["data"]}

    async def test_update_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_job(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.put(
            f"/scheduler/jobs/{created['id']}",
            params={"organization_id": str(organization_id)},
            json={"name": "Renamed job"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_update_edits_a_job(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_job(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.put(
            f"/scheduler/jobs/{created['id']}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "Renamed job"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["name"] == "Renamed job"

    async def test_delete_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_job(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.delete(
            f"/scheduler/jobs/{created['id']}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_delete_marks_the_job_deleted(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_job(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.delete(
            f"/scheduler/jobs/{created['id']}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "deleted"


class TestLifecycle:
    async def test_run_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/run", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_run_dispatches_an_execution(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/run",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]["execution"]
        assert data["job_id"] == str(job.id)
        assert data["status"] == "completed"
        assert data["trigger_source"] == "manual"

    async def test_run_returns_404_for_a_missing_job(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/scheduler/jobs/{uuid.uuid4()}/run",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_run_a_deleted_job_is_a_conflict(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        headers = auth_headers(uuid.uuid4())
        await client.delete(
            f"/scheduler/jobs/{job.id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/run",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_pause_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/pause", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_pause_pauses_an_active_job(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/pause",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "paused"

    async def test_resume_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/resume", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_resume_resumes_a_paused_job(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        headers = auth_headers(uuid.uuid4())
        await client.post(
            f"/scheduler/jobs/{job.id}/pause",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/resume",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "active"

    async def test_resume_an_already_active_job_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/resume",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_cancel_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/cancel",
            params={"organization_id": str(organization_id)},
            json={},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_cancel_disables_a_job_with_a_reason(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/cancel",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"reason": "No longer needed."},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "disabled"

    async def test_cancel_without_a_reason_is_accepted(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/cancel",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={},
        )
        assert resp.status_code == HTTP_OK

    async def test_cancel_an_already_disabled_job_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        headers = auth_headers(uuid.uuid4())
        await client.post(
            f"/scheduler/jobs/{job.id}/cancel",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={},
        )
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/cancel",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestScheduleAndHistory:
    async def test_get_schedule_returns_the_materialized_state(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job_with_cron_trigger
    ) -> None:
        job = await make_job_with_cron_trigger()
        resp = await client.get(
            f"/scheduler/jobs/{job.id}/schedule", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["job_id"] == str(job.id)
        assert data["next_run_at"] is not None

    async def test_get_schedule_returns_404_for_a_missing_job(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/scheduler/jobs/{uuid.uuid4()}/schedule",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_get_history_lists_every_transition(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.get(
            f"/scheduler/jobs/{job.id}/history", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        rows = resp.json()["data"]
        assert len(rows) == 2
        assert {row["to_status"] for row in rows} == {"registered", "active"}


class TestTriggers:
    async def test_add_trigger_returns_the_new_trigger(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/triggers",
            params={"organization_id": str(organization_id)},
            json={"trigger_type": "cron", "cron_expression": "0 3 * * *"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["job_id"] == str(job.id)
        assert data["trigger_type"] == "cron"
        assert data["enabled"] is True

    async def test_add_trigger_returns_404_for_a_missing_job(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/scheduler/jobs/{uuid.uuid4()}/triggers",
            params={"organization_id": str(organization_id)},
            json={"trigger_type": "cron", "cron_expression": "0 3 * * *"},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_triggers_finds_it(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        created = await client.post(
            f"/scheduler/jobs/{job.id}/triggers",
            params={"organization_id": str(organization_id)},
            json={"trigger_type": "interval", "interval_seconds": 60},
        )
        resp = await client.get(
            f"/scheduler/jobs/{job.id}/triggers", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created.json()["data"]["id"] in ids

    async def test_set_trigger_enabled_disables_it(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        created = await client.post(
            f"/scheduler/jobs/{job.id}/triggers",
            params={"organization_id": str(organization_id)},
            json={"trigger_type": "cron", "cron_expression": "0 3 * * *"},
        )
        trigger_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/scheduler/jobs/triggers/{trigger_id}/enabled",
            params={"organization_id": str(organization_id)},
            json={"enabled": False},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["enabled"] is False

    async def test_set_trigger_enabled_returns_404_for_a_missing_trigger(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            f"/scheduler/jobs/triggers/{uuid.uuid4()}/enabled",
            params={"organization_id": str(organization_id)},
            json={"enabled": True},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_remove_trigger(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        created = await client.post(
            f"/scheduler/jobs/{job.id}/triggers",
            params={"organization_id": str(organization_id)},
            json={"trigger_type": "cron", "cron_expression": "0 3 * * *"},
        )
        trigger_id = created.json()["data"]["id"]
        resp = await client.delete(
            f"/scheduler/jobs/triggers/{trigger_id}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] is None

    async def test_remove_trigger_returns_404_for_a_missing_trigger(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            f"/scheduler/jobs/triggers/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestDependencies:
    async def test_add_dependency_returns_the_new_edge(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        parent = await make_job(name="Parent job")
        child = await make_job(name="Child job")
        resp = await client.post(
            f"/scheduler/jobs/{child.id}/dependencies",
            params={"organization_id": str(organization_id)},
            json={"parent_job_id": str(parent.id)},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["parent_job_id"] == str(parent.id)
        assert data["child_job_id"] == str(child.id)
        assert data["dependency_type"] == "sequential"

    async def test_add_dependency_to_self_is_a_bad_request(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{job.id}/dependencies",
            params={"organization_id": str(organization_id)},
            json={"parent_job_id": str(job.id)},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_add_dependency_returns_404_for_a_missing_parent(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        child = await make_job()
        resp = await client.post(
            f"/scheduler/jobs/{child.id}/dependencies",
            params={"organization_id": str(organization_id)},
            json={"parent_job_id": str(uuid.uuid4())},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_dependencies_finds_it(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        parent = await make_job(name="Parent job")
        child = await make_job(name="Child job")
        await client.post(
            f"/scheduler/jobs/{child.id}/dependencies",
            params={"organization_id": str(organization_id)},
            json={"parent_job_id": str(parent.id)},
        )
        resp = await client.get(
            f"/scheduler/jobs/{child.id}/dependencies",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["parent_job_id"] == str(parent.id)

    async def test_remove_dependency(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        parent = await make_job(name="Parent job")
        child = await make_job(name="Child job")
        created = await client.post(
            f"/scheduler/jobs/{child.id}/dependencies",
            params={"organization_id": str(organization_id)},
            json={"parent_job_id": str(parent.id)},
        )
        dependency_id = created.json()["data"]["id"]
        resp = await client.delete(
            f"/scheduler/jobs/dependencies/{dependency_id}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] is None

    async def test_remove_dependency_returns_404_for_a_missing_dependency(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            f"/scheduler/jobs/dependencies/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestRetryPolicy:
    async def test_get_retry_policy_is_none_when_unconfigured(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.get(
            f"/scheduler/jobs/{job.id}/retry-policy",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] is None

    async def test_set_retry_policy_creates_it(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        resp = await client.put(
            f"/scheduler/jobs/{job.id}/retry-policy",
            params={"organization_id": str(organization_id)},
            json={"max_attempts": 5, "base_delay_seconds": 10, "max_delay_seconds": 120},
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["job_id"] == str(job.id)
        assert data["max_attempts"] == 5
        assert data["retry_type"] == "exponential_backoff"

    async def test_set_retry_policy_twice_replaces_it(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        await client.put(
            f"/scheduler/jobs/{job.id}/retry-policy",
            params={"organization_id": str(organization_id)},
            json={"max_attempts": 5},
        )
        resp = await client.put(
            f"/scheduler/jobs/{job.id}/retry-policy",
            params={"organization_id": str(organization_id)},
            json={"max_attempts": 9},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["max_attempts"] == 9

        confirm = await client.get(
            f"/scheduler/jobs/{job.id}/retry-policy",
            params={"organization_id": str(organization_id)},
        )
        assert confirm.json()["data"]["max_attempts"] == 9

    async def test_get_retry_policy_after_set(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        job = await make_job()
        await client.put(
            f"/scheduler/jobs/{job.id}/retry-policy",
            params={"organization_id": str(organization_id)},
            json={"max_attempts": 7},
        )
        resp = await client.get(
            f"/scheduler/jobs/{job.id}/retry-policy",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["max_attempts"] == 7
