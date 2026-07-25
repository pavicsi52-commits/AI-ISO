"""Tests for the ``/automation/executions`` router."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient

from tests.conftest import AuthHeadersFn


def _job_body(*, organization_id: uuid.UUID) -> dict[str, object]:
    return {
        "organization_id": str(organization_id),
        "project_id": None,
        "name": "job-for-executions",
        "description": None,
        "automation_type": "custom_automation",
        "playbook_type": "shell_script",
        "execution_mode": "manual",
        "content": "echo hi",
        "target_selector": {},
        "variables": {},
        "tags": [],
        "timeout_seconds": None,
        "owner_id": None,
    }


async def _create_execution(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    org_id = uuid.uuid4()
    job_response = await client.post(
        "/automation/jobs", json=_job_body(organization_id=org_id), headers=headers
    )
    job_id = job_response.json()["data"]["id"]
    exec_response = await client.post(
        f"/automation/jobs/{job_id}/execute", json={}, headers=headers
    )
    return exec_response.json()["data"]  # type: ignore[no-any-return]


class TestExecutionsRouter:
    async def test_list_executions(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        execution = await _create_execution(client, headers)
        response = await client.get(
            "/automation/executions",
            params={"organization_id": execution["organization_id"]},
            headers=headers,
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_get_execution(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        execution = await _create_execution(client, headers)
        response = await client.get(f"/automation/executions/{execution['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == execution["id"]

    async def test_get_execution_not_found(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        response = await client.get(
            f"/automation/executions/{uuid.uuid4()}", headers=auth_headers(uuid.uuid4())
        )
        assert response.status_code == 404

    async def test_list_execution_logs_empty(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        execution = await _create_execution(client, headers)
        response = await client.get(
            f"/automation/executions/{execution['id']}/logs", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_list_execution_artifacts_empty(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        execution = await _create_execution(client, headers)
        response = await client.get(
            f"/automation/executions/{execution['id']}/artifacts", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_list_executions_filters_by_status(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        execution = await _create_execution(client, headers)
        response = await client.get(
            "/automation/executions",
            params={"organization_id": execution["organization_id"], "status": "completed"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"] == []
