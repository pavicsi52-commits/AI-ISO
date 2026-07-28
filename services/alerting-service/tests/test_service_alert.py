"""Tests for :class:`app.services.alert.AlertService` -- the alert
lifecycle and its own recorded history, against real Postgres.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.enums.severity import Severity
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AlertSource, AlertStatus
from app.repositories.alert_history import AlertHistoryRepository
from app.repositories.alert_instance import AlertInstanceRepository
from app.services.alert import AlertService
from tests.conftest import make_alert


def _service(db_session: AsyncSession) -> AlertService:
    return AlertService(AlertInstanceRepository(db_session), AlertHistoryRepository(db_session))


class TestAlertCreation:
    async def test_create_records_opening_history_entry(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        alert = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            rule_id=None,
            source=AlertSource.MONITORING,
            severity=Severity.HIGH,
            title="Disk full",
            message="/var at 98%",
            fingerprint=uuid.uuid4().hex,
            source_reference={"target_id": "abc"},
        )
        history = await service.list_history(alert.id)
        assert len(history) == 1
        assert history[0].from_status is None
        assert history[0].to_status == AlertStatus.NEW


class TestAlertTransitions:
    async def test_valid_transition_updates_status_and_history(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session)
        alert = await make_alert(db_session, status=AlertStatus.OPEN)
        caller = uuid.uuid4()

        updated = await service.transition(
            alert.id, AlertStatus.ACKNOWLEDGED, changed_by=caller, reason="on it"
        )
        assert updated.status == AlertStatus.ACKNOWLEDGED

        history = await service.list_history(alert.id)
        assert history[-1].from_status == AlertStatus.OPEN
        assert history[-1].to_status == AlertStatus.ACKNOWLEDGED
        assert history[-1].changed_by == caller

    async def test_invalid_transition_raises_conflict(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        alert = await make_alert(db_session, status=AlertStatus.CLOSED)
        with pytest.raises(ConflictError):
            await service.transition(alert.id, AlertStatus.ACKNOWLEDGED)

    async def test_resolving_sets_resolved_at(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        alert = await make_alert(db_session, status=AlertStatus.OPEN)
        resolved = await service.transition(alert.id, AlertStatus.RESOLVED)
        assert resolved.resolved_at is not None

    async def test_closing_sets_closed_at(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        alert = await make_alert(db_session, status=AlertStatus.RESOLVED)
        closed = await service.transition(alert.id, AlertStatus.CLOSED)
        assert closed.closed_at is not None

    async def test_reopening_clears_prior_resolution(self, db_session: AsyncSession) -> None:
        """A recurrence must not inherit the old occurrence's own resolution time."""
        service = _service(db_session)
        alert = await make_alert(db_session, status=AlertStatus.OPEN)
        await service.transition(alert.id, AlertStatus.RESOLVED)
        reopened = await service.transition(alert.id, AlertStatus.OPEN)
        assert reopened.resolved_at is None

    async def test_unknown_alert_raises_not_found(self, db_session: AsyncSession) -> None:
        with pytest.raises(NotFoundError):
            await _service(db_session).transition(uuid.uuid4(), AlertStatus.RESOLVED)


class TestAlertQueries:
    async def test_list_filters_by_status_and_severity(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        org = uuid.uuid4()
        await make_alert(
            db_session, organization_id=org, status=AlertStatus.OPEN, severity=Severity.HIGH
        )
        await make_alert(
            db_session, organization_id=org, status=AlertStatus.RESOLVED, severity=Severity.LOW
        )

        assert len(await service.list_for_org(org)) == 2
        assert len(await service.list_for_org(org, status=AlertStatus.OPEN)) == 1
        assert len(await service.list_for_org(org, severity=Severity.LOW)) == 1

    async def test_list_is_scoped_to_one_organization(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        mine, theirs = uuid.uuid4(), uuid.uuid4()
        await make_alert(db_session, organization_id=mine)
        await make_alert(db_session, organization_id=theirs)
        assert len(await service.list_for_org(mine)) == 1

    async def test_update_changes_mutable_fields(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        alert = await make_alert(db_session)
        assignee = uuid.uuid4()
        updated = await service.update(
            alert.id, severity=Severity.CRITICAL, title="new", assigned_to=assignee
        )
        assert updated.severity == Severity.CRITICAL
        assert updated.title == "new"
        assert updated.assigned_to == assignee

    async def test_update_leaves_unspecified_fields_alone(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        alert = await make_alert(db_session, severity=Severity.HIGH)
        original_title = alert.title
        updated = await service.update(alert.id, severity=Severity.LOW)
        assert updated.title == original_title
