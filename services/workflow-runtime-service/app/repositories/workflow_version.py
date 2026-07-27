"""Repository for :class:`app.models.workflow_version.WorkflowVersion`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_version import WorkflowVersion


class WorkflowVersionRepository(BaseRepository[WorkflowVersion]):
    """CRUD plus lookup for :class:`WorkflowVersion`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowVersion, tenant_scope=tenant_scope)

    async def list_for_definition(self, definition_id: UUID) -> list[WorkflowVersion]:
        """Every version recorded for *definition_id*, newest first."""
        stmt = (
            self._base_select()
            .where(WorkflowVersion.definition_id == definition_id)
            .order_by(desc(WorkflowVersion.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_definition(self, definition_id: UUID) -> WorkflowVersion | None:
        """Return *definition_id*'s most recently created version, or ``None``."""
        stmt = (
            self._base_select()
            .where(WorkflowVersion.definition_id == definition_id)
            .order_by(desc(WorkflowVersion.created_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_number(
        self, definition_id: UUID, version_number: str
    ) -> WorkflowVersion | None:
        """Return *definition_id*'s version numbered exactly *version_number*, or ``None``."""
        stmt = self._base_select().where(
            WorkflowVersion.definition_id == definition_id,
            WorkflowVersion.version_number == version_number,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["WorkflowVersionRepository"]
