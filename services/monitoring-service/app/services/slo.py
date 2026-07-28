"""Service Level Objective tracking ("SLA / SLO" "Track": Latency SLO,
Error Budget, Objective Violations).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.models.enums import ComplianceStatus, SLOType
from app.models.monitoring_slo import MonitoringSLO
from app.repositories.monitoring_slo import MonitoringSLORepository

_AT_RISK_ERROR_BUDGET_PERCENTAGE = 20.0


class MonitoringSLOService:
    """Creates, updates, and reads Service Level Objective targets."""

    def __init__(self, slos: MonitoringSLORepository) -> None:
        self._slos = slos

    async def get_by_id(self, slo_id: UUID) -> MonitoringSLO:
        """Return the SLO identified by *slo_id*.

        Raises:
            NotFoundError: If no such SLO exists.
        """
        return await self._slos.require_by_id(slo_id)

    async def list_for_target(self, target_id: UUID) -> list[MonitoringSLO]:
        """Every SLO tracked for *target_id*."""
        return await self._slos.list_for_target(target_id)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringSLO]:
        """Every SLO belonging to *organization_id*."""
        return await self._slos.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        target_id: UUID,
        slo_type: SLOType,
        objective_value: float,
        period_start: datetime,
        period_end: datetime,
    ) -> MonitoringSLO:
        """Register a new SLO target."""
        return await self._slos.create(
            MonitoringSLO(
                organization_id=organization_id,
                target_id=target_id,
                slo_type=slo_type,
                objective_value=objective_value,
                actual_value=None,
                error_budget_remaining_percentage=100.0,
                status=ComplianceStatus.COMPLIANT,
                period_start=period_start,
                period_end=period_end,
            )
        )

    async def update_actual(
        self, slo_id: UUID, *, actual_value: float, error_budget_remaining_percentage: float
    ) -> MonitoringSLO:
        """Record a period's own actual value and error budget, and
        recompute compliance status ("Error Budget", "Objective Violations").

        Raises:
            NotFoundError: If no such SLO exists.
        """
        slo = await self._slos.require_by_id(slo_id)
        slo.actual_value = actual_value
        slo.error_budget_remaining_percentage = error_budget_remaining_percentage
        if error_budget_remaining_percentage <= 0:
            slo.status = ComplianceStatus.VIOLATED
        elif error_budget_remaining_percentage <= _AT_RISK_ERROR_BUDGET_PERCENTAGE:
            slo.status = ComplianceStatus.AT_RISK
        else:
            slo.status = ComplianceStatus.COMPLIANT
        return await self._slos.update(slo)


__all__ = ["MonitoringSLOService"]
