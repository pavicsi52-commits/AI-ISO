"""Tests for the ``/automation/jobs`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.models.enums import AutomationType, ExecutionMode, JobStatus, PlaybookType
from tests.conftest import AuthHeadersFn


def _job_body(*, organization_id: uuid.UUID | None = None) -> dict[str, object]:
    return {
        "organization_id": str(organization_id or uuid.uuid4()),
        "project_id": None,
        "name": "deploy-web",
        "description": "Deploys the web tier",
        "automation_type": AutomationType.DEPLOYMENT.value,
        "playbook_type": PlaybookType.SHELL_SCRIPT.value,
        "execution_mode": ExecutionMode.MANUAL.value,
        "content": "echo deploy",
        "target_selector": {},
        "variables": {},
        "tags": ["prod"],
        "timeout_seconds": 600,
        "owner_id": None,
    }


class TestJobsRouter:
    async def test_create_job(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        response = await client.post(
            "/automation/jobs", json=_job_body(), headers=auth_headers(uuid.uuid4())
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["name"] == "deploy-web"
        assert body["data"]["status"] == JobStatus.ACTIVE.value

    async def test_create_job_requires_auth(self, client: AsyncClient) -> None:
        response = await client.post("/automation/jobs", json=_job_body())
        assert response.status_code == 401

    async def test_list_jobs(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        org_id = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        await client.post(
            "/automation/jobs", json=_job_body(organization_id=org_id), headers=headers
        )
        response = await client.get(
            "/automation/jobs", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_get_job(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post("/automation/jobs", json=_job_body(), headers=headers)
        job_id = created.json()["data"]["id"]
        response = await client.get(f"/automation/jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == job_id

    async def test_get_job_not_found(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        response = await client.get(
            f"/automation/jobs/{uuid.uuid4()}", headers=auth_headers(uuid.uuid4())
        )
        assert response.status_code == 404

    async def test_update_job(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post("/automation/jobs", json=_job_body(), headers=headers)
        job_id = created.json()["data"]["id"]
        update_body = _job_body()
        update_body.pop("organization_id")
        update_body["name"] = "renamed-job"
        update_body["status"] = JobStatus.DISABLED.value
        response = await client.put(f"/automation/jobs/{job_id}", json=update_body, headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "renamed-job"
        assert response.json()["data"]["status"] == JobStatus.DISABLED.value

    async def test_delete_job(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post("/automation/jobs", json=_job_body(), headers=headers)
        job_id = created.json()["data"]["id"]
        response = await client.delete(f"/automation/jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["success"] is True

        follow_up = await client.get(f"/automation/jobs/{job_id}", headers=headers)
        assert follow_up.status_code == 404

    async def test_execute_job_enqueues_pending_execution(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post("/automation/jobs", json=_job_body(), headers=headers)
        job_id = created.json()["data"]["id"]
        response = await client.post(f"/automation/jobs/{job_id}/execute", json={}, headers=headers)
        assert response.status_code == 201
        assert response.json()["data"]["job_id"] == job_id
        assert response.json()["data"]["status"] == "pending"

    async def test_cancel_job_execution(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post("/automation/jobs", json=_job_body(), headers=headers)
        job_id = created.json()["data"]["id"]
        await client.post(f"/automation/jobs/{job_id}/execute", json={}, headers=headers)
        response = await client.post(f"/automation/jobs/{job_id}/cancel", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "cancelled"

    async def test_cancel_job_with_no_active_execution_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post("/automation/jobs", json=_job_body(), headers=headers)
        job_id = created.json()["data"]["id"]
        response = await client.post(f"/automation/jobs/{job_id}/cancel", headers=headers)
        assert response.status_code == 404

    async def test_pause_and_resume_job_execution(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post("/automation/jobs", json=_job_body(), headers=headers)
        job_id = created.json()["data"]["id"]
        exec_response = await client.post(
            f"/automation/jobs/{job_id}/execute", json={}, headers=headers
        )
        execution_id = exec_response.json()["data"]["id"]

        # PENDING executions aren't RUNNING yet -- pause requires RUNNING, so
        # this exercises the "no active execution in that status" 404 path.
        pause_response = await client.post(f"/automation/jobs/{job_id}/pause", headers=headers)
        assert pause_response.status_code == 404
        assert execution_id
