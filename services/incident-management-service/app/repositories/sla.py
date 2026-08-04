"""Repositories for SLA clocks and escalations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EscalationStatus, SlaKind, SlaStatus
from app.models.sla import IncidentEscalation, IncidentSla


class SlaRepository(BaseRepository[IncidentSla]):
    """SLA clocks."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentSla, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, sla_id: UUID) -> IncidentSla:
        """One clock by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(IncidentSla.organization_id == organization_id)
            .where(IncidentSla.id == sla_id)
        )
        result = await self._session.execute(stmt)
        found: IncidentSla | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No SLA clock with id {sla_id} in this organization.")
        return found

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID
    ) -> list[IncidentSla]:
        """Every clock on one incident."""
        stmt = (
            self._base_select()
            .where(IncidentSla.organization_id == organization_id)
            .where(IncidentSla.incident_id == incident_id)
            .order_by(IncidentSla.kind)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_incident(
        self, organization_id: UUID, incident_id: UUID, kind: SlaKind
    ) -> IncidentSla | None:
        """One kind of clock on one incident."""
        stmt = (
            self._base_select()
            .where(IncidentSla.organization_id == organization_id)
            .where(IncidentSla.incident_id == incident_id)
            .where(IncidentSla.kind == str(kind))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_running(self, organization_id: UUID, *, limit: int = 5_000) -> list[IncidentSla]:
        """Every clock currently running, for the escalation sweep."""
        stmt = (
            self._base_select()
            .where(IncidentSla.organization_id == organization_id)
            .where(IncidentSla.status == str(SlaStatus.RUNNING))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_in_window(
        self, organization_id: UUID, *, status: SlaStatus, start: datetime, end: datetime
    ) -> int:
        """How many clocks reached *status* within a window, for statistics."""
        column = IncidentSla.met_at if status is SlaStatus.MET else IncidentSla.breached_at
        stmt = (
            select(func.count())
            .select_from(IncidentSla)
            .where(IncidentSla.organization_id == organization_id)
            .where(column >= start)
            .where(column < end)
            .where(IncidentSla.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())


class EscalationRepository(BaseRepository[IncidentEscalation]):
    """Escalations, fired and pending."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentEscalation, tenant_scope=tenant_scope)

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID
    ) -> list[IncidentEscalation]:
        """Every escalation on one incident, in level order."""
        stmt = (
            self._base_select()
            .where(IncidentEscalation.organization_id == organization_id)
            .where(IncidentEscalation.incident_id == incident_id)
            .order_by(IncidentEscalation.level)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def fired_levels(self, organization_id: UUID, incident_id: UUID) -> frozenset[int]:
        """The levels already escalated to, for ``due_steps`` to exclude.

        Only ``TRIGGERED`` and ``ACKNOWLEDGED`` count as fired --
        ``CANCELLED`` does not, so a mistakenly-fired escalation that was
        cancelled can be re-triggered rather than permanently blocking
        its level.
        """
        stmt = (
            self._base_select()
            .where(IncidentEscalation.organization_id == organization_id)
            .where(IncidentEscalation.incident_id == incident_id)
            .where(
                IncidentEscalation.status.in_(
                    [str(EscalationStatus.TRIGGERED), str(EscalationStatus.ACKNOWLEDGED)]
                )
            )
        )
        result = await self._session.execute(stmt)
        return frozenset(row.level for row in result.scalars().all())

    async def count_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime
    ) -> int:
        """How many escalations fired within a window, for statistics."""
        stmt = (
            select(func.count())
            .select_from(IncidentEscalation)
            .where(IncidentEscalation.organization_id == organization_id)
            .where(IncidentEscalation.triggered_at >= start)
            .where(IncidentEscalation.triggered_at < end)
            .where(IncidentEscalation.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())


__all__ = ["EscalationRepository", "SlaRepository"]
