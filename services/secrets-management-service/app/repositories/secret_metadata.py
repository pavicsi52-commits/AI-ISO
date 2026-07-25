"""Repository for :class:`app.models.secret_metadata.SecretMetadataEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.secret_metadata import SecretMetadataEntry


class SecretMetadataRepository(BaseRepository[SecretMetadataEntry]):
    """CRUD plus lookup for :class:`SecretMetadataEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SecretMetadataEntry, tenant_scope=tenant_scope)

    async def get_by_key(self, secret_id: UUID, key: str) -> SecretMetadataEntry | None:
        """Return the metadata entry identified by *key* on *secret_id*, or ``None``."""
        stmt = self._base_select().where(
            SecretMetadataEntry.secret_id == secret_id, SecretMetadataEntry.key == key
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_secret(self, secret_id: UUID) -> list[SecretMetadataEntry]:
        """Every metadata entry for *secret_id*."""
        stmt = self._base_select().where(SecretMetadataEntry.secret_id == secret_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["SecretMetadataRepository"]
