"""Repositories for the organization-configurable lookup tables.

Categories, priorities, and statuses -- the display and SLA-override
layer that sits beside the platform's built-in enum vocabulary. See
``app/models/incident.py`` for why these exist as tables at all.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import IncidentPriority, IncidentStatus
from app.models.incident import IncidentCategoryRecord, IncidentPriorityRecord, IncidentStatusRecord


class IncidentCategoryRepository(BaseRepository[IncidentCategoryRecord]):
    """Organization-defined category labels."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentCategoryRecord, tenant_scope=tenant_scope)

    async def get_by_slug(self, organization_id: UUID, slug: str) -> IncidentCategoryRecord | None:
        """One category by its slug within an organization."""
        stmt = (
            self._base_select()
            .where(IncidentCategoryRecord.organization_id == organization_id)
            .where(IncidentCategoryRecord.slug == slug)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200
    ) -> list[IncidentCategoryRecord]:
        """Every category, in display order."""
        stmt = (
            self._base_select()
            .where(IncidentCategoryRecord.organization_id == organization_id)
            .order_by(IncidentCategoryRecord.display_order, IncidentCategoryRecord.name)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class IncidentPriorityRepository(BaseRepository[IncidentPriorityRecord]):
    """An organization's own SLA-window overrides, per priority."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentPriorityRecord, tenant_scope=tenant_scope)

    async def get_for_priority(
        self, organization_id: UUID, priority: IncidentPriority
    ) -> IncidentPriorityRecord | None:
        """This organization's override for one priority level, if any."""
        stmt = (
            self._base_select()
            .where(IncidentPriorityRecord.organization_id == organization_id)
            .where(IncidentPriorityRecord.priority == str(priority))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 50
    ) -> list[IncidentPriorityRecord]:
        """Every priority override this organization has configured."""
        stmt = (
            self._base_select()
            .where(IncidentPriorityRecord.organization_id == organization_id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class IncidentStatusRepository(BaseRepository[IncidentStatusRecord]):
    """Display metadata for lifecycle statuses."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentStatusRecord, tenant_scope=tenant_scope)

    async def get_for_status(
        self, organization_id: UUID, status: IncidentStatus
    ) -> IncidentStatusRecord | None:
        """This organization's display record for one status, if any."""
        stmt = (
            self._base_select()
            .where(IncidentStatusRecord.organization_id == organization_id)
            .where(IncidentStatusRecord.status == str(status))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 50
    ) -> list[IncidentStatusRecord]:
        """Every status record this organization has configured, in order."""
        stmt = (
            self._base_select()
            .where(IncidentStatusRecord.organization_id == organization_id)
            .order_by(IncidentStatusRecord.display_order)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = [
    "IncidentCategoryRepository",
    "IncidentPriorityRepository",
    "IncidentStatusRepository",
]
