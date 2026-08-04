"""The change request repository, and change-to-change relationships.

Every read is scoped by ``organization_id``, including the lookup by
reference -- ``CHG-0042`` is a human-quotable identifier read aloud in a
CAB meeting, so an unscoped lookup by reference would let one tenant
read another's change by guessing a small, sequential number.
``require_in_org`` is named apart from the base repository's unscoped
``require_by_id`` for the same reason Prompt 050, 051, and 052 each
established it: two same-named methods of different arity on one class
make an unscoped call look correct.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change import ChangeRelationship, ChangeRequest
from app.models.enums import OPEN_CHANGE_STATUSES, ChangeCategory, ChangePriority, ChangeStatus


class ChangeRequestRepository(BaseRepository[ChangeRequest]):
    """The change catalogue."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeRequest, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, change_id: UUID) -> ChangeRequest:
        """One change by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here. Deliberately not a
                permission error -- telling a caller it exists but
                belongs to someone else confirms the id, which is the
                one thing they did not already know.
        """
        stmt = (
            self._base_select()
            .where(ChangeRequest.organization_id == organization_id)
            .where(ChangeRequest.id == change_id)
        )
        result = await self._session.execute(stmt)
        found: ChangeRequest | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No change with id {change_id} in this organization.")
        return found

    async def get_by_reference(self, organization_id: UUID, reference: str) -> ChangeRequest | None:
        """One change by its human-quotable reference."""
        stmt = (
            self._base_select()
            .where(ChangeRequest.organization_id == organization_id)
            .where(ChangeRequest.reference == reference)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def next_reference_sequence(self, organization_id: UUID) -> int:
        """The next number to use in this organization's ``CHG-####`` series.

        Derived from the highest existing reference rather than a row
        count, so a deleted change does not cause the next reference to
        be reused -- a reference already quoted in a CAB meeting must
        stay unique forever.
        """
        stmt = select(ChangeRequest.reference).where(
            ChangeRequest.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        highest = 0
        for (reference,) in result.all():
            _, _, tail = reference.rpartition("-")
            if tail.isdigit():
                highest = max(highest, int(tail))
        return highest + 1

    async def list_filtered(
        self,
        organization_id: UUID,
        *,
        status: ChangeStatus | None = None,
        priority: ChangePriority | None = None,
        category: ChangeCategory | None = None,
        technical_owner_id: str | None = None,
        open_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ChangeRequest]:
        """Changes matching a caller's filters, newest first."""
        stmt = self._base_select().where(ChangeRequest.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ChangeRequest.status == str(status))
        if priority is not None:
            stmt = stmt.where(ChangeRequest.priority == str(priority))
        if category is not None:
            stmt = stmt.where(ChangeRequest.category == str(category))
        if technical_owner_id is not None:
            stmt = stmt.where(ChangeRequest.technical_owner_id == technical_owner_id)
        if open_only:
            stmt = stmt.where(ChangeRequest.status.in_([str(one) for one in OPEN_CHANGE_STATUSES]))
        stmt = stmt.order_by(ChangeRequest.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_open(self, organization_id: UUID, *, limit: int = 500) -> list[ChangeRequest]:
        """Every open change, for conflict detection and dashboards."""
        return await self.list_filtered(organization_id, open_only=True, limit=limit)

    async def list_scheduled_between(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 500
    ) -> list[ChangeRequest]:
        """Changes scheduled to touch a window, for conflict detection and the calendar."""
        stmt = (
            self._base_select()
            .where(ChangeRequest.organization_id == organization_id)
            .where(ChangeRequest.scheduled_start_at.is_not(None))
            .where(ChangeRequest.scheduled_start_at < end)
            .where(ChangeRequest.scheduled_end_at > start)
            .order_by(ChangeRequest.scheduled_start_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, organization_id: UUID) -> dict[str, int]:
        """How many changes sit in each lifecycle status."""
        stmt = (
            select(ChangeRequest.status, func.count())
            .where(ChangeRequest.organization_id == organization_id)
            .where(ChangeRequest.deleted_at.is_(None))
            .group_by(ChangeRequest.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def list_created_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 10_000
    ) -> list[ChangeRequest]:
        """Changes created within a window, for statistics rollups."""
        stmt = (
            self._base_select()
            .where(ChangeRequest.organization_id == organization_id)
            .where(ChangeRequest.created_at >= start)
            .where(ChangeRequest.created_at < end)
            .order_by(ChangeRequest.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ChangeRelationshipRepository(BaseRepository[ChangeRelationship]):
    """How changes relate to each other."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeRelationship, tenant_scope=tenant_scope)

    async def list_for_change(
        self, organization_id: UUID, change_id: UUID
    ) -> list[ChangeRelationship]:
        """Every relationship this change is the *source* side of."""
        stmt = (
            self._base_select()
            .where(ChangeRelationship.organization_id == organization_id)
            .where(ChangeRelationship.change_id == change_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_referencing(
        self, organization_id: UUID, related_change_id: UUID
    ) -> list[ChangeRelationship]:
        """Every relationship naming this change as the *related* side."""
        stmt = (
            self._base_select()
            .where(ChangeRelationship.organization_id == organization_id)
            .where(ChangeRelationship.related_change_id == related_change_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ChangeRelationshipRepository", "ChangeRequestRepository"]
