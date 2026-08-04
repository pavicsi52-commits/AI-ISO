"""Repositories for impact assessments and the services/assets they name."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.impact import IncidentAssetImpact, IncidentImpact, IncidentServiceImpact


class ImpactRepository(BaseRepository[IncidentImpact]):
    """The assessed severity of an incident, over time."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentImpact, tenant_scope=tenant_scope)

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID, *, limit: int = 100
    ) -> list[IncidentImpact]:
        """Every assessment for one incident, newest first."""
        stmt = (
            self._base_select()
            .where(IncidentImpact.organization_id == organization_id)
            .where(IncidentImpact.incident_id == incident_id)
            .order_by(IncidentImpact.assessed_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest(self, organization_id: UUID, incident_id: UUID) -> IncidentImpact | None:
        """The most recent assessment for one incident."""
        rows = await self.list_for_incident(organization_id, incident_id, limit=1)
        return rows[0] if rows else None


class ServiceImpactRepository(BaseRepository[IncidentServiceImpact]):
    """Individual affected services."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentServiceImpact, tenant_scope=tenant_scope)

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID, *, limit: int = 500
    ) -> list[IncidentServiceImpact]:
        """Every affected service on one incident."""
        stmt = (
            self._base_select()
            .where(IncidentServiceImpact.organization_id == organization_id)
            .where(IncidentServiceImpact.incident_id == incident_id)
            .order_by(IncidentServiceImpact.service_name)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AssetImpactRepository(BaseRepository[IncidentAssetImpact]):
    """Individual affected assets."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentAssetImpact, tenant_scope=tenant_scope)

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID, *, limit: int = 500
    ) -> list[IncidentAssetImpact]:
        """Every affected asset on one incident."""
        stmt = (
            self._base_select()
            .where(IncidentAssetImpact.organization_id == organization_id)
            .where(IncidentAssetImpact.incident_id == incident_id)
            .order_by(IncidentAssetImpact.asset_name)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetImpactRepository", "ImpactRepository", "ServiceImpactRepository"]
