"""Repositories for the organization-configurable lookup tables.

Categories, types, priorities, and statuses -- the display and policy
override layer that sits beside the platform's built-in enum vocabulary.
See ``app/models/catalogue.py`` for why these exist as tables at all.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalogue import (
    ChangeCategoryRecord,
    ChangePriorityRecord,
    ChangeStatusRecord,
    ChangeTypeRecord,
)
from app.models.enums import ChangePriority, ChangeStatus, ChangeType


class ChangeCategoryRepository(BaseRepository[ChangeCategoryRecord]):
    """Organization-defined category labels."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeCategoryRecord, tenant_scope=tenant_scope)

    async def get_by_slug(self, organization_id: UUID, slug: str) -> ChangeCategoryRecord | None:
        """One category by its slug within an organization."""
        stmt = (
            self._base_select()
            .where(ChangeCategoryRecord.organization_id == organization_id)
            .where(ChangeCategoryRecord.slug == slug)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200
    ) -> list[ChangeCategoryRecord]:
        """Every category, in display order."""
        stmt = (
            self._base_select()
            .where(ChangeCategoryRecord.organization_id == organization_id)
            .order_by(ChangeCategoryRecord.display_order, ChangeCategoryRecord.name)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ChangeTypeRepository(BaseRepository[ChangeTypeRecord]):
    """An organization's own policy overrides, per process type."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeTypeRecord, tenant_scope=tenant_scope)

    async def get_for_type(
        self, organization_id: UUID, change_type: ChangeType
    ) -> ChangeTypeRecord | None:
        """This organization's override for one process type, if any."""
        stmt = (
            self._base_select()
            .where(ChangeTypeRecord.organization_id == organization_id)
            .where(ChangeTypeRecord.change_type == str(change_type))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 50
    ) -> list[ChangeTypeRecord]:
        """Every process-type override this organization has configured."""
        stmt = (
            self._base_select()
            .where(ChangeTypeRecord.organization_id == organization_id)
            .order_by(ChangeTypeRecord.display_order)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ChangePriorityRepository(BaseRepository[ChangePriorityRecord]):
    """An organization's own approval-window overrides, per priority."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangePriorityRecord, tenant_scope=tenant_scope)

    async def get_for_priority(
        self, organization_id: UUID, priority: ChangePriority
    ) -> ChangePriorityRecord | None:
        """This organization's override for one priority level, if any."""
        stmt = (
            self._base_select()
            .where(ChangePriorityRecord.organization_id == organization_id)
            .where(ChangePriorityRecord.priority == str(priority))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 50
    ) -> list[ChangePriorityRecord]:
        """Every priority override this organization has configured."""
        stmt = (
            self._base_select()
            .where(ChangePriorityRecord.organization_id == organization_id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ChangeStatusRepository(BaseRepository[ChangeStatusRecord]):
    """Display metadata for lifecycle statuses."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeStatusRecord, tenant_scope=tenant_scope)

    async def get_for_status(
        self, organization_id: UUID, status: ChangeStatus
    ) -> ChangeStatusRecord | None:
        """This organization's display record for one status, if any."""
        stmt = (
            self._base_select()
            .where(ChangeStatusRecord.organization_id == organization_id)
            .where(ChangeStatusRecord.status == str(status))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 50
    ) -> list[ChangeStatusRecord]:
        """Every status record this organization has configured, in order."""
        stmt = (
            self._base_select()
            .where(ChangeStatusRecord.organization_id == organization_id)
            .order_by(ChangeStatusRecord.display_order)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = [
    "ChangeCategoryRepository",
    "ChangePriorityRepository",
    "ChangeStatusRepository",
    "ChangeTypeRepository",
]
