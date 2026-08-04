"""Test fixtures for the incident management service.

Everything runs against **real** PostgreSQL, Redis, and RabbitMQ. Nothing
here mocks infrastructure: the notification service is a real manager
with no channel registered, the event publisher is a real awaitable that
records, and the app fixture starts the actual lifespan.

**The one thing the HTTP tests cannot tell you.** The ``app`` fixture
overrides only the request session, so a test's writes roll back. That
override changes *transaction lifetime*, which means any behaviour whose
correctness depends on transaction lifetime is untestable through it.

Concretely: ``AuditService.record_failure`` commits in its own
``session_scope`` precisely so a refused request's audit entry survives
the rollback of the request that raised. Under a SAVEPOINT that
distinction vanishes and the test passes whether the code is right or
wrong -- which is how the same bug shipped in
``services/knowledge-graph-service`` and stayed green. That path is
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_incident_management")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "25")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_incident_management_test_keys"
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

os.environ.setdefault(
    "AIIOS_INCIDENT_MANAGEMENT_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH)
)
os.environ.setdefault("AIIOS_INCIDENT_MANAGEMENT_SERVICE_SCHEDULER_ENABLED", "false")

from shared_core.config.settings import (  # noqa: E402
    DatabaseSettings,
    RabbitMQSettings,
    RedisSettings,
)
from shared_core.database.engine import create_engine  # noqa: E402
from shared_core.notifications.factory import create_notification_framework  # noqa: E402
from shared_core.security.jwt import encode_token  # noqa: E402

from app.api import deps  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.enums import (  # noqa: E402
    IncidentCategory,
    IncidentPriority,
    IncidentSource,
    WarRoomRole,
)
from app.notifications.incident_notifications import IncidentNotificationService  # noqa: E402
from app.repositories.catalogue import (  # noqa: E402
    IncidentCategoryRepository,
    IncidentPriorityRepository,
    IncidentStatusRepository,
)
from app.repositories.governance import (  # noqa: E402
    AuditRepository,
    ReportRepository,
    StatisticRepository,
)
from app.repositories.impact import (  # noqa: E402
    AssetImpactRepository,
    ImpactRepository,
    ServiceImpactRepository,
)
from app.repositories.incident import IncidentRepository  # noqa: E402
from app.repositories.major import (  # noqa: E402
    MajorIncidentRepository,
    WarRoomParticipantRepository,
    WarRoomRepository,
)
from app.repositories.postmortem import ActionItemRepository, PostmortemRepository  # noqa: E402
from app.repositories.rca import (  # noqa: E402
    KnownErrorRepository,
    ProblemRepository,
    RootCauseRepository,
)
from app.repositories.sla import EscalationRepository, SlaRepository  # noqa: E402
from app.repositories.timeline import (  # noqa: E402
    AssignmentRepository,
    TimelineRepository,
    WorklogRepository,
)
from app.services.assignment import AssignmentService  # noqa: E402
from app.services.escalation import EscalationService  # noqa: E402
from app.services.impact import ImpactService  # noqa: E402
from app.services.incident import IncidentService  # noqa: E402
from app.services.major_incident import MajorIncidentService  # noqa: E402
from app.services.postmortem import PostmortemService  # noqa: E402
from app.services.rca import ProblemService, RootCauseService  # noqa: E402
from app.services.reporting import AuditService, ReportService, StatisticsService  # noqa: E402
from app.services.sla import SlaService  # noqa: E402
from app.sla.engine import BusinessCalendar  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_incident_management",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 25 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=25,
        _env_file=None,
    )


def rabbitmq_test_settings() -> RabbitMQSettings:
    """The broker the scheduler's job queue runs on."""
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
def notifications() -> IncidentNotificationService:
    """A real notification service with no channels registered.

    Not a mock: the manager, router, dispatcher, and dead-letter store all
    run for real, and with no channel registered every send fails the way
    a misconfigured deployment's would. That is the path worth exercising,
    because every caller here is meant to survive it.
    """
    return IncidentNotificationService(create_notification_framework())


# ---- repositories -------------------------------------------------------


@pytest.fixture
def incidents_repo(db_session: AsyncSession) -> IncidentRepository:
    return IncidentRepository(db_session)


