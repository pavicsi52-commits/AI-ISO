"""Tests for :class:`app.services.ingestion.AlertIngestionService` --
the central pipeline (fingerprint -> deduplicate -> suppress -> raise
-> correlate), end to end against real Postgres with no mocking of the
orchestrator itself.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from shared_core.enums.severity import Severity
from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AlertSource, AlertStatus, SuppressionType
from app.repositories.alert_correlation import AlertCorrelationRepository
from app.repositories.alert_deduplication import AlertDeduplicationRepository
from app.repositories.alert_history import AlertHistoryRepository
from app.repositories.alert_instance import AlertInstanceRepository
from app.repositories.alert_maintenance_window import AlertMaintenanceWindowRepository
from app.repositories.alert_suppression import AlertSuppressionRepository
from app.services.alert import AlertService
from app.services.correlation import AlertCorrelationService
from app.services.deduplication import AlertDeduplicationService
from app.services.ingestion import AlertIngestionService, IngestionOutcome
from app.services.suppression import AlertSuppressionService
from tests.conftest import make_maintenance_window, make_suppression


class _EventRecorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)

    def names(self) -> list[str]:
        return [type(event).__name__ for event in self.events]


def _service(
    db_session: AsyncSession,
    recorder: _EventRecorder,
    *,
    deduplication_window_seconds: float = 300.0,
    correlation_window_seconds: float = 300.0,
) -> AlertIngestionService:
    return AlertIngestionService(
        AlertService(AlertInstanceRepository(db_session), AlertHistoryRepository(db_session)),
        AlertInstanceRepository(db_session),
        AlertDeduplicationService(AlertDeduplicationRepository(db_session)),
        AlertSuppressionService(
            AlertSuppressionRepository(db_session),
            AlertMaintenanceWindowRepository(db_session),
        ),
        AlertCorrelationService(
            AlertCorrelationRepository(db_session), AlertInstanceRepository(db_session)
        ),
        publish_event=recorder,
        deduplication_window_seconds=deduplication_window_seconds,
        correlation_window_seconds=correlation_window_seconds,
    )


async def _ingest(
    service: AlertIngestionService,
    organization_id: uuid.UUID,
    *,
    reference: dict[str, str] | None = None,
    severity: Severity = Severity.HIGH,
    moment: datetime | None = None,
    title: str = "Disk full",
):
    return await service.ingest(
        organization_id=organization_id,
        source=AlertSource.MONITORING,
        severity=severity,
        title=title,
        message="details",
        source_reference=reference if reference is not None else {"target_id": "db-1"},
        moment=moment,
    )


class TestIngestionHappyPath:
    async def test_first_event_creates_an_open_alert(self, db_session: AsyncSession) -> None:
        recorder = _EventRecorder()
        result = await _ingest(_service(db_session, recorder), uuid.uuid4())

        assert result.outcome is IngestionOutcome.CREATED
        assert result.alert.status == AlertStatus.OPEN
        assert "AlertCreatedEvent" in recorder.names()

    async def test_fingerprint_is_recorded_on_the_alert(self, db_session: AsyncSession) -> None:
        result = await _ingest(_service(db_session, _EventRecorder()), uuid.uuid4())
        assert result.alert.fingerprint


class TestDeduplication:
    async def test_repeat_of_same_condition_consolidates(self, db_session: AsyncSession) -> None:
        recorder = _EventRecorder()
        service = _service(db_session, recorder)
        org = uuid.uuid4()

        first = await _ingest(service, org)
        second = await _ingest(service, org)

        assert second.outcome is IngestionOutcome.DEDUPLICATED
        assert second.alert.id == first.alert.id
        # Exactly one alert was ever created.
        assert recorder.names().count("AlertCreatedEvent") == 1

    async def test_occurrence_count_increments(self, db_session: AsyncSession) -> None:
        service = _service(db_session, _EventRecorder())
        org = uuid.uuid4()
        await _ingest(service, org)
        await _ingest(service, org)
        await _ingest(service, org)

        entries = AlertDeduplicationRepository(db_session)
        alerts = await AlertInstanceRepository(db_session).list_for_org(org)
        entry = await entries.get_by_fingerprint(alerts[0].fingerprint)
        assert entry is not None
        assert entry.occurrence_count == 3

    async def test_different_target_is_not_a_duplicate(self, db_session: AsyncSession) -> None:
        service = _service(db_session, _EventRecorder())
        org = uuid.uuid4()
        first = await _ingest(service, org, reference={"target_id": "db-1"})
        second = await _ingest(service, org, reference={"target_id": "db-2"})
        assert second.outcome is IngestionOutcome.CREATED
        assert second.alert.id != first.alert.id

    async def test_recurrence_outside_window_creates_a_new_alert(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session, _EventRecorder(), deduplication_window_seconds=60)
        org = uuid.uuid4()
        start = datetime.now(UTC) - timedelta(hours=1)
        first = await _ingest(service, org, moment=start)
        second = await _ingest(service, org, moment=datetime.now(UTC))
        assert second.outcome is IngestionOutcome.CREATED
        assert second.alert.id != first.alert.id

    async def test_resolved_alert_does_not_absorb_a_recurrence(
        self, db_session: AsyncSession
    ) -> None:
        """A condition recurring after resolution is genuinely new."""
        service = _service(db_session, _EventRecorder())
        alerts = AlertService(
            AlertInstanceRepository(db_session), AlertHistoryRepository(db_session)
        )
        org = uuid.uuid4()

        first = await _ingest(service, org)
        await alerts.transition(first.alert.id, AlertStatus.RESOLVED)

        second = await _ingest(service, org)
        assert second.outcome is IngestionOutcome.CREATED
        assert second.alert.id != first.alert.id


class TestSuppression:
    async def test_matching_suppression_records_a_suppressed_alert(
        self, db_session: AsyncSession
    ) -> None:
        recorder = _EventRecorder()
        service = _service(db_session, recorder)
        org = uuid.uuid4()
        await make_suppression(
            db_session,
            organization_id=org,
            suppression_type=SuppressionType.MANUAL,
            scope_reference="db-1",
        )

        result = await _ingest(service, org, reference={"target_id": "db-1"})

        assert result.outcome is IngestionOutcome.SUPPRESSED
        assert result.alert.status == AlertStatus.SUPPRESSED
        assert "AlertSuppressedEvent" in recorder.names()
        assert "AlertCreatedEvent" not in recorder.names()

    async def test_suppressed_alert_is_still_persisted(self, db_session: AsyncSession) -> None:
        """Suppression is not deletion -- noise analytics need the record."""
        service = _service(db_session, _EventRecorder())
        org = uuid.uuid4()
        await make_suppression(db_session, organization_id=org)

        await _ingest(service, org)
        stored = await AlertInstanceRepository(db_session).list_for_org(org)
        assert len(stored) == 1

    async def test_maintenance_window_suppresses(self, db_session: AsyncSession) -> None:
        service = _service(db_session, _EventRecorder())
        org = uuid.uuid4()
        await make_maintenance_window(db_session, organization_id=org)
        result = await _ingest(service, org)
        assert result.outcome is IngestionOutcome.SUPPRESSED

    async def test_non_matching_suppression_does_not_suppress(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session, _EventRecorder())
        org = uuid.uuid4()
        await make_suppression(db_session, organization_id=org, scope_reference="other-target")
        result = await _ingest(service, org, reference={"target_id": "db-1"})
        assert result.outcome is IngestionOutcome.CREATED

    async def test_another_organizations_suppression_does_not_apply(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session, _EventRecorder())
        mine = uuid.uuid4()
        await make_suppression(db_session, organization_id=uuid.uuid4())
        result = await _ingest(service, mine)
        assert result.outcome is IngestionOutcome.CREATED


class TestCorrelation:
    async def test_related_alert_is_correlated_to_the_earlier_one(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session, _EventRecorder())
        org = uuid.uuid4()
        now = datetime.now(UTC)

        first = await _ingest(
            service,
            org,
            reference={"target_id": "db-1"},
            severity=Severity.CRITICAL,
            moment=now - timedelta(seconds=60),
        )
        second = await _ingest(
            service,
            org,
            reference={"target_id": "db-1", "metric_id": "cpu"},
            moment=now,
        )

        assert second.outcome is IngestionOutcome.CREATED
        assert second.correlated_to == first.alert.id

    async def test_unrelated_first_alert_has_no_correlation(self, db_session: AsyncSession) -> None:
        service = _service(db_session, _EventRecorder())
        result = await _ingest(service, uuid.uuid4())
        assert result.correlated_to is None

    async def test_correlation_edge_is_persisted(self, db_session: AsyncSession) -> None:
        service = _service(db_session, _EventRecorder())
        org = uuid.uuid4()
        now = datetime.now(UTC)
        first = await _ingest(
            service, org, reference={"target_id": "db-1"}, moment=now - timedelta(seconds=30)
        )
        second = await _ingest(
            service, org, reference={"target_id": "db-1", "metric_id": "m"}, moment=now
        )

        edges = await AlertCorrelationRepository(db_session).list_children(first.alert.id)
        assert [edge.child_alert_id for edge in edges] == [second.alert.id]
