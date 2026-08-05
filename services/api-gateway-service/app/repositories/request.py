"""The API request and response log repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request import ApiRequestLog, ApiResponseLog


class ApiRequestLogRepository(BaseRepository[ApiRequestLog]):
    """One inbound request, per row."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiRequestLog, tenant_scope=tenant_scope)

    async def list_created_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 10_000
    ) -> list[ApiRequestLog]:
        """Requests started within a window, for statistics rollups."""
        stmt = (
            self._base_select()
            .where(ApiRequestLog.organization_id == organization_id)
            .where(ApiRequestLog.started_at >= start)
            .where(ApiRequestLog.started_at < end)
            .order_by(ApiRequestLog.started_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent(self, organization_id: UUID, *, limit: int = 200) -> list[ApiRequestLog]:
        """The most recently started requests, newest first."""
        stmt = (
            self._base_select()
            .where(ApiRequestLog.organization_id == organization_id)
            .order_by(ApiRequestLog.started_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ApiResponseLogRepository(BaseRepository[ApiResponseLog]):
    """One request's own outcome, per row."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ApiResponseLog, tenant_scope=tenant_scope)

    async def list_created_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 10_000
    ) -> list[ApiResponseLog]:
        """Responses completed within a window, for statistics rollups."""
        stmt = (
            self._base_select()
            .where(ApiResponseLog.organization_id == organization_id)
            .where(ApiResponseLog.completed_at >= start)
            .where(ApiResponseLog.completed_at < end)
            .order_by(ApiResponseLog.completed_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status_code(self, organization_id: UUID) -> dict[str, int]:
        """How many responses fall under each HTTP status code."""
        stmt = (
            select(ApiResponseLog.status_code, func.count())
            .where(ApiResponseLog.organization_id == organization_id)
            .where(ApiResponseLog.deleted_at.is_(None))
            .group_by(ApiResponseLog.status_code)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(status_code): int(count) for status_code, count in rows}


__all__ = ["ApiRequestLogRepository", "ApiResponseLogRepository"]
