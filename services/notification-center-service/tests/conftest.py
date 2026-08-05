"""Test fixtures for the notification center service.

Everything runs against **real** PostgreSQL, Redis, and RabbitMQ. Nothing
here mocks infrastructure: the notification manager is a real
`shared_core.notifications.manager.NotificationManager` with a real
`InAppChannel` registered (so an ``IN_APP`` delivery genuinely succeeds)
and every other channel deliberately left unregistered (so a delivery to
any other channel genuinely fails with a real
``ChannelUnavailableError`` -- the exact path
:class:`~app.services.delivery.DeliveryService` is built to survive).
The event publisher is a real awaitable that records, and the app
fixture starts the actual lifespan.

**The one thing the HTTP tests cannot tell you.** The ``app`` fixture
overrides only the request session, so a test's writes roll back. That
override changes *transaction lifetime*, which means any behaviour whose
correctness depends on transaction lifetime is untestable through it.
``AuditService.record_failure`` commits in its own ``session_scope``
precisely so a refused request's audit entry survives the rollback of
the request that raised. Under a SAVEPOINT that distinction vanishes and
the test passes whether the code is right or wrong -- the same reasoning
every prior AI-IOS service's own conftest documents. That path is
therefore exercised at service level against the real session factory,
never over HTTP.

Where a test's isolation differs from production's, the test is only
trustworthy about things that isolation does not touch.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_LOOPBACK = "127.0.0.1"
"""IPv4, never "localhost".

Docker Desktop's IPv6 loopback does not reach the published ports, so a
name that resolves to ``::1`` first makes every connection hang until it
times out rather than failing fast.
"""

os.environ.setdefault("AIIOS_DATABASE_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_notification_center")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "28")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_notification_center_test_keys"
_TEST_KEY_DIR.mkdir(parents=True, exist_ok=True)
_TEST_PRIVATE_KEY_PATH = _TEST_KEY_DIR / "private.pem"
_TEST_PUBLIC_KEY_PATH = _TEST_KEY_DIR / "public.pem"

if not _TEST_PRIVATE_KEY_PATH.is_file():
    _private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _TEST_PRIVATE_KEY_PATH.write_text(
        _private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii"),
        encoding="ascii",
    )
    _TEST_PUBLIC_KEY_PATH.write_text(
        _private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii"),
        encoding="ascii",
    )

os.environ.setdefault("AIIOS_NOTIFICATION_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault("AIIOS_NOTIFICATION_SERVICE_WORKERS_ENABLED", "false")

from shared_core.config.settings import (  # noqa: E402
    DatabaseSettings,
    RabbitMQSettings,
    RedisSettings,
)
from shared_core.database.engine import create_engine  # noqa: E402
from shared_core.notifications.factory import create_notification_framework  # noqa: E402
from shared_core.notifications.in_app import InAppChannel, InAppNotificationStore  # noqa: E402
from shared_core.notifications.manager import NotificationManager  # noqa: E402
from shared_core.security.jwt import encode_token  # noqa: E402

from app.api import deps  # noqa: E402
from app.config.settings import NotificationServiceSettings  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.enums import (  # noqa: E402
    NotificationCategory,
    NotificationChannelKind,
    NotificationPriority,
)
from app.repositories.announcement import (  # noqa: E402
    NotificationAnnouncementRepository,
    NotificationBroadcastRepository,
)
from app.repositories.channel import NotificationChannelConfigRepository  # noqa: E402
from app.repositories.delivery import (  # noqa: E402
    NotificationDeliveryAttemptRepository,
    NotificationDeliveryRepository,
)
from app.repositories.governance import (  # noqa: E402
    NotificationAuditRepository,
    NotificationReportRepository,
    NotificationStatisticRepository,
)
from app.repositories.notification import NotificationRepository  # noqa: E402
from app.repositories.preference import NotificationPreferenceRepository  # noqa: E402
from app.repositories.retry import (  # noqa: E402
    NotificationDeadLetterRepository,
    NotificationRetryQueueRepository,
)
from app.repositories.subscription import NotificationSubscriptionRepository  # noqa: E402
from app.repositories.template import (  # noqa: E402
    NotificationTemplateRepository,
    NotificationTemplateVersionRepository,
)
from app.services.announcement import AnnouncementService  # noqa: E402
from app.services.broadcast import BroadcastService  # noqa: E402
from app.services.channel import ChannelConfigService  # noqa: E402
from app.services.delivery import DeliveryService, build_delivery_service  # noqa: E402
from app.services.digest import DigestService  # noqa: E402
from app.services.notification import NotificationService  # noqa: E402
from app.services.preference import PreferenceService  # noqa: E402
from app.services.reporting import AuditService, ReportService, StatisticsService  # noqa: E402
from app.services.subscription import SubscriptionService  # noqa: E402
from app.services.template import TemplateService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NO_CONTENT = 204
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_notification_center",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 28 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=28,
        _env_file=None,
    )


def rabbitmq_test_settings() -> RabbitMQSettings:
    """The broker the retry/digest/statistics/expiry sweeps run on."""
    return RabbitMQSettings(
        rabbitmq_host=_LOOPBACK,
        rabbitmq_port=5672,
        rabbitmq_user="aiios",
        rabbitmq_password="change-me",
        rabbitmq_vhost="/aiios",
        _env_file=None,
    )


@pytest_asyncio.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine(postgres_test_settings())
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=5)
    except UNREACHABLE_ERRORS as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(
    pg_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory on one per-test SAVEPOINT-isolated connection."""
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        yield async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        await trans.rollback()


