"""Repository for :class:`app.models.validation_audit.ValidationAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_audit import ValidationAuditEntry


class ValidationAuditEntryRepository(BaseRepository[ValidationAuditEntry]):
    """CRUD plus lookup for :class:`ValidationAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationAuditEntry, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ValidationAuditEntry]:
        """Every audit entry recorded for *organization_id*."""
        stmt = self._base_select().where(ValidationAuditEntry.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationAuditEntryRepository"]
