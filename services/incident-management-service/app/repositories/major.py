"""Repositories for major incident declarations, war rooms, and their participants."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import exists as sa_exists
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WarRoomStatus
from app.models.major import MajorIncidentEvent, WarRoom, WarRoomParticipant
from app.models.timeline import IncidentTimeline


class MajorIncidentRepository(BaseRepository[MajorIncidentEvent]):
    """Major incident declarations."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MajorIncidentEvent, tenant_scope=tenant_scope)

    async def get_for_incident(
        self, organization_id: UUID, incident_id: UUID
    ) -> MajorIncidentEvent | None:
        """The declaration for one incident, if it has been declared major."""
        stmt = (
            self._base_select()
            .where(MajorIncidentEvent.organization_id == organization_id)
            .where(MajorIncidentEvent.incident_id == incident_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_active(
        self, organization_id: UUID, *, limit: int = 200
    ) -> list[MajorIncidentEvent]:
        """Every major incident not yet stood down."""
        stmt = (
            self._base_select()
            .where(MajorIncidentEvent.organization_id == organization_id)
            .where(MajorIncidentEvent.stood_down_at.is_(None))
            .order_by(MajorIncidentEvent.declared_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime
    ) -> int:
        """How many major incidents were declared within a window."""
        stmt = (
            select(func.count())
            .select_from(MajorIncidentEvent)
            .where(MajorIncidentEvent.organization_id == organization_id)
            .where(MajorIncidentEvent.declared_at >= start)
            .where(MajorIncidentEvent.declared_at < end)
            .where(MajorIncidentEvent.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())


class WarRoomRepository(BaseRepository[WarRoom]):
    """War rooms."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WarRoom, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, war_room_id: UUID) -> WarRoom:
        """One war room by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WarRoom.organization_id == organization_id)
            .where(WarRoom.id == war_room_id)
        )
        result = await self._session.execute(stmt)
        found: WarRoom | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No war room with id {war_room_id} in this organization.")
        return found

    async def get_open_for_incident(
        self, organization_id: UUID, incident_id: UUID
    ) -> WarRoom | None:
        """The open (not closed) war room for one incident, if any.

        At most one war room is ever open per incident -- reopening
        coordination for an incident that already has one open should
        rejoin that room, not spawn a second one nobody is watching.
        """
        stmt = (
            self._base_select()
            .where(WarRoom.organization_id == organization_id)
            .where(WarRoom.incident_id == incident_id)
            .where(WarRoom.status != str(WarRoomStatus.CLOSED))
            .order_by(WarRoom.opened_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_stale(
        self, organization_id: UUID, *, idle_since: datetime, limit: int = 200
    ) -> list[WarRoom]:
        """Active war rooms with no timeline activity since *idle_since*.

        What the maintenance sweep uses to flag a forgotten room for
        stand-down -- see ``app/config/settings.py``'s
        ``war_room_idle_close_minutes``.
        """
        recent_activity = sa_exists().where(
            IncidentTimeline.incident_id == WarRoom.incident_id,
            IncidentTimeline.organization_id == WarRoom.organization_id,
            IncidentTimeline.occurred_at >= idle_since,
        )
        stmt = (
            self._base_select()
            .where(WarRoom.organization_id == organization_id)
            .where(WarRoom.status == str(WarRoomStatus.ACTIVE))
            .where(~recent_activity)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class WarRoomParticipantRepository(BaseRepository[WarRoomParticipant]):
    """War room participants."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WarRoomParticipant, tenant_scope=tenant_scope)

    async def list_current(
        self, organization_id: UUID, war_room_id: UUID
    ) -> list[WarRoomParticipant]:
        """Everyone still in the room -- has not left yet."""
        stmt = (
            self._base_select()
            .where(WarRoomParticipant.organization_id == organization_id)
            .where(WarRoomParticipant.war_room_id == war_room_id)
            .where(WarRoomParticipant.left_at.is_(None))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self, organization_id: UUID, war_room_id: UUID) -> list[WarRoomParticipant]:
        """Everyone who was ever in the room, including those who left."""
        stmt = (
            self._base_select()
            .where(WarRoomParticipant.organization_id == organization_id)
            .where(WarRoomParticipant.war_room_id == war_room_id)
            .order_by(WarRoomParticipant.joined_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def holder_of(
        self, organization_id: UUID, war_room_id: UUID, role: str
    ) -> WarRoomParticipant | None:
        """Whoever currently holds a singleton role, if anyone."""
        stmt = (
            self._base_select()
            .where(WarRoomParticipant.organization_id == organization_id)
            .where(WarRoomParticipant.war_room_id == war_room_id)
            .where(WarRoomParticipant.role == role)
            .where(WarRoomParticipant.left_at.is_(None))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["MajorIncidentRepository", "WarRoomParticipantRepository", "WarRoomRepository"]