@pytest.fixture
def categories_repo(db_session: AsyncSession) -> IncidentCategoryRepository:
    return IncidentCategoryRepository(db_session)


@pytest.fixture
def priorities_repo(db_session: AsyncSession) -> IncidentPriorityRepository:
    return IncidentPriorityRepository(db_session)


@pytest.fixture
def statuses_repo(db_session: AsyncSession) -> IncidentStatusRepository:
    return IncidentStatusRepository(db_session)


@pytest.fixture
def timeline_repo(db_session: AsyncSession) -> TimelineRepository:
    return TimelineRepository(db_session)


@pytest.fixture
def worklog_repo(db_session: AsyncSession) -> WorklogRepository:
    return WorklogRepository(db_session)


@pytest.fixture
def assignment_repo(db_session: AsyncSession) -> AssignmentRepository:
    return AssignmentRepository(db_session)


@pytest.fixture
def sla_repo(db_session: AsyncSession) -> SlaRepository:
    return SlaRepository(db_session)


@pytest.fixture
def escalation_repo(db_session: AsyncSession) -> EscalationRepository:
    return EscalationRepository(db_session)


@pytest.fixture
def impact_repo(db_session: AsyncSession) -> ImpactRepository:
    return ImpactRepository(db_session)


@pytest.fixture
def service_impact_repo(db_session: AsyncSession) -> ServiceImpactRepository:
    return ServiceImpactRepository(db_session)


@pytest.fixture
def asset_impact_repo(db_session: AsyncSession) -> AssetImpactRepository:
    return AssetImpactRepository(db_session)


@pytest.fixture
def major_repo(db_session: AsyncSession) -> MajorIncidentRepository:
    return MajorIncidentRepository(db_session)


@pytest.fixture
def war_room_repo(db_session: AsyncSession) -> WarRoomRepository:
    return WarRoomRepository(db_session)


@pytest.fixture
def war_room_participant_repo(db_session: AsyncSession) -> WarRoomParticipantRepository:
    return WarRoomParticipantRepository(db_session)


@pytest.fixture
def root_cause_repo(db_session: AsyncSession) -> RootCauseRepository:
    return RootCauseRepository(db_session)


@pytest.fixture
def problem_repo(db_session: AsyncSession) -> ProblemRepository:
    return ProblemRepository(db_session)


@pytest.fixture
def known_error_repo(db_session: AsyncSession) -> KnownErrorRepository:
    return KnownErrorRepository(db_session)


@pytest.fixture
def postmortem_repo(db_session: AsyncSession) -> PostmortemRepository:
    return PostmortemRepository(db_session)


@pytest.fixture
def action_item_repo(db_session: AsyncSession) -> ActionItemRepository:
    return ActionItemRepository(db_session)


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> AuditRepository:
    return AuditRepository(db_session)


@pytest.fixture
def report_repo(db_session: AsyncSession) -> ReportRepository:
    return ReportRepository(db_session)


@pytest.fixture
def statistic_repo(db_session: AsyncSession) -> StatisticRepository:
    return StatisticRepository(db_session)


# ---- services -------------------------------------------------------------


