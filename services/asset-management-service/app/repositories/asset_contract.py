"""Repository for :class:`app.models.asset_contract.AssetContract`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_contract import AssetContract


class AssetContractRepository(BaseRepository[AssetContract]):
    """CRUD plus lookup for :class:`AssetContract`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetContract, tenant_scope=tenant_scope)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetContract]:
        """Every contract covering *managed_asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetContract.managed_asset_id == managed_asset_id)
            .order_by(desc(AssetContract.end_date))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_expiring_before(self, cutoff: datetime) -> list[AssetContract]:
        """Every contract ending on or before *cutoff*, for expiration alerts."""
        stmt = self._base_select().where(AssetContract.end_date <= cutoff)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetContractRepository"]
