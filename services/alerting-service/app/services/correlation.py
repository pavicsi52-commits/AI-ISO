"""Correlation edge persistence ("CORRELATION")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.correlation.engine import correlate
from app.models.alert_correlation import AlertCorrelation
from app.models.alert_instance import AlertInstance
from app.models.enums import CorrelationType
from app.repositories.alert_correlation import AlertCorrelationRepository
from app.repositories.alert_instance import AlertInstanceRepository


class AlertCorrelationService:
    """Correlates a new alert against those already open in its own window."""

    def __init__(
        self,
        correlations: AlertCorrelationRepository,
        alerts: AlertInstanceRepository,
    ) -> None:
        self._correlations = correlations
        self._alerts = alerts

    async def list_children(self, parent_alert_id: UUID) -> list[AlertCorrelation]:
        """Every alert correlated to *parent_alert_id* as its own root cause."""
        return await self._correlations.list_children(parent_alert_id)

    async def list_parents(self, child_alert_id: UUID) -> list[AlertCorrelation]:
        """Every alert *child_alert_id* is itself correlated to."""
        return await self._correlations.list_parents(child_alert_id)

    async def correlate_alert(
        self, alert: AlertInstance, *, window_seconds: float
    ) -> AlertCorrelation | None:
        """Correlate *alert* to an earlier one, if any qualifies.

        Idempotent: re-running over the same window never registers the
        same edge twice.
        """
        window = timedelta(seconds=window_seconds)
        candidates = await self._alerts.list_triggered_between(
            alert.organization_id, alert.triggered_at - window, alert.triggered_at
        )
        decision = correlate(alert, candidates, window=window)
        if decision is None:
            return None

        existing = await self._correlations.get_edge(decision.parent.id, alert.id)
        if existing is not None:
            return existing
        return await self.record_edge(
            alert,
            parent_alert_id=decision.parent.id,
            correlation_type=decision.correlation_type,
        )

    async def record_edge(
        self,
        alert: AlertInstance,
        *,
        parent_alert_id: UUID,
        correlation_type: CorrelationType,
        moment: datetime | None = None,
    ) -> AlertCorrelation:
        """Persist one correlation edge."""
        return await self._correlations.create(
            AlertCorrelation(
                organization_id=alert.organization_id,
                project_id=alert.project_id,
                parent_alert_id=parent_alert_id,
                child_alert_id=alert.id,
                correlation_type=correlation_type,
                correlated_at=moment or datetime.now(UTC),
            )
        )


__all__ = ["AlertCorrelationService"]
