"""Repository for :class:`app.models.validation_remediation.ValidationRemediation`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_remediation import ValidationRemediation


class ValidationRemediationRepository(BaseRepository[ValidationRemediation]):
    """CRUD plus lookup for :class:`ValidationRemediation`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationRemediation, tenant_scope=tenant_scope)

    async def list_for_failure(self, failure_id: UUID) -> list[ValidationRemediation]:
        """Every remediation suggested for *failure_id*."""
        stmt = self._base_select().where(ValidationRemediation.failure_id == failure_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[ValidationRemediation]:
        """Every remediation ever suggested for *organization_id*."""
        stmt = self._base_select().where(ValidationRemediation.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationRemediationRepository"]