@pytest_asyncio.fixture
async def db_session(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """One SAVEPOINT-isolated session per test, always rolled back."""
    async with db_session_factory() as session:
        yield session


@pytest.fixture
def organization_id() -> uuid.UUID:
    """A fresh organization id per test.

    Every test works inside its own tenant, which means every test is
    also, incidentally, a tenant-isolation test: a query that forgot its
    ``organization_id`` filter would see the other tests' rows.
    """
    return uuid.uuid4()


@pytest.fixture(scope="session")
def jwt_keypair() -> tuple[str, str]:
    """The test session's fixed RSA keypair."""
    return (
        _TEST_PRIVATE_KEY_PATH.read_text(encoding="ascii"),
        _TEST_PUBLIC_KEY_PATH.read_text(encoding="ascii"),
    )


AuthHeadersFn = Callable[[uuid.UUID], dict[str, str]]


@pytest.fixture
def auth_headers(jwt_keypair: tuple[str, str]) -> AuthHeadersFn:
    """Build ``Authorization`` headers for a given user id."""
    private_key, _public_key = jwt_keypair

    def _headers(user_id: uuid.UUID) -> dict[str, str]:
        token = encode_token({"sub": str(user_id)}, private_key=private_key)
        return {"Authorization": f"Bearer {token}"}

    return _headers


class RecordingPublisher:
    """A real :data:`~app.types.EventPublisher` that records.

    Not a mock: an awaitable callable with the right signature, so the
    publish path executes for real and a test can assert exactly which
    domain events a flow announced.
    """

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def __call__(self, event: Any) -> None:
        self.events.append(event)

    @property
    def names(self) -> list[str]:
        """The ``event_name`` of every event published, in order."""
        return [event.event_name for event in self.events]


@pytest.fixture
def publisher() -> RecordingPublisher:
    """A recording event publisher."""
    return RecordingPublisher()


@pytest.fixture
def notification_manager() -> NotificationManager:
    """A real `NotificationManager` with only ``IN_APP`` registered.

    Not a mock: the manager, router, dispatcher, retry policy, history,
    and dead-letter store all run for real. ``IN_APP`` (backed by a real,
    fresh `InAppNotificationStore`) always succeeds, so tests can exercise
    a genuine success path; every other channel is deliberately left
    unregistered, so a delivery to it genuinely raises
    ``ChannelUnavailableError`` -- the real failure/retry/dead-letter path
    :class:`~app.services.delivery.DeliveryService` is built to survive.
    """
    manager = create_notification_framework()
    manager.channels.register(InAppChannel(InAppNotificationStore()))
    return manager


@pytest.fixture
def service_settings() -> NotificationServiceSettings:
    """Test-tuned settings: small retry delays, so a retry-sweep test doesn't sleep for real."""
    return NotificationServiceSettings(
        default_max_attempts=3,
        default_base_delay_seconds=0.01,
        default_max_delay_seconds=0.05,
        digest_max_items=50,
        workers_enabled=False,
    )


# ---- repositories -----------------------------------------------------------


@pytest.fixture
def notifications_repo(db_session: AsyncSession) -> NotificationRepository:
    return NotificationRepository(db_session)


@pytest.fixture
def channels_repo(db_session: AsyncSession) -> NotificationChannelConfigRepository:
    return NotificationChannelConfigRepository(db_session)


@pytest.fixture
def templates_repo(db_session: AsyncSession) -> NotificationTemplateRepository:
    return NotificationTemplateRepository(db_session)


@pytest.fixture
def template_versions_repo(db_session: AsyncSession) -> NotificationTemplateVersionRepository:
    return NotificationTemplateVersionRepository(db_session)


@pytest.fixture
def preferences_repo(db_session: AsyncSession) -> NotificationPreferenceRepository:
    return NotificationPreferenceRepository(db_session)


@pytest.fixture
def subscriptions_repo(db_session: AsyncSession) -> NotificationSubscriptionRepository:
    return NotificationSubscriptionRepository(db_session)


@pytest.fixture
def deliveries_repo(db_session: AsyncSession) -> NotificationDeliveryRepository:
    return NotificationDeliveryRepository(db_session)


@pytest.fixture
def delivery_attempts_repo(db_session: AsyncSession) -> NotificationDeliveryAttemptRepository:
    return NotificationDeliveryAttemptRepository(db_session)


@pytest.fixture
def retry_queue_repo(db_session: AsyncSession) -> NotificationRetryQueueRepository:
    return NotificationRetryQueueRepository(db_session)


@pytest.fixture
def dead_letters_repo(db_session: AsyncSession) -> NotificationDeadLetterRepository:
    return NotificationDeadLetterRepository(db_session)


@pytest.fixture
def announcements_repo(db_session: AsyncSession) -> NotificationAnnouncementRepository:
    return NotificationAnnouncementRepository(db_session)


@pytest.fixture
def broadcasts_repo(db_session: AsyncSession) -> NotificationBroadcastRepository:
    return NotificationBroadcastRepository(db_session)


@pytest.fixture
def statistics_repo(db_session: AsyncSession) -> NotificationStatisticRepository:
    return NotificationStatisticRepository(db_session)


@pytest.fixture
def reports_repo(db_session: AsyncSession) -> NotificationReportRepository:
    return NotificationReportRepository(db_session)


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> NotificationAuditRepository:
    return NotificationAuditRepository(db_session)


# ---- services -----------------------------------------------------------


@pytest.fixture
def notification_service(
    db_session: AsyncSession, publisher: RecordingPublisher
) -> NotificationService:
    return NotificationService(NotificationRepository(db_session), publish_event=publisher)


@pytest.fixture
def preference_service(db_session: AsyncSession) -> PreferenceService:
    return PreferenceService(NotificationPreferenceRepository(db_session))


@pytest.fixture
def channel_service(db_session: AsyncSession) -> ChannelConfigService:
    return ChannelConfigService(NotificationChannelConfigRepository(db_session))


@pytest.fixture
def subscription_service(db_session: AsyncSession) -> SubscriptionService:
    return SubscriptionService(NotificationSubscriptionRepository(db_session))


@pytest.fixture
def template_service(db_session: AsyncSession) -> TemplateService:
    return TemplateService(
        NotificationTemplateRepository(db_session),
        NotificationTemplateVersionRepository(db_session),
    )


@pytest.fixture
def delivery_service(
    db_session: AsyncSession,
    notification_manager: NotificationManager,
    service_settings: NotificationServiceSettings,
    publisher: RecordingPublisher,
) -> DeliveryService:
    return build_delivery_service(
        db_session, notification_manager, service_settings, publish_event=publisher
    )


@pytest.fixture
def broadcast_service(
    db_session: AsyncSession,
    notification_service: NotificationService,
    delivery_service: DeliveryService,
    subscription_service: SubscriptionService,
) -> BroadcastService:
    return BroadcastService(
        NotificationBroadcastRepository(db_session),
        notification_service,
        delivery_service,
        subscription_service,
    )


@pytest.fixture
def announcement_service(
    db_session: AsyncSession, publisher: RecordingPublisher
) -> AnnouncementService:
    return AnnouncementService(
        NotificationAnnouncementRepository(db_session), publish_event=publisher
    )


@pytest.fixture
def digest_service(
    db_session: AsyncSession,
    preference_service: PreferenceService,
    notification_service: NotificationService,
    delivery_service: DeliveryService,
    service_settings: NotificationServiceSettings,
) -> DigestService:
    return DigestService(
        NotificationRepository(db_session),
        preference_service,
        notification_service,
        delivery_service,
        max_items=service_settings.digest_max_items,
    )


@pytest.fixture
def statistics_service(db_session: AsyncSession) -> StatisticsService:
    return StatisticsService(
        NotificationStatisticRepository(db_session),
        NotificationRepository(db_session),
        NotificationDeliveryRepository(db_session),
    )


@pytest.fixture
def report_service(db_session: AsyncSession) -> ReportService:
    return ReportService(
        NotificationReportRepository(db_session),
        NotificationDeliveryRepository(db_session),
        NotificationDeadLetterRepository(db_session),
        NotificationRetryQueueRepository(db_session),
        NotificationAuditRepository(db_session),
    )


@pytest.fixture
def audit_service(db_session: AsyncSession) -> AuditService:
    return AuditService(NotificationAuditRepository(db_session))


# ---- composite fixtures --------------------------------------------------


MakeNotificationFn = Callable[..., Any]


@pytest.fixture
def make_notification(
    notification_service: NotificationService, organization_id: uuid.UUID
) -> MakeNotificationFn:
    """Create one notification, ``CREATED`` and not yet dispatched."""

    async def _make(
        user_id: str = "user-1",
        *,
        category: NotificationCategory = NotificationCategory.INFORMATION,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        body: str = "Something happened.",
        source_service: str = "test-suite",
        **kwargs: Any,
    ) -> Any:
        return await notification_service.create(
            organization_id,
            user_id=user_id,
            category=category,
            priority=priority,
            body=body,
            source_service=source_service,
            **kwargs,
        )

    return _make


MakeTemplateFn = Callable[..., Any]


@pytest.fixture
def make_template(template_service: TemplateService, organization_id: uuid.UUID) -> MakeTemplateFn:
    """Register one plain-text template."""

    async def _make(
        template_key: str = "test.template",
        *,
        name: str = "Test template",
        body_template: str = "Hello {{ name }}.",
        **kwargs: Any,
    ) -> Any:
        return await template_service.create(
            organization_id,
            template_key=template_key,
            name=name,
            body_template=body_template,
            **kwargs,
        )

    return _make


MakePreferenceFn = Callable[..., Any]


@pytest.fixture
def make_preference(
    preference_service: PreferenceService, organization_id: uuid.UUID
) -> MakePreferenceFn:
    """Set one user's own preferences, defaulting to only ``IN_APP`` preferred."""

    async def _make(user_id: str = "user-1", **kwargs: Any) -> Any:
        kwargs.setdefault("preferred_channels", [str(NotificationChannelKind.IN_APP)])
        return await preference_service.update(organization_id, user_id, **kwargs)

    return _make


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    PostgreSQL, Redis, RabbitMQ, notifications, and key loading all run
    for real. Only the request session is overridden, so a test's writes
    roll back -- see this module's docstring for the one thing that
    override makes untestable here.
    """
    application = create_app()
    async with application.router.lifespan_context(application):

        async def _override_db_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        application.dependency_overrides[deps.get_db_session] = _override_db_session
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def utcnow() -> datetime:
    """The current moment, timezone-aware."""
    return datetime.now(UTC)


def soon(hours: int = 4) -> datetime:
    """A moment *hours* in the future."""
    return datetime.now(UTC) + timedelta(hours=hours)


def ago(hours: int = 4) -> datetime:
    """A moment *hours* in the past."""
    return datetime.now(UTC) - timedelta(hours=hours)


__all__ = [
    "HTTP_BAD_REQUEST",
    "HTTP_CONFLICT",
    "HTTP_CREATED",
    "HTTP_NOT_FOUND",
    "HTTP_NO_CONTENT",
    "HTTP_OK",
    "HTTP_UNAUTHORIZED",
    "HTTP_UNPROCESSABLE",
    "ago",
    "soon",
    "utcnow",
]
