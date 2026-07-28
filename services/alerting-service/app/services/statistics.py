"""Alerting analytics computation. Per docs/045 "ANALYTICS" "Collect":
Alert Volume, Alert Frequency, Top Alert Sources, Top Rules, Noise
Ratio, Suppression Rate, Resolution Time, MTTA, MTTR, Escalation
Statistics. Computed on demand and cached, the same "cached, not live"
shape ``services/monitoring-service``'s own statistics service
established.

**MTTA vs MTTR**, since the two are routinely conflated: MTTA is
trigger -> *first* acknowledgement (how fast a human responded); MTTR
is trigger -> resolution (how fast it was actually fixed). Both are
computed only over alerts that genuinely reached that state -- an
unacknowledged alert contributes to neither, rather than being
silently counted as zero and flattering the average.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.models.alert_statistics import AlertStatistics
from app.models.enums import AlertStatus
from app.repositories.alert_acknowledgement import AlertAcknowledgementRepository
from app.repositories.alert_history import AlertHistoryRepository
from app.repositories.alert_instance import OPEN_STATUSES, AlertInstanceRepository
from app.repositories.alert_statistics import AlertStatisticsRepository

_NOISE_STATUSES = frozenset({AlertStatus.SUPPRESSED, AlertStatus.EXPIRED})
"""What counts as "noise": suppressed or expired without ever being
acted on. An alert someone acknowledged was, by definition, worth
raising.
"""


class AlertStatisticsService:
    """Recomputes and reads an organization's cached alerting analytics."""

    def __init__(
        self,
        statistics: AlertStatisticsRepository,
        alerts: AlertInstanceRepository,
        acknowledgements: AlertAcknowledgementRepository,
        history: AlertHistoryRepository,
    ) -> None:
        self._statistics = statistics
        self._alerts = alerts
        self._acknowledgements = acknowledgements
        self._history = history

    async def get_for_org(self, organization_id: UUID) -> AlertStatistics:
        """Return *organization_id*'s cached snapshot, recomputing if none exists."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> AlertStatistics:
        """Recompute and persist *organization_id*'s statistics snapshot."""
        alerts = await self._alerts.list_for_org(organization_id)
        total = len(alerts)

        open_count = sum(1 for alert in alerts if alert.status in OPEN_STATUSES)
        noise_count = sum(1 for alert in alerts if alert.status in _NOISE_STATUSES)
        suppressed_count = sum(1 for alert in alerts if alert.status == AlertStatus.SUPPRESSED)

        resolution_seconds: list[float] = [
            (alert.resolved_at - alert.triggered_at).total_seconds()
            for alert in alerts
            if alert.resolved_at is not None
        ]

        acknowledgement_seconds: list[float] = []
        for alert in alerts:
            first = await self._acknowledgements.get_first_for_alert(alert.id)
            if first is not None:
                acknowledgement_seconds.append(
                    (first.acknowledged_at - alert.triggered_at).total_seconds()
                )

        escalated = sum(
            1
            for entry in await self._history.list_for_org(organization_id)
            if entry.to_status == AlertStatus.ESCALATED
        )

        trend: Counter[str] = Counter()
        for alert in alerts:
            trend[alert.triggered_at.date().isoformat()] += 1

        snapshot_fields = {
            "total_alerts": total,
            "open_alert_count": open_count,
            "noise_ratio": noise_count / total if total else 0.0,
            "suppression_rate": suppressed_count / total if total else 0.0,
            "average_resolution_seconds": _mean(resolution_seconds),
            "mtta_seconds": _mean(acknowledgement_seconds),
            "mttr_seconds": _mean(resolution_seconds),
            "top_sources": dict(Counter(str(alert.source) for alert in alerts)),
            "top_rules": dict(
                Counter(str(alert.rule_id) for alert in alerts if alert.rule_id is not None)
            ),
            "escalation_statistics": {"escalated_transitions": escalated},
            "trend_data": dict(trend),
            "computed_at": datetime.now(UTC),
        }

        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for field, value in snapshot_fields.items():
                setattr(existing, field, value)
            return await self._statistics.update(existing)
        return await self._statistics.create(
            AlertStatistics(organization_id=organization_id, **snapshot_fields)
        )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


__all__ = ["AlertStatisticsService"]
