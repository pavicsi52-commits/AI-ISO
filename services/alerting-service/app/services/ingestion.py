"""The alert ingestion pipeline -- this service's own central
orchestrator, and the "operational nervous system" behaviour docs/045
describes.

One incoming event flows through, in this order:

1. **Fingerprint** it (:mod:`app.deduplication.fingerprint`).
2. **Deduplicate**: if an equivalent alert is already open inside the
   deduplication window, consolidate into it and stop -- no second
   alert, no second page.
3. **Suppress**: if a maintenance window or suppression rule covers it,
   record it as ``SUPPRESSED`` rather than raising it for attention.
   The alert is still *stored* (suppression is not deletion -- the
   record matters for noise analytics and post-incident review).
4. **Raise** it as a real, open alert.
5. **Correlate** it to an earlier related alert, if one qualifies.

Every step's outcome is reported back in :class:`IngestionResult` so
the caller (and tests) can see exactly which path was taken, rather
than inferring it from the resulting status alone.

Deliberately sequential, never ``asyncio.gather``-ed: every step here
touches the database, and ``AsyncSession`` is not safe for concurrent
use by multiple asyncio tasks even for reads (a flush is not
reentrant) -- the real production bug
``services/validation-service`` hit and fixed, and which
``services/monitoring-service`` then designed around proactively.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from shared_core.enums.severity import Severity

from app.deduplication.fingerprint import compute_fingerprint
from app.events.alert_events import AlertCreatedEvent, AlertSuppressedEvent
from app.models.alert_instance import AlertInstance
from app.models.enums import AlertSource, AlertStatus
from app.repositories.alert_instance import AlertInstanceRepository
from app.services.alert import AlertService
from app.services.correlation import AlertCorrelationService
from app.services.deduplication import AlertDeduplicationService
from app.services.suppression import AlertSuppressionService
from app.types import EventPublisher


class IngestionOutcome(StrEnum):
    """Which path an ingested event took."""

    CREATED = "created"
    DEDUPLICATED = "deduplicated"
    SUPPRESSED = "suppressed"


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """What happened to one ingested event."""

    outcome: IngestionOutcome
    alert: AlertInstance
    correlated_to: UUID | None = None
    reason: str | None = None


class AlertIngestionService:
    """Runs an incoming event through the full alerting pipeline."""

    def __init__(
        self,
        alerts: AlertService,
        alert_repository: AlertInstanceRepository,
        deduplication: AlertDeduplicationService,
        suppression: AlertSuppressionService,
        correlation: AlertCorrelationService,
        *,
        publish_event: EventPublisher,
        deduplication_window_seconds: float,
        correlation_window_seconds: float,
    ) -> None:
        self._alerts = alerts
        self._alert_repository = alert_repository
        self._deduplication = deduplication
        self._suppression = suppression
        self._correlation = correlation
        self._publish_event = publish_event
        self._deduplication_window_seconds = deduplication_window_seconds
        self._correlation_window_seconds = correlation_window_seconds

    async def ingest(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
        rule_id: UUID | None = None,
        source: AlertSource,
        severity: Severity,
        title: str,
        message: str,
        source_reference: dict[str, Any] | None = None,
        moment: datetime | None = None,
    ) -> IngestionResult:
        """Ingest one event and return what happened to it."""
        now = moment or datetime.now(UTC)
        reference = source_reference or {}
        fingerprint = compute_fingerprint(
            organization_id=organization_id,
            source=source,
            rule_id=rule_id,
            source_reference=reference,
        )

        deduplicated = await self._try_deduplicate(organization_id, fingerprint, now)
        if deduplicated is not None:
            return deduplicated

        decision = await self._suppression.decide(organization_id, reference, moment=now)
        status = AlertStatus.SUPPRESSED if decision.suppressed else AlertStatus.OPEN

        alert = await self._alerts.create(
            organization_id=organization_id,
            project_id=project_id,
            rule_id=rule_id,
            source=source,
            severity=severity,
            title=title,
            message=message,
            fingerprint=fingerprint,
            source_reference=reference,
            status=status,
            triggered_at=now,
        )
        await self._deduplication.register_or_reassign(
            organization_id=organization_id,
            project_id=project_id,
            fingerprint=fingerprint,
            primary_alert_id=alert.id,
            moment=now,
        )

        if decision.suppressed:
            await self._publish_event(
                AlertSuppressedEvent(
                    source_service="alerting-service",
                    payload={
                        "alert_id": str(alert.id),
                        "reason": decision.reason,
                        "suppression_type": (
                            str(decision.suppression_type)
                            if decision.suppression_type is not None
                            else None
                        ),
                    },
                )
            )
            return IngestionResult(
                outcome=IngestionOutcome.SUPPRESSED, alert=alert, reason=decision.reason
            )

        await self._publish_event(
            AlertCreatedEvent(
                source_service="alerting-service",
                payload={
                    "alert_id": str(alert.id),
                    "severity": str(severity),
                    "source": str(source),
                },
            )
        )
        edge = await self._correlation.correlate_alert(
            alert, window_seconds=self._correlation_window_seconds
        )
        return IngestionResult(
            outcome=IngestionOutcome.CREATED,
            alert=alert,
            correlated_to=edge.parent_alert_id if edge is not None else None,
        )

    async def _try_deduplicate(
        self, organization_id: UUID, fingerprint: str, now: datetime
    ) -> IngestionResult | None:
        """Consolidate into an already-open equivalent alert, if one exists."""
        entry = await self._deduplication.get_by_fingerprint(fingerprint)
        if entry is None:
            return None
        since = now - timedelta(seconds=self._deduplication_window_seconds)
        existing = await self._alert_repository.get_active_by_fingerprint(
            organization_id, fingerprint, since=since
        )
        if existing is None:
            return None
        await self._deduplication.record_occurrence(entry, moment=now)
        return IngestionResult(
            outcome=IngestionOutcome.DEDUPLICATED,
            alert=existing,
            reason=f"Consolidated into alert {existing.id!s} (occurrence "
            f"{entry.occurrence_count}).",
        )


__all__ = ["AlertIngestionService", "IngestionOutcome", "IngestionResult"]
