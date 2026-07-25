"""Repository for :class:`app.models.asset_compliance.AssetCompliance`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_compliance import AssetCompliance
from app.models.enums import ComplianceType


class AssetComplianceRepository(BaseRepository[AssetCompliance]):
    """CRUD plus lookup for :class:`AssetCompliance`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetCompliance, tenant_scope=tenant_scope)

    async def list_for_managed_asset(
        self, managed_asset_id: UUID, *, compliance_type: ComplianceType | None = None
    ) -> list[AssetCompliance]:
        """Every compliance evaluation for *managed_asset_id*, newest first,
        optionally narrowed to a single *compliance_type*.
        """
        stmt = self._base_select().where(AssetCompliance.managed_asset_id == managed_asset_id)
        if compliance_type is not None:
            stmt = stmt.where(AssetCompliance.compliance_type == compliance_type)
        stmt = stmt.order_by(desc(AssetCompliance.checked_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetComplianceRepository"]
