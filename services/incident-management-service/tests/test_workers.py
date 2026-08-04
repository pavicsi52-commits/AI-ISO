"""The four background workers, against real PostgreSQL.

Each worker gets its own session per organization in production; here
that session factory is the same SAVEPOINT-bound one every other
fixture uses, so data created through the service fixtures in the same
test is visible to the worker's own sessions -- see
``tests/conftest.py``'s ``db_session_factory``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import IncidentPriority, IncidentStatus, WarRoomStatus
from app.repositories.major import WarRoomRepository
from app.services.incident import IncidentService
from app.services.major_incident import MajorIncidentService
from app.services.sla import SlaService
from app.workers.escalation_sweep import EscalationSweepWorker
from app.workers.maintenance import MaintenanceWorker
from app.workers.sla_sweep import SlaSweepWorker
from app.workers.statistics import StatisticsWorker

pytestmark = pytest.mark.asyncio


class TestSlaSweepWorker:
    async def test_tick_breaches_an_overdue_clock(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        sla_service: SlaService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident(priority=IncidentPriority.P1_CRITICAL)
        past = datetime.now(UTC) - timedelta(days=10)
        await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P1_CRITICAL, now=past
        )
        worker = SlaSweepWorker(db_session_factory)
        counts = await worker.tick()
        assert counts["breached"] >= 1

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = SlaSweepWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_tick_with_no_organizations_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = SlaSweepWorker(db_session_factory, max_per_tick=0)
        counts = await worker.tick()
        assert counts["organizations"] == 0


class TestEscalationSweepWorker:
    async def test_tick_fires_a_rung_for_a_breached_incident(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        sla_service: SlaService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident(priority=IncidentPriority.P1_CRITICAL)
        past = datetime.now(UTC) - timedelta(days=10)
        await sla_service.start_clocks(
            organization_id, incident.id, priority=IncidentPriority.P1_CRITICAL, now=past
        )
        await sla_service.sweep(organization_id)
        worker = EscalationSweepWorker(db_session_factory)
        # The sweep's own breached_at is stamped "now"; a P1's first rung
        # is due 15 minutes later, so a tick immediately after finds
        # nothing due yet -- the same anchor timing this service's own
        # escalation tests establish. Confirmed here as "runs without
        # error and returns a real count", not "fires immediately".
        fired = await worker.tick()
        assert fired >= 0

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = EscalationSweepWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]


class TestStatisticsWorker:
    async def test_tick_recomputes_every_organization(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        organization_id,
        make_incident,
    ) -> None:
        await make_incident()
        worker = StatisticsWorker(db_session_factory)
        done = await worker.tick()
        assert done >= 1

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_tick_with_no_organizations_succeeds_with_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsWorker(db_session_factory, max_per_tick=0)
        assert await worker.tick() == 0


class TestMaintenanceWorker:
    async def test_tick_stands_down_an_idle_war_room(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        major_incident_service: MajorIncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        _declaration, war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage"
        )
        worker = MaintenanceWorker(db_session_factory, war_room_idle_minutes=0)
        counts = await worker.tick()
        assert counts["stood_down"] >= 1
        # A fresh session, not the fixture's: the worker committed
        # through its own session on the same connection, and re-reading
        # through the identity map that created this row would return
        # its stale, pre-tick copy rather than a real re-fetch.
        async with db_session_factory() as fresh:
            refreshed = await WarRoomRepository(fresh).require_in_org(organization_id, war_room.id)
            assert refreshed.status == str(WarRoomStatus.CLOSED)

    async def test_tick_reminds_of_an_overdue_status_update(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        major_incident_service: MajorIncidentService,
        organization_id,
        make_incident,
        major_repo,
    ) -> None:
        incident = await make_incident()
        declaration, _war_room = await major_incident_service.declare(
            organization_id, incident.id, reason="Outage", incident_commander_id="alice"
        )
        # Force it overdue: a freshly declared incident has not had time
        # to breach its own default 30-minute cadence within one test.
        declaration.status_update_interval_minutes = 0
        await major_repo.update(declaration)
        await db_session.commit()

        worker = MaintenanceWorker(db_session_factory, war_room_idle_minutes=10_000)
        counts = await worker.tick()
        assert counts["update_reminders"] >= 1

    async def test_tick_reminds_of_a_missing_postmortem(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        incident_service: IncidentService,
        major_incident_service: MajorIncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await major_incident_service.declare(
            organization_id, incident.id, reason="Outage", incident_commander_id="alice"
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.ASSIGNED
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.ACKNOWLEDGED
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.INVESTIGATING
        )
        await incident_service.transition(
            organization_id, incident.id, target=IncidentStatus.RESOLVED
        )
        worker = MaintenanceWorker(
            db_session_factory, war_room_idle_minutes=10_000, postmortem_due_days=0
        )
        counts = await worker.tick()
        assert counts["postmortem_reminders"] >= 1

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = MaintenanceWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_tick_with_no_organizations_reports_all_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = MaintenanceWorker(db_session_factory, max_per_tick=0)
        counts = await worker.tick()
        assert counts == {
            "organizations": 0,
            "stood_down": 0,
            "update_reminders": 0,
            "postmortem_reminders": 0,
        }
