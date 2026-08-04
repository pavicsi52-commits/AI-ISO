"""The four background workers, against real PostgreSQL.

Each worker gets its own session per organization in production; here
that session factory is the same SAVEPOINT-bound one every other
fixture uses, so data created through the service fixtures in the same
test is visible to the worker's own sessions -- see
``tests/conftest.py``'s ``db_session_factory``.
"""

from __future__ import annotations

import pytest
from shared_core.notifications.factory import create_notification_framework
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import ago

from app.models.enums import ApprovalPolicy, ApprovalStatus
from app.notifications.change_notifications import ChangeNotificationService
from app.repositories.approval import ChangeApprovalRepository
from app.repositories.change import ChangeRequestRepository
from app.repositories.conflict import ChangeConflictRepository
from app.repositories.governance import ChangeStatisticRepository
from app.services.approval import ApprovalService
from app.workers.approval_expiry_sweep import ApprovalExpirySweepWorker
from app.workers.conflict_sweep import ConflictSweepWorker
from app.workers.maintenance import MaintenanceWorker
from app.workers.statistics import StatisticsWorker

pytestmark = pytest.mark.asyncio


class TestConflictSweepWorker:
    async def test_tick_detects_a_new_conflict_between_overlapping_changes(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        conflicts_repo: ChangeConflictRepository,
        organization_id,
        make_scheduled_change,
    ) -> None:
        # Two changes scheduled into the exact same window: a scheduling
        # conflict even before either affects a shared asset.
        await make_scheduled_change()
        await make_scheduled_change()
        worker = ConflictSweepWorker(db_session_factory)
        counts = await worker.tick()
        assert counts["organizations"] >= 1
        assert counts["changes_checked"] >= 2
        assert counts["conflicts_found"] >= 1

        active = await conflicts_repo.list_active(organization_id)
        assert len(active) >= 1

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = ConflictSweepWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_tick_with_no_organizations_reports_all_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = ConflictSweepWorker(db_session_factory, max_per_tick=0)
        counts = await worker.tick()
        assert counts == {"organizations": 0, "changes_checked": 0, "conflicts_found": 0}


class TestApprovalExpirySweepWorker:
    async def test_tick_expires_an_overdue_pending_approval(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        approval_service: ApprovalService,
        approvals_repo: ChangeApprovalRepository,
        organization_id,
        make_assessed_change,
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        approval = approvals[0]
        approval.expires_at = ago(hours=1)
        await approvals_repo.update(approval)

        notifications = ChangeNotificationService(create_notification_framework())
        worker = ApprovalExpirySweepWorker(db_session_factory, notifications)
        expired = await worker.tick()
        assert expired >= 1

        # A fresh session, not the fixture's: the worker committed
        # through its own session on the same connection, and re-reading
        # through the identity map that created this row would return
        # its stale, pre-tick copy rather than a real re-fetch.
        async with db_session_factory() as fresh:
            refreshed = await ChangeApprovalRepository(fresh).require_in_org(
                organization_id, approval.id
            )
            assert refreshed.status == str(ApprovalStatus.EXPIRED)

    async def test_tick_leaves_an_unexpired_pending_approval_alone(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        approval_service: ApprovalService,
        approvals_repo: ChangeApprovalRepository,
        organization_id,
        make_assessed_change,
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        approval = approvals[0]

        notifications = ChangeNotificationService(create_notification_framework())
        worker = ApprovalExpirySweepWorker(db_session_factory, notifications)
        expired = await worker.tick()
        assert expired == 0

        refreshed = await approvals_repo.require_in_org(organization_id, approval.id)
        assert refreshed.status == str(ApprovalStatus.PENDING)

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        notifications = ChangeNotificationService(create_notification_framework())
        worker = ApprovalExpirySweepWorker(db_session_factory, notifications)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_tick_with_no_organizations_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        notifications = ChangeNotificationService(create_notification_framework())
        worker = ApprovalExpirySweepWorker(db_session_factory, notifications, max_per_tick=0)
        assert await worker.tick() == 0


class TestStatisticsWorker:
    async def test_tick_recomputes_every_organization(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        statistics_repo: ChangeStatisticRepository,
        organization_id,
        make_change,
    ) -> None:
        await make_change()
        worker = StatisticsWorker(db_session_factory)
        done = await worker.tick()
        assert done >= 1

        # A fresh session, not the fixture's: the worker committed
        # through its own session on the same connection, and re-reading
        # through the identity map that created this row would return
        # its stale, pre-tick copy rather than a real re-fetch.
        async with db_session_factory() as fresh:
            latest = await ChangeStatisticRepository(fresh).latest(organization_id)
            assert latest is not None

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
    async def test_tick_reminds_of_an_overdue_post_implementation_review(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        changes_repo: ChangeRequestRepository,
        organization_id,
        make_completed_change,
    ) -> None:
        change = await make_completed_change(technical_owner_id="owner-1")
        stored = await changes_repo.require_in_org(organization_id, change.id)
        stored.completed_at = ago(hours=24 * 10)
        stored.actual_end_at = ago(hours=24 * 10)
        await changes_repo.update(stored)

        notifications = ChangeNotificationService(create_notification_framework())
        worker = MaintenanceWorker(db_session_factory, notifications)
        reminded = await worker.tick()
        assert reminded >= 1

    async def test_tick_does_not_remind_within_the_due_window(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        organization_id,
        make_completed_change,
    ) -> None:
        # Just completed: well within the default 5-day PIR grace period.
        await make_completed_change(technical_owner_id="owner-2")
        notifications = ChangeNotificationService(create_notification_framework())
        worker = MaintenanceWorker(db_session_factory, notifications)
        reminded = await worker.tick()
        assert reminded == 0

    async def test_tick_skips_a_change_with_no_technical_owner(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        changes_repo: ChangeRequestRepository,
        organization_id,
        make_completed_change,
    ) -> None:
        change = await make_completed_change()
        stored = await changes_repo.require_in_org(organization_id, change.id)
        assert stored.technical_owner_id is None
        stored.completed_at = ago(hours=24 * 10)
        stored.actual_end_at = ago(hours=24 * 10)
        await changes_repo.update(stored)

        notifications = ChangeNotificationService(create_notification_framework())
        worker = MaintenanceWorker(db_session_factory, notifications)
        reminded = await worker.tick()
        assert reminded == 0

    async def test_tick_skips_a_change_that_already_has_a_review(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        changes_repo: ChangeRequestRepository,
        pir_service,
        organization_id,
        make_completed_change,
    ) -> None:
        change = await make_completed_change(technical_owner_id="owner-3")
        await pir_service.start(organization_id, change.id)
        stored = await changes_repo.require_in_org(organization_id, change.id)
        stored.completed_at = ago(hours=24 * 10)
        stored.actual_end_at = ago(hours=24 * 10)
        await changes_repo.update(stored)

        notifications = ChangeNotificationService(create_notification_framework())
        worker = MaintenanceWorker(db_session_factory, notifications)
        reminded = await worker.tick()
        assert reminded == 0

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        notifications = ChangeNotificationService(create_notification_framework())
        worker = MaintenanceWorker(db_session_factory, notifications)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_tick_with_no_organizations_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        notifications = ChangeNotificationService(create_notification_framework())
        worker = MaintenanceWorker(db_session_factory, notifications, max_per_tick=0)
        assert await worker.tick() == 0
