"""Repository for :class:`app.models.asset_contact.AssetContact`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_contact import AssetContact
from app.models.enums import ContactRole


class AssetContactRepository(BaseRepository[AssetContact]):
    """CRUD plus lookup for :class:`AssetContact`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetContact, tenant_scope=tenant_scope)

    async def get_for_role(self, managed_asset_id: UUID, role: ContactRole) -> AssetContact | None:
        """Return *managed_asset_id*'s contact for *role*, or ``None``."""
        stmt = self._base_select().where(
            AssetContact.managed_asset_id == managed_asset_id, AssetContact.role == role
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetContact]:
        """Every reachable contact for *managed_asset_id*."""
        stmt = self._base_select().where(AssetContact.managed_asset_id == managed_asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetContactRepository"]
