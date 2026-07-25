"""Repository for :class:`app.models.automation_artifact.AutomationArtifact`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_artifact import AutomationArtifact


class AutomationArtifactRepository(BaseRepository[AutomationArtifact]):
    """CRUD plus lookup for :class:`AutomationArtifact`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationArtifact, tenant_scope=tenant_scope)

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationArtifact]:
        """Every artifact recorded for *execution_id*."""
        stmt = self._base_select().where(AutomationArtifact.execution_id == execution_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationArtifactRepository"]
