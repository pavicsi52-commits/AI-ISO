"""Repository for :class:`app.models.secret_category.SecretCategory`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.secret_category import SecretCategory


class SecretCategoryRepository(BaseRepository[SecretCategory]):
    """CRUD plus lookup for :class:`SecretCategory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SecretCategory, tenant_scope=tenant_scope)

    async def get_by_name(self, organization_id: UUID, name: str) -> SecretCategory | None:
        """Return the category identified by *name* within *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            SecretCategory.organization_id == organization_id, SecretCategory.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[SecretCategory]:
        """Every category defined for *organization_id*."""
        stmt = self._base_select().where(SecretCategory.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["SecretCategoryRepository"]
