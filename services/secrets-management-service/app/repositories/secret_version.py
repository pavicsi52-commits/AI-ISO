"""Repository for :class:`app.models.secret_version.SecretVersion`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.secret_version import SecretVersion


class SecretVersionRepository(BaseRepository[SecretVersion]):
    """CRUD plus lookup for :class:`SecretVersion`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, SecretVersion, tenant_scope=tenant_scope)

    async def get_current(self, secret_id: UUID) -> SecretVersion | None:
        """Return *secret_id*'s current version row, or ``None``."""
        stmt = self._base_select().where(
            SecretVersion.secret_id == secret_id, SecretVersion.is_current.is_(True)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_number(self, secret_id: UUID, version_number: int) -> SecretVersion | None:
        """Return *secret_id*'s version identified by *version_number*, or ``None``."""
        stmt = self._base_select().where(
            SecretVersion.secret_id == secret_id, SecretVersion.version_number == version_number
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_secret(self, secret_id: UUID) -> list[SecretVersion]:
        """Every version of *secret_id*, newest first ("Version History")."""
        stmt = (
            self._base_select()
            .where(SecretVersion.secret_id == secret_id)
            .order_by(desc(SecretVersion.version_number))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_encryption_key(self, encryption_key_id: UUID) -> list[SecretVersion]:
        """Every version currently encrypted by *encryption_key_id* ("Key Rotation")."""
        stmt = self._base_select().where(SecretVersion.encryption_key_id == encryption_key_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["SecretVersionRepository"]
