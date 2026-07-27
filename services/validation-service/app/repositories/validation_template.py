"""Repository for :class:`app.models.validation_template.ValidationTemplate`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_template import ValidationTemplate


class ValidationTemplateRepository(BaseRepository[ValidationTemplate]):
    """CRUD plus lookup for :class:`ValidationTemplate`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationTemplate, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ValidationTemplate]:
        """Every validation template belonging to *organization_id*."""
        stmt = self._base_select().where(ValidationTemplate.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationTemplateRepository"]
