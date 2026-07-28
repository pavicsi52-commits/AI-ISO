"""Service Level Agreement tracking ("SLA / SLO" "Track": Availability
SLA, Performance SLA, Compliance Percentage, Reporting).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.models.enums import ComplianceStatus, SLAType
from app.models.monitoring_sla import MonitoringSLA
from app.repositories.monitoring_sla import MonitoringSLARepository

_AT_RISK_THRESHOLD_PERCENTAGE = 1.0


class MonitoringSLAService:
    """Creates, updates, and reads Service Level Agreement objectives."""

    def __init__(self, slas: MonitoringSLARepository) -> None:
        self._slas = slas

    async def get_by_id(self, sla_id: UUID) -> MonitoringSLA:
        """Return the SLA identified by *sla_id*.

        Raises:
            NotFoundError: If no such SLA exists.
        """
        return await self._slas.require_by_id(sla_id)

    async def list_for_target(self, target_id: UUID) -> list[MonitoringSLA]:
        """Every SLA tracked for *target_id*."""
        return await self._slas.list_for_target(target_id)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringSLA]:
        """Every SLA belonging to *organization_id*."""
        return await self._slas.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        target_id: UUID,
        sla_type: SLAType,
        objective_percentage: float,
        period_start: datetime,
        period_end: datetime,
    ) -> MonitoringSLA:
        """Register a new SLA objective."""
        return await self._slas.create(
            MonitoringSLA(
                organization_id=organization_id,
                target_id=target_id,
                sla_type=sla_type,
                objective_percentage=objective_percentage,
                actual_percentage=None,
                status=ComplianceStatus.COMPLIANT,
                period_start=period_start,
                period_end=period_end,
            )
        )

    async def update_actual(self, sla_id: UUID, *, actual_percentage: float) -> MonitoringSLA:
        """Record a period's own actual percentage and recompute compliance
        status ("Compliance Percentage").

        Raises:
            NotFoundError: If no such SLA exists.
        """
        sla = await self._slas.require_by_id(sla_id)
        sla.actual_percentage = actual_percentage
        if actual_percentage >= sla.objective_percentage:
            sla.status = ComplianceStatus.COMPLIANT
        elif actual_percentage >= sla.objective_percentage - _AT_RISK_THRESHOLD_PERCENTAGE:
            sla.status = ComplianceStatus.AT_RISK
        else:
            sla.status = ComplianceStatus.VIOLATED
        return await self._slas.update(sla)


__all__ = ["MonitoringSLAService"]
