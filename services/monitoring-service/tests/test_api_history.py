"""Tests for the ``/monitoring/history`` router."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from shared_core.enums.health_status import HealthStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.monitoring_history import MonitoringHistoryRepository
from app.services.history import MonitoringHistoryService
from tests.conftest import AuthHeadersFn, make_target


class TestMonitoringHistoryApi:
    async def test_list_by_target_id(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        target = await make_target(db_session)
        await MonitoringHistoryService(MonitoringHistoryRepository(db_session)).record(
            organization_id=target.organization_id,
            target_id=target.id,
            status=HealthStatus.HEALTHY,
            score=90.0,
        )
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/monitoring/history", params={"target_id": str(target.id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_list_by_organization_id(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        target = await make_target(db_session)
        await MonitoringHistoryService(MonitoringHistoryRepository(db_session)).record(
            organization_id=target.organization_id,
            target_id=target.id,
            status=HealthStatus.DEGRADED,
            score=None,
        )
        headers = auth_headers(uuid.uuid4())
        response = await client.get(
            "/monitoring/history",
            params={"organization_id": str(target.organization_id)},
            headers=headers,
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_no_filter_returns_empty(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get("/monitoring/history", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get("/monitoring/history")
        assert response.status_code == 401
