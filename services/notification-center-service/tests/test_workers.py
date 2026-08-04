"""The four background workers, against real PostgreSQL.

Each worker gets its own session in production; here that session
factory is the same SAVEPOINT-bound one every other fixture uses, so
data created through the service fixtures in the same test is visible
to the worker's own sessions -- see ``tests/conftest.py``'s
``db_session_factory``.

**Reading back what a worker's own session committed.** A worker
commits through a *new* ``AsyncSession`` object bound to the same
underlying connection, not the fixture's ``db_session``. A fresh query
for rows the fixture session never loaded (a list, a count) sees that
commit immediately -- same connection, same transaction. Re-reading an
object the fixture session already loaded into its own identity map
does not: with ``expire_on_commit=False`` that object is never
refreshed just because another session on the same connection
committed. Those reads go through a brand-new ``db_session_factory()``
session instead, the same pattern every prior AI-IOS service's own
``test_workers.py`` already establishes.

Every worker's own ``tick()`` swallows its body's exceptions and returns
a zero/falsy count rather than raising -- so "did it actually do
something" is only checkable by seeding real data first and asserting
either the returned count or a re-queried row's own state afterward.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.notifications.manager import NotificationManager
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import NotificationServiceSettings
from app.models.announcement import NotificationAnnouncement
from app.models.delivery import NotificationDelivery
from app.models.enums import AnnouncementScope, AnnouncementStatus, DigestFrequency, NotificationCategory
from app.models.retry import NotificationRetryQueueEntry
from app.repositories.announcement import NotificationAnnouncementRepository
from app.repositories.delivery import NotificationDeliveryRepository
from app.repositories.governance import NotificationStatisticRepository
from app.repositories.retry import NotificationRetryQueueRepository
from app.workers.announcement_expiry import AnnouncementExpiryWorker
from app.workers.digest_sweep import DigestSweepWorker
from app.workers.retry_sweep import RetrySweepWorker
from app.workers.statistics import StatisticsWorker

pytestmark = pytest.mark.asyncio


def _delivery(
    organization_id: uuid.UUID, notification_id: uuid.UUID, *, channel: str, queued_at: datetime
) -> NotificationDelivery:
    return NotificationDelivery(
        organization_id=organization_id,
        notification_id=notification_id,
        channel=channel,
        status="queued",
        queued_at=queued_at,
    )


def _retry_entry(
    organization_id: uuid.UUID,
    notification_id: uuid.UUID,
    delivery_id: uuid.UUID,
    *,
    next_retry_at: datetime,
) -> NotificationRetryQueueEntry:
    return NotificationRetryQueueEntry(
        organization_id=organization_id,
        notification_id=notification_id,
        delivery_id=delivery_id,
        retry_count=1,
        max_attempts=3,
        next_retry_at=next_retry_at,
        last_error="Simulated failure.",
    )


def _flaky_after(
    real_factory: async_sessionmaker[AsyncSession], *, fail_on_call: int
) -> Callable[[], AsyncSession]:
    """A session factory that raises on its *fail_on_call*-th invocation only.

    Simulates one organization's own session breaking mid-sweep without
    touching any other organization's -- the workers open one session
    per organization by calling ``session_factory()`` with no
    arguments, so the only way to target "one organization's session"
    from outside is by call order.
    """
    calls = {"n": 0}

    def factory() -> AsyncSession:
        calls["n"] += 1
        if calls["n"] == fail_on_call:
            raise RuntimeError("Simulated per-organization session failure.")
        return real_factory()

    return factory


class TestRetrySweepWorker:
    async def test_tick_dispatches_a_due_retry_and_resolves_it(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        notification_manager: NotificationManager,
        service_settings: NotificationServiceSettings,
        make_notification,
        organization_id: uuid.UUID,
    ) -> None:
        notification = await make_notification()
        now = datetime.now(UTC)
        delivery_repo = NotificationDeliveryRepository(db_session)
        delivery = await delivery_repo.create(
            _delivery(organization_id, notification.id, channel="in_app", queued_at=now)
        )
        retry_repo = NotificationRetryQueueRepository(db_session)
        entry = await retry_repo.create(
            _retry_entry(organization_id, notification.id, delivery.id, next_retry_at=now - timedelta(minutes=1))
        )

        worker = RetrySweepWorker(db_session_factory, notification_manager, service_settings)
        dispatched = await worker.tick()
        assert dispatched >= 1

        async with db_session_factory() as fresh:
            refreshed = await NotificationRetryQueueRepository(fresh).require_in_org(
                organization_id, entry.id
            )
            assert refreshed.resolved is True

    async def test_a_tick_with_nothing_due_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession], notification_manager, service_settings
    ) -> None:
        worker = RetrySweepWorker(db_session_factory, notification_manager, service_settings)
        assert await worker.tick() == 0

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession], notification_manager, service_settings
    ) -> None:
        worker = RetrySweepWorker(db_session_factory, notification_manager, service_settings)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_broken_session_factory_is_swallowed_and_reports_zero(
        self, notification_manager: NotificationManager, service_settings: NotificationServiceSettings
    ) -> None:
        def _broken() -> AsyncSession:
            raise RuntimeError("Simulated session failure.")

        worker = RetrySweepWorker(_broken, notification_manager, service_settings)  # type: ignore[arg-type]
        assert await worker.tick() == 0


class TestDigestSweepWorker:
    async def test_tick_sends_a_due_digest_for_a_subscribed_user(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        notification_manager: NotificationManager,
        service_settings: NotificationServiceSettings,
        make_notification,
        make_preference,
    ) -> None:
        await make_preference("digest-user", digest_frequency=DigestFrequency.HOURLY)
        await make_notification("digest-user", subject="Something happened")

        worker = DigestSweepWorker(db_session_factory, notification_manager, service_settings)
        sent = await worker.tick()
        assert sent >= 1

    async def test_a_user_with_no_digest_preference_is_skipped(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        notification_manager: NotificationManager,
        service_settings: NotificationServiceSettings,
        make_notification,
    ) -> None:
        await make_notification("no-digest-user")
        worker = DigestSweepWorker(db_session_factory, notification_manager, service_settings)
        assert await worker.tick() == 0

    async def test_a_tick_with_no_subscribers_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession], notification_manager, service_settings
    ) -> None:
        worker = DigestSweepWorker(db_session_factory, notification_manager, service_settings)
        assert await worker.tick() == 0

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession], notification_manager, service_settings
    ) -> None:
        worker = DigestSweepWorker(db_session_factory, notification_manager, service_settings)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_failed_digest_for_one_user_does_not_poison_the_next(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        notification_manager: NotificationManager,
        service_settings: NotificationServiceSettings,
        make_notification,
        make_preference,
    ) -> None:
        # `_send_one` opens its own session per user precisely so one
        # user's own failure (a broken session, a bad template) never
        # poisons the next user's digest -- a factory that fails on the
        # *first* per-user call (call #1 is `_subscribers()`'s own
        # session, which must succeed) leaves the second subscriber's
        # own digest unaffected. Two subscribers also exercises the
        # sweep's own loop continuing past its first iteration.
        await make_preference("digest-user-a", digest_frequency=DigestFrequency.HOURLY)
        await make_notification("digest-user-a", subject="A")
        await make_preference("digest-user-b", digest_frequency=DigestFrequency.HOURLY)
        await make_notification("digest-user-b", subject="B")

        flaky = _flaky_after(db_session_factory, fail_on_call=2)
        worker = DigestSweepWorker(flaky, notification_manager, service_settings)  # type: ignore[arg-type]
        sent = await worker.tick()
        assert sent == 1


class TestStatisticsWorker:
    async def test_tick_recomputes_every_organization_and_a_row_now_exists(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        make_notification,
        organization_id: uuid.UUID,
    ) -> None:
        await make_notification()
        worker = StatisticsWorker(db_session_factory)
        done = await worker.tick()
        assert done >= 1

        async with db_session_factory() as fresh:
            latest = await NotificationStatisticRepository(fresh).latest(organization_id)
            assert latest is not None

    async def test_a_tick_with_no_organizations_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsWorker(db_session_factory, max_per_tick=0)
        assert await worker.tick() == 0

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_failure_recomputing_one_organization_does_not_poison_the_next(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        notification_service,
        organization_id: uuid.UUID,
    ) -> None:
        # `_organizations()` itself is not wrapped in `tick()`'s own
        # try/except -- only each organization's own `_recompute()` is,
        # per this worker's "one session per organization; a failure on
        # one tenant must not poison the transaction the next one needs"
        # design. So a factory that fails on the *first per-organization*
        # call (call #2 overall -- call #1 is the organizations lookup,
        # which must succeed) leaves the *second* organization's own
        # recompute unaffected.
        other_organization_id = uuid.uuid4()
        await notification_service.create(
            organization_id,
            user_id="user-1",
            category=NotificationCategory.INFORMATION,
            source_service="test-suite",
            body="A",
        )
        await notification_service.create(
            other_organization_id,
            user_id="user-2",
            category=NotificationCategory.INFORMATION,
            source_service="test-suite",
            body="B",
        )

        flaky = _flaky_after(db_session_factory, fail_on_call=2)
        worker = StatisticsWorker(flaky)  # type: ignore[arg-type]
        done = await worker.tick()
        assert done == 1


class TestAnnouncementExpiryWorker:
    async def test_tick_expires_a_published_and_overdue_announcement(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        now = datetime.now(UTC)
        announcement = await NotificationAnnouncementRepository(db_session).create(
            NotificationAnnouncement(
                organization_id=organization_id,
                scope=AnnouncementScope.ORGANIZATION,
                status=AnnouncementStatus.PUBLISHED,
                title="Overdue announcement",
                body="This should have expired already.",
                is_pinned=False,
                published_at=now - timedelta(days=2),
                expires_at=now - timedelta(hours=1),
            )
        )

        worker = AnnouncementExpiryWorker(db_session_factory)
        expired = await worker.tick()
        assert expired >= 1

        async with db_session_factory() as fresh:
            refreshed = await NotificationAnnouncementRepository(fresh).require_in_org(
                organization_id, announcement.id
            )
            assert refreshed.status == str(AnnouncementStatus.EXPIRED)

    async def test_a_published_announcement_not_yet_due_is_left_alone(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        now = datetime.now(UTC)
        announcement = await NotificationAnnouncementRepository(db_session).create(
            NotificationAnnouncement(
                organization_id=organization_id,
                scope=AnnouncementScope.SYSTEM,
                status=AnnouncementStatus.PUBLISHED,
                title="Still active",
                body="Not due yet.",
                is_pinned=False,
                expires_at=now + timedelta(days=1),
            )
        )

        worker = AnnouncementExpiryWorker(db_session_factory)
        await worker.tick()

        async with db_session_factory() as fresh:
            refreshed = await NotificationAnnouncementRepository(fresh).require_in_org(
                organization_id, announcement.id
            )
            assert refreshed.status == str(AnnouncementStatus.PUBLISHED)

    async def test_a_tick_with_nothing_due_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = AnnouncementExpiryWorker(db_session_factory)
        assert await worker.tick() == 0

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = AnnouncementExpiryWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_broken_session_factory_is_swallowed_and_reports_zero(self) -> None:
        def _broken() -> AsyncSession:
            raise RuntimeError("Simulated session failure.")

        worker = AnnouncementExpiryWorker(_broken)  # type: ignore[arg-type]
        assert await worker.tick() == 0
