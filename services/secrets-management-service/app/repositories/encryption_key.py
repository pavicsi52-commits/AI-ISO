"""Repository for :class:`app.models.encryption_key.EncryptionKey`.

Data Encryption Keys are minted **per organization** -- not one shared
key for the whole service -- since ``organization_id`` is a mandatory,
non-nullable column on every AI-IOS entity table (docs/018 "BASE
MODEL": "No future entity may redefine these fields") and docs/035's
own "SECURITY" section explicitly requires "Tenant isolation": a
compromised DEK for one organization must never expose another
organization's secrets.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.encryption_key import EncryptionKey
from app.models.enums import EncryptionKeyStatus


class EncryptionKeyRepository(BaseRepository[EncryptionKey]):
    """CRUD plus lookup for :class:`EncryptionKey`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, EncryptionKey, tenant_scope=tenant_scope)

    async def get_active(self, organization_id: UUID) -> EncryptionKey | None:
        """Return *organization_id*'s current active Data Encryption Key, if one exists."""
        stmt = (
            self._base_select()
            .where(
                EncryptionKey.organization_id == organization_id,
                EncryptionKey.status == EncryptionKeyStatus.ACTIVE,
            )
            .order_by(desc(EncryptionKey.version))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[EncryptionKey]:
        """Every Data Encryption Key ever minted for *organization_id*, newest first."""
        stmt = (
            self._base_select()
            .where(EncryptionKey.organization_id == organization_id)
            .order_by(desc(EncryptionKey.version))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["EncryptionKeyRepository"]
