"""Repository for :class:`app.models.secret_tag.SecretTag`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.secret_tag import SecretTag


class SecretTagRepository(BaseRepository[SecretTag]):
    """CRUD plus lookup for :class:`SecretTag`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SecretTag, tenant_scope=tenant_scope)

    async def get_by_label(self, secret_id: UUID, label: str) -> SecretTag | None:
        """Return the tag identified by *label* on *secret_id*, or ``None``."""
        stmt = self._base_select().where(SecretTag.secret_id == secret_id, SecretTag.label == label)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_secret(self, secret_id: UUID) -> list[SecretTag]:
        """Every tag assigned to *secret_id*."""
        stmt = self._base_select().where(SecretTag.secret_id == secret_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["SecretTagRepository"]
