"""Repository for :class:`app.models.validation_exception.ValidationException`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationExceptionStatus
from app.models.validation_exception import ValidationException


class ValidationExceptionRepository(BaseRepository[ValidationException]):
    """CRUD plus lookup for :class:`ValidationException`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationException, tenant_scope=tenant_scope)

    async def list_for_failure(self, failure_id: UUID) -> list[ValidationException]:
        """Every exception ever requested for *failure_id*."""
        stmt = self._base_select().where(ValidationException.failure_id == failure_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_for_org(self, organization_id: UUID) -> list[ValidationException]:
        """Every exception request for *organization_id* still awaiting a decision."""
        stmt = self._base_select().where(
            ValidationException.organization_id == organization_id,
            ValidationException.status == ValidationExceptionStatus.PENDING,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationExceptionRepository"]
