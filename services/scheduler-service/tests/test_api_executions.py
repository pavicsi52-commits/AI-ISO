"""HTTP tests for /scheduler/executions -- execution history and log lines.

None of these routes declare a ``caller: CurrentUserId`` parameter, so none
of them need ``Authorization`` headers. Executions are set up through the
plain ``execution_service`` fixture (dispatching a real job), then read back
over HTTP.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import HTTP_NOT_FOUND, HTTP_OK

pytestmark = pytest.mark.asyncio


class TestListExecutions:
    async def test_list_finds_a_dispatched_execution(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job, execution_service
    ) -> None:
        job = await make_job()
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        resp = await client.get(
            "/scheduler/executions", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert str(execution.id) in ids

    async def test_list_filters_by_status(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job, execution_service
    ) -> None:
        job = await make_job()
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        matching = await client.get(
            "/scheduler/executions",
            params={"organization_id": str(organization_id), "status": "completed"},
        )
        assert str(execution.id) in {one["id"] for one in matching.json()["data"]}
        non_matching = await client.get(
            "/scheduler/executions",
            params={"organization_id": str(organization_id), "status": "cancelled"},
        )
        assert str(execution.id) not in {one["id"] for one in non_matching.json()["data"]}

    async def test_list_filters_by_job_id(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job, execution_service
    ) -> None:
        job_a = await make_job(name="Job A")
        job_b = await make_job(name="Job B")
        exec_a = await execution_service.dispatch(organization_id, job_a.id, trigger_source="a")
        await execution_service.dispatch(organization_id, job_b.id, trigger_source="b")
        resp = await client.get(
            "/scheduler/executions",
            params={"organization_id": str(organization_id), "job_id": str(job_a.id)},
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert ids == {str(exec_a.id)}


class TestGetExecution:
    async def test_get_returns_the_execution(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job, execution_service
    ) -> None:
        job = await make_job()
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        resp = await client.get(
            f"/scheduler/executions/{execution.id}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["id"] == str(execution.id)
        assert data["job_id"] == str(job.id)
        assert data["status"] == "completed"

    async def test_get_returns_404_for_a_missing_execution(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/scheduler/executions/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestExecutionLogs:
    async def test_logs_are_empty_for_a_fresh_execution(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job, execution_service
    ) -> None:
        job = await make_job()
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        resp = await client.get(
            f"/scheduler/executions/{execution.id}/logs",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_logs_lists_added_log_lines(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job, execution_service
    ) -> None:
        job = await make_job()
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        await execution_service.add_log(
            organization_id, execution.id, level="info", message="Started."
        )
        resp = await client.get(
            f"/scheduler/executions/{execution.id}/logs",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["execution_id"] == str(execution.id)
        assert rows[0]["message"] == "Started."
        assert rows[0]["level"] == "info"
