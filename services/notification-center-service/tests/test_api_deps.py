"""Unit tests for the handful of ``app/api/deps.py`` providers no route reaches.

Every other dependency provider in this module is already exercised
transitively by the HTTP tests in ``tests/test_api_*.py`` -- a request
through a real route builds its whole dependency chain for real. Three
are not, because no *route* currently depends on them:

- ``get_db_session`` itself: every HTTP test overrides it
  (``application.dependency_overrides[deps.get_db_session]``) so a
  test's writes roll back, which means its own real body (a
  ``session_scope`` around the app's session factory) never runs
  through any HTTP test.
- ``get_digest_service``/``DigestSvc``: digests are worker-only
  (``app.workers.digest_sweep``) -- no router declares a
  ``DigestSvc`` parameter.
- ``get_delivery_attempt_repository``/``DeliveryAttemptRepo``: a
  read-only extension point no router currently surfaces.

Called directly here, against real infrastructure, rather than left
uncovered.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest
from shared_core.notifications.factory import create_notification_framework
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api import deps
from app.config.settings import NotificationServiceSettings
from app.repositories.delivery import NotificationDeliveryAttemptRepository
from app.repositories.notification import NotificationRepository
from app.repositories.preference import NotificationPreferenceRepository
from app.services.delivery import build_delivery_service
from app.services.digest import DigestService
from app.services.notification import NotificationService
from app.services.preference import PreferenceService

pytestmark = pytest.mark.asyncio


class TestGetDbSession:
    async def test_yields_a_working_session_and_commits_on_exit(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        fake_request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(db_session_factory=db_session_factory))
        )
        generator = deps.get_db_session(fake_request)  # type: ignore[arg-type]
        session = await generator.__anext__()
        assert isinstance(session, AsyncSession)
        # Draining the generator runs `session_scope`'s own commit path
        # (nothing was written, so there is nothing to actually persist).
        with contextlib.suppress(StopAsyncIteration):
            await generator.__anext__()


class TestGetDigestService:
    async def test_builds_a_working_digest_service(self, db_session: AsyncSession) -> None:
        settings = NotificationServiceSettings(_env_file=None)
        fake_request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(service_settings=settings))
        )
        preferences = PreferenceService(NotificationPreferenceRepository(db_session))
        notifications = NotificationService(NotificationRepository(db_session))
        delivery = build_delivery_service(db_session, create_notification_framework(), settings)

        service = deps.get_digest_service(
            db_session, preferences, notifications, delivery, fake_request  # type: ignore[arg-type]
        )
        assert isinstance(service, DigestService)


class TestGetDeliveryAttemptRepository:
    async def test_builds_a_working_repository(self, db_session: AsyncSession) -> None:
        repository = deps.get_delivery_attempt_repository(db_session)
        assert isinstance(repository, NotificationDeliveryAttemptRepository)
