"""Repository for :class:`app.models.validation_execution.ValidationExecution`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationExecutionStatus
from app.models.validation_execution import ValidationExecution


class ValidationExecutionRepository(BaseRepository[ValidationExecution]):
    """CRUD plus lookup for :class:`ValidationExecution`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationExecution, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, status: ValidationExecutionStatus | None = None
    ) -> list[ValidationExecution]:
        """Every execution belonging to *organization_id*, optionally filtered by status."""
        stmt = self._base_select().where(ValidationExecution.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ValidationExecution.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_profile(self, profile_id: UUID) -> list[ValidationExecution]:
        """Every execution of *profile_id*, most recent first."""
        stmt = (
            self._base_select()
            .where(ValidationExecution.profile_id == profile_id)
            .order_by(ValidationExecution.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationExecutionRepository"]
