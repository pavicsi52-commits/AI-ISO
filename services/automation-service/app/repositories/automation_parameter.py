"""Repository for :class:`app.models.automation_parameter.AutomationParameter`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_parameter import AutomationParameter


class AutomationParameterRepository(BaseRepository[AutomationParameter]):
    """CRUD plus lookup for :class:`AutomationParameter`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationParameter, tenant_scope=tenant_scope)

    async def list_for_job(self, job_id: UUID) -> list[AutomationParameter]:
        """Every parameter definition for *job_id*."""
        stmt = self._base_select().where(AutomationParameter.job_id == job_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationParameterRepository"]
