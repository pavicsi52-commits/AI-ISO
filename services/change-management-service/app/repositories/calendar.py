"""The change calendar repository -- maintenance windows and blackout periods."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar import ChangeCalendarEntry
from app.models.change import ChangeRequest
from app.models.enums import CalendarEntryKind


class ChangeCalendarRepository(BaseRepository[ChangeCalendarEntry]):
    """Maintenance windows and blackout periods."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeCalendarEntry, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, entry_id: UUID) -> ChangeCalendarEntry:
        """One calendar entry by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ChangeCalendarEntry.organization_id == organization_id)
            .where(ChangeCalendarEntry.id == entry_id)
        )
        result = await self._session.execute(stmt)
        found: ChangeCalendarEntry | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No calendar entry with id {entry_id} in this organization.")
        return found

    async def list_overlapping(
        self,
        organization_id: UUID,
        *,
        start: datetime,
        end: datetime,
        kind: CalendarEntryKind | None = None,
        limit: int = 500,
    ) -> list[ChangeCalendarEntry]:
        """Every entry whose own recurrence base window could touch a range.

        Returns the stored (first-occurrence) window only -- a caller
        working with a recurring entry expands it with
        ``app/calendar/engine.py::expand_occurrences`` afterward. This
        is deliberately generous (it does not itself rule out a
        recurring entry whose *first* occurrence misses the range but a
        *later* one hits it), which is why it filters only by kind, not
        by a tight time comparison, when the entry recurs.
        """
        stmt = (
            self._base_select()
            .where(ChangeCalendarEntry.organization_id == organization_id)
            .where(ChangeCalendarEntry.starts_at < end)
            .where(
                func.coalesce(ChangeCalendarEntry.recurrence_until, ChangeCalendarEntry.ends_at)
                >= start
            )
            .limit(limit)
        )
        if kind is not None:
            stmt = stmt.where(ChangeCalendarEntry.kind == str(kind))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_bookings(
        self,
        organization_id: UUID,
        calendar_entry_id: UUID,
        *,
        exclude_change_id: UUID | None = None,
    ) -> int:
        """How many changes currently reference one calendar entry."""
        stmt = (
            select(func.count())
            .select_from(ChangeRequest)
            .where(ChangeRequest.organization_id == organization_id)
            .where(ChangeRequest.calendar_entry_id == calendar_entry_id)
            .where(ChangeRequest.deleted_at.is_(None))
        )
        if exclude_change_id is not None:
            stmt = stmt.where(ChangeRequest.id != exclude_change_id)
        return int((await self._session.execute(stmt)).scalar_one())


__all__ = ["ChangeCalendarRepository"]
