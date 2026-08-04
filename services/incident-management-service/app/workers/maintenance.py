"""The maintenance sweep worker.

Three checks whose absence is silent, which is why they are swept
rather than left to be noticed:

1. **Idle war rooms.** A room nobody has touched in a while is a
   coordination space that still reads as staffed and is not -- worse
   for the next incident than one that was properly closed. Stood down
   automatically, since standing a war room down is independent of
   closing out its major-incident declaration (see
   :meth:`~app.services.major_incident.MajorIncidentService.stand_down`).
2. **Overdue stakeholder updates.** Each major incident carries its own
   ``status_update_interval_minutes``; a commander who has gone quiet
   past it is reminded rather than the platform silently accepting that
   stakeholders are owed nothing.
3. **Missing postmortems.** A major incident resolved days ago with no
   postmortem started is the single most common way a "blameless
   learning culture" quietly stops producing any learning.

**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`. **One session per organization**, so a
failure on one tenant does not poison the transaction the next one
needs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.notifications.factory import create_notification_framework
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import WarRoomStatus
from app.models.incident import Incident
from app.notifications.incident_notifications import IncidentNotificationService
from app.repositories.incident import IncidentRepository
from app.repositories.major import MajorIncidentRepository, WarRoomRepository
from app.repositories.postmortem import PostmortemRepository

logger = get_logger("app.workers.maintenance")


class MaintenanceWorker:
    """Stands down idle war rooms and reminds commanders of what is owed."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 200,
        war_room_idle_minutes: int = 1_440,
        postmortem_due_days: int = 5,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick
        self._war_room_idle_minutes = war_room_idle_minutes
        self._postmortem_due_days = postmortem_due_days

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> dict[str, int]:
        """Sweep every organization; returns what was cleaned up and reminded."""
        organizations = await self._organizations()
        stood_down = update_reminders = postmortem_reminders = 0
        for organization_id in organizations:
            counts = await self._sweep(organization_id)
            stood_down += counts["stood_down"]
            update_reminders += counts["update_reminders"]
            postmortem_reminders += counts["postmortem_reminders"]
        logger.info(
            "Incident maintenance sweep complete.",
            extra={
                "extra_fields": {
                    "organizations": len(organizations),
                    "war_rooms_stood_down": stood_down,
                    "status_update_reminders": update_reminders,
                    "postmortem_reminders": postmortem_reminders,
                }
            },
        )
        return {
            "organizations": len(organizations),
            "stood_down": stood_down,
            "update_reminders": update_reminders,
            "postmortem_reminders": postmortem_reminders,
        }

    async def _organizations(self) -> list[UUID]:
        """Every organization with at least one incident."""
        async with self._session_factory() as session:
            statement = select(distinct(Incident.organization_id)).limit(self._max_per_tick)
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> dict[str, int]:
        """Sweep one organization under its own session."""
        try:
            async with self._session_factory() as session:
                notifications = IncidentNotificationService(create_notification_framework())
                now = datetime.now(UTC)
                stood_down = await self._stand_down_idle_war_rooms(
                    session, organization_id, now=now
                )
                update_reminders = await self._remind_overdue_status_updates(
                    session, organization_id, notifications=notifications, now=now
                )
                postmortem_reminders = await self._remind_missing_postmortems(
                    session, organization_id, notifications=notifications, now=now
                )
                await session.commit()
            return {
                "stood_down": stood_down,
                "update_reminders": update_reminders,
                "postmortem_reminders": postmortem_reminders,
            }
        except Exception as exc:
            logger.warning(
                "An incident maintenance sweep failed; the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return {"stood_down": 0, "update_reminders": 0, "postmortem_reminders": 0}

    async def _stand_down_idle_war_rooms(
        self, session: AsyncSession, organization_id: UUID, *, now: datetime
    ) -> int:
        war_rooms = WarRoomRepository(session)
        idle_since = now - timedelta(minutes=self._war_room_idle_minutes)
        stale = await war_rooms.list_stale(organization_id, idle_since=idle_since)
        for room in stale:
            room.status = WarRoomStatus.CLOSED
            room.closed_at = now
            await war_rooms.update(room)
        return len(stale)

    async def _remind_overdue_status_updates(
        self,
        session: AsyncSession,
        organization_id: UUID,
        *,
        notifications: IncidentNotificationService,
        now: datetime,
    ) -> int:
        major_incidents = MajorIncidentRepository(session)
        incidents = IncidentRepository(session)
        reminded = 0
        for declaration in await major_incidents.list_active(organization_id):
            if not declaration.incident_commander_id:
                continue
            anchor = declaration.last_status_update_at or declaration.declared_at
            elapsed_minutes = (now - anchor).total_seconds() / 60
            if elapsed_minutes < declaration.status_update_interval_minutes:
                continue
            incident = await incidents.require_in_org(organization_id, declaration.incident_id)
            await notifications.send_status_update_overdue(
                declaration.incident_commander_id,
                reference=incident.reference,
                title=incident.title,
                minutes_since_last_update=int(elapsed_minutes),
            )
            reminded += 1
        return reminded

    async def _remind_missing_postmortems(
        self,
        session: AsyncSession,
        organization_id: UUID,
        *,
        notifications: IncidentNotificationService,
        now: datetime,
    ) -> int:
        incidents = IncidentRepository(session)
        major_incidents = MajorIncidentRepository(session)
        postmortems = PostmortemRepository(session)
        reminded = 0
        for incident in await incidents.list_filtered(organization_id, is_major=True, limit=1_000):
            if incident.resolved_at is None:
                continue
            resolved_days_ago = (now - incident.resolved_at).days
            if resolved_days_ago < self._postmortem_due_days:
                continue
            if await postmortems.get_for_incident(organization_id, incident.id) is not None:
                continue
            declaration = await major_incidents.get_for_incident(organization_id, incident.id)
            if declaration is None or not declaration.incident_commander_id:
                continue
            await notifications.send_postmortem_due(
                declaration.incident_commander_id,
                reference=incident.reference,
                title=incident.title,
                resolved_days_ago=resolved_days_ago,
            )
            reminded += 1
        return reminded


__all__ = ["MaintenanceWorker"]