@pytest.fixture
def incident_service(
    db_session: AsyncSession,
    notifications: IncidentNotificationService,
    publisher: RecordingPublisher,
) -> IncidentService:
    return IncidentService(
        IncidentRepository(db_session),
        TimelineRepository(db_session),
        WorklogRepository(db_session),
        AssignmentRepository(db_session),
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def sla_service(
    db_session: AsyncSession,
    notifications: IncidentNotificationService,
    publisher: RecordingPublisher,
) -> SlaService:
    return SlaService(
        SlaRepository(db_session),
        IncidentPriorityRepository(db_session),
        IncidentRepository(db_session),
        notifications,
        publish_event=publisher,
        calendar=BusinessCalendar(),
    )


@pytest.fixture
def escalation_service(
    db_session: AsyncSession,
    notifications: IncidentNotificationService,
    publisher: RecordingPublisher,
) -> EscalationService:
    return EscalationService(
        EscalationRepository(db_session),
        SlaRepository(db_session),
        IncidentRepository(db_session),
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def assignment_service(
    db_session: AsyncSession, incident_service: IncidentService
) -> AssignmentService:
    return AssignmentService(IncidentRepository(db_session), incident_service)


@pytest.fixture
def impact_service(db_session: AsyncSession) -> ImpactService:
    return ImpactService(
        ImpactRepository(db_session),
        ServiceImpactRepository(db_session),
        AssetImpactRepository(db_session),
        IncidentRepository(db_session),
    )


@pytest.fixture
def major_incident_service(
    db_session: AsyncSession,
    notifications: IncidentNotificationService,
    publisher: RecordingPublisher,
) -> MajorIncidentService:
    return MajorIncidentService(
        MajorIncidentRepository(db_session),
        WarRoomRepository(db_session),
        WarRoomParticipantRepository(db_session),
        IncidentRepository(db_session),
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def root_cause_service(db_session: AsyncSession) -> RootCauseService:
    return RootCauseService(RootCauseRepository(db_session), IncidentRepository(db_session))


@pytest.fixture
def problem_service(db_session: AsyncSession, publisher: RecordingPublisher) -> ProblemService:
    return ProblemService(
        ProblemRepository(db_session),
        KnownErrorRepository(db_session),
        IncidentRepository(db_session),
        publish_event=publisher,
    )


@pytest.fixture
def postmortem_service(
    db_session: AsyncSession, publisher: RecordingPublisher
) -> PostmortemService:
    return PostmortemService(
        PostmortemRepository(db_session),
        ActionItemRepository(db_session),
        IncidentRepository(db_session),
        publish_event=publisher,
    )


@pytest.fixture
def statistics_service(db_session: AsyncSession) -> StatisticsService:
    return StatisticsService(
        StatisticRepository(db_session),
        IncidentRepository(db_session),
        SlaRepository(db_session),
        EscalationRepository(db_session),
        MajorIncidentRepository(db_session),
        ProblemRepository(db_session),
    )


@pytest.fixture
def report_service(
    db_session: AsyncSession, statistics_service: StatisticsService
) -> ReportService:
    return ReportService(
        ReportRepository(db_session),
        IncidentRepository(db_session),
        statistics_service,
        MajorIncidentRepository(db_session),
        ProblemRepository(db_session),
        PostmortemRepository(db_session),
    )


@pytest.fixture
def audit_service(db_session: AsyncSession) -> AuditService:
    return AuditService(AuditRepository(db_session))


# ---- helpers ----------------------------------------------------------


MakeIncidentFn = Callable[..., Any]


@pytest.fixture
def make_incident(incident_service: IncidentService, organization_id: uuid.UUID) -> MakeIncidentFn:
    """Open one incident."""

    async def _make(
        title: str = "Something is on fire",
        *,
        priority: IncidentPriority = IncidentPriority.P3_MEDIUM,
        category: IncidentCategory = IncidentCategory.APPLICATION,
        source: IncidentSource = IncidentSource.MANUAL,
        **kwargs: Any,
    ) -> Any:
        created, _is_new = await incident_service.create(
            organization_id,
            title=title,
            priority=priority,
            category=category,
            source=source,
            **kwargs,
        )
        return created

    return _make


@pytest.fixture
def make_major_incident(
    major_incident_service: MajorIncidentService,
    make_incident: MakeIncidentFn,
    organization_id: uuid.UUID,
) -> MakeIncidentFn:
    """Declare one incident major, opening its war room."""

    async def _make(*, commander_id: str = "commander-1", reason: str = "Widespread outage") -> Any:
        incident = await make_incident()
        return await major_incident_service.declare(
            organization_id,
            incident.id,
            reason=reason,
            incident_commander_id=commander_id,
        )

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


def soon(minutes: int = 30) -> datetime:
    """A moment *minutes* in the future."""
    return datetime.now(UTC) + timedelta(minutes=minutes)


def ago(minutes: int = 30) -> datetime:
    """A moment *minutes* in the past."""
    return datetime.now(UTC) - timedelta(minutes=minutes)


__all__ = [
    "HTTP_BAD_REQUEST",
    "HTTP_CONFLICT",
    "HTTP_CREATED",
    "HTTP_NOT_FOUND",
    "HTTP_OK",
    "HTTP_UNAUTHORIZED",
    "HTTP_UNPROCESSABLE",
    "WarRoomRole",
    "ago",
    "soon",
    "utcnow",
]
