"""HTTP tests for /scheduler/failures -- unrecovered failures and manual recovery.

``list_unrecovered_failures`` needs no authentication; ``recover_failure``
declares ``audit: AuditSvc`` and ``caller: CurrentUserId``, so it needs
``Authorization`` headers. A terminal failure is built directly here via the
``failures_repo`` fixture, attached to a real execution obtained by
dispatching a job through the plain ``execution_service`` fixture first --
the same pattern ``tests/test_recovery_service.py`` uses at the service
level.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from tests.conftest import HTTP_CONFLICT, HTTP_NOT_FOUND, HTTP_OK, HTTP_UNAUTHORIZED

from app.models.history import JobFailure

pytestmark = pytest.mark.asyncio


async def _make_failure(
    execution_service,
    failures_repo,
    organization_id: uuid.UUID,
    job,
    *,
    is_terminal: bool,
    recovered: bool = False,
) -> JobFailure:
    execution = await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
    return await failures_repo.create(
        JobFailure(
            organization_id=organization_id,
            job_id=job.id,
            execution_id=execution.id,
            occurred_at=datetime.now(UTC),
            failure_reason="Simulated failure",
            error_detail="Something went wrong downstream.",
            is_terminal=is_terminal,
            recovered=recovered,
        )
    )


class TestListUnrecoveredFailures:
    async def test_list_returns_empty_when_nothing_is_terminal(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/scheduler/failures", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_returns_only_terminal_unrecovered_failures(
        self,
        client: AsyncClient,
        organization_id: uuid.UUID,
        make_job,
        execution_service,
        failures_repo,
    ) -> None:
        job = await make_job()
        unrecovered_terminal = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=False
        )
        already_recovered = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True, recovered=True
        )

        resp = await client.get(
            "/scheduler/failures", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert ids == {str(unrecovered_terminal.id)}
        assert str(already_recovered.id) not in ids


class TestRecoverFailure:
    async def test_recover_requires_auth(
        self,
        client: AsyncClient,
        organization_id: uuid.UUID,
        make_job,
        execution_service,
        failures_repo,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        resp = await client.post(
            f"/scheduler/failures/{failure.id}/recover",
            params={"organization_id": str(organization_id)},
            json={"action": "manual_recovery"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_recover_marks_the_failure_recovered(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_job,
        execution_service,
        failures_repo,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        resp = await client.post(
            f"/scheduler/failures/{failure.id}/recover",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"action": "automatic_retry", "recovered_by": "ops-1"},
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["recovered"] is True
        assert data["recovered_by"] == "ops-1"
        assert data["recovery_action"] == "automatic_retry"

    async def test_recover_a_non_terminal_failure_is_a_conflict(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_job,
        execution_service,
        failures_repo,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=False
        )
        resp = await client.post(
            f"/scheduler/failures/{failure.id}/recover",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"action": "manual_recovery"},
        )
        assert resp.status_code == HTTP_CONFLICT

    async def test_recover_returns_404_for_a_missing_failure(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/scheduler/failures/{uuid.uuid4()}/recover",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"action": "manual_recovery"},
        )
        assert resp.status_code == HTTP_NOT_FOUND
