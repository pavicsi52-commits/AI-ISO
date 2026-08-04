"""Test fixtures for the scheduler service.

Everything runs against **real** PostgreSQL, Redis, and RabbitMQ. Nothing
here mocks infrastructure: the notification service is a real manager
with no channel registered, the event publisher is a real awaitable that
records, and the app fixture starts the actual lifespan.

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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_scheduler")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "27")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_scheduler_test_keys"
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

os.environ.setdefault("AIIOS_SCHEDULER_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault("AIIOS_SCHEDULER_SERVICE_SCHEDULER_ENABLED", "false")

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
from app.models.enums import JobPriority, JobType  # noqa: E402
from app.notifications.scheduler_notifications import SchedulerNotificationService  # noqa: E402
from app.repositories.dependency import JobDependencyRepository  # noqa: E402
from app.repositories.execution import (  # noqa: E402
    JobExecutionLogRepository,
    JobExecutionRepository,
)
from app.repositories.governance import (  # noqa: E402
    SchedulerAuditRepository,
    SchedulerReportRepository,
    SchedulerStatisticRepository,
)
from app.repositories.history import JobFailureRepository, JobHistoryRepository  # noqa: E402
from app.repositories.holiday import HolidayCalendarRepository  # noqa: E402
from app.repositories.job import ScheduledJobRepository  # noqa: E402
from app.repositories.maintenance import MaintenanceWindowRepository  # noqa: E402
from app.repositories.priority import JobPriorityPolicyRepository  # noqa: E402
from app.repositories.retry import JobRetryPolicyRepository  # noqa: E402
from app.repositories.trigger import JobScheduleRepository, JobTriggerRepository  # noqa: E402
from app.services.dependency import DependencyService  # noqa: E402
from app.services.execution import ExecutionService  # noqa: E402
from app.services.holiday import HolidayService  # noqa: E402
from app.services.job import JobService  # noqa: E402
from app.services.maintenance import MaintenanceWindowService  # noqa: E402
from app.services.priority import PriorityService  # noqa: E402
from app.services.recovery import RecoveryService  # noqa: E402
from app.services.reporting import AuditService, ReportService, StatisticsService  # noqa: E402
from app.services.trigger import TriggerService  # noqa: E402

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
        database_name="aiios_scheduler",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 27 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=27,
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
def notifications() -> SchedulerNotificationService:
    """A real notification service with no channels registered.

    Not a mock: the manager, router, dispatcher, and dead-letter store all
    run for real, and with no channel registered every send fails the way
    a misconfigured deployment's would. That is the path worth exercising,
    because every caller here is meant to survive it.
    """
    return SchedulerNotificationService(create_notification_framework())


# ---- repositories -----------------------------------------------------------


@pytest.fixture
def jobs_repo(db_session: AsyncSession) -> ScheduledJobRepository:
    return ScheduledJobRepository(db_session)


@pytest.fixture
def triggers_repo(db_session: AsyncSession) -> JobTriggerRepository:
    return JobTriggerRepository(db_session)


@pytest.fixture
def schedules_repo(db_session: AsyncSession) -> JobScheduleRepository:
    return JobScheduleRepository(db_session)


@pytest.fixture
def dependencies_repo(db_session: AsyncSession) -> JobDependencyRepository:
    return JobDependencyRepository(db_session)


@pytest.fixture
def executions_repo(db_session: AsyncSession) -> JobExecutionRepository:
    return JobExecutionRepository(db_session)


@pytest.fixture
def execution_logs_repo(db_session: AsyncSession) -> JobExecutionLogRepository:
    return JobExecutionLogRepository(db_session)


@pytest.fixture
def retry_policies_repo(db_session: AsyncSession) -> JobRetryPolicyRepository:
    return JobRetryPolicyRepository(db_session)


@pytest.fixture
def priority_policies_repo(db_session: AsyncSession) -> JobPriorityPolicyRepository:
    return JobPriorityPolicyRepository(db_session)


@pytest.fixture
def history_repo(db_session: AsyncSession) -> JobHistoryRepository:
    return JobHistoryRepository(db_session)


@pytest.fixture
def failures_repo(db_session: AsyncSession) -> JobFailureRepository:
    return JobFailureRepository(db_session)


@pytest.fixture
def maintenance_repo(db_session: AsyncSession) -> MaintenanceWindowRepository:
    return MaintenanceWindowRepository(db_session)


@pytest.fixture
def holidays_repo(db_session: AsyncSession) -> HolidayCalendarRepository:
    return HolidayCalendarRepository(db_session)


@pytest.fixture
def statistics_repo(db_session: AsyncSession) -> SchedulerStatisticRepository:
    return SchedulerStatisticRepository(db_session)


@pytest.fixture
def reports_repo(db_session: AsyncSession) -> SchedulerReportRepository:
    return SchedulerReportRepository(db_session)


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> SchedulerAuditRepository:
    return SchedulerAuditRepository(db_session)


# ---- services -----------------------------------------------------------


@pytest.fixture
def job_service(db_session: AsyncSession, publisher: RecordingPublisher) -> JobService:
    return JobService(
        ScheduledJobRepository(db_session),
        JobHistoryRepository(db_session),
        publish_event=publisher,
    )


@pytest.fixture
def trigger_service(db_session: AsyncSession, publisher: RecordingPublisher) -> TriggerService:
    return TriggerService(
        JobTriggerRepository(db_session),
        JobScheduleRepository(db_session),
        ScheduledJobRepository(db_session),
        HolidayCalendarRepository(db_session),
        publish_event=publisher,
    )


@pytest.fixture
def dependency_service(db_session: AsyncSession) -> DependencyService:
    return DependencyService(
        JobDependencyRepository(db_session),
        ScheduledJobRepository(db_session),
        JobExecutionRepository(db_session),
    )


@pytest.fixture
def execution_service(
    db_session: AsyncSession,
    job_service: JobService,
    notifications: SchedulerNotificationService,
    publisher: RecordingPublisher,
) -> ExecutionService:
    return ExecutionService(
        JobExecutionRepository(db_session),
        JobExecutionLogRepository(db_session),
        JobFailureRepository(db_session),
        ScheduledJobRepository(db_session),
        JobRetryPolicyRepository(db_session),
        job_service,
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def priority_service(db_session: AsyncSession) -> PriorityService:
    return PriorityService(JobPriorityPolicyRepository(db_session))


@pytest.fixture
def maintenance_service(
    db_session: AsyncSession, publisher: RecordingPublisher
) -> MaintenanceWindowService:
    return MaintenanceWindowService(
        MaintenanceWindowRepository(db_session), publish_event=publisher
    )


@pytest.fixture
def holiday_service(db_session: AsyncSession) -> HolidayService:
    return HolidayService(HolidayCalendarRepository(db_session))


@pytest.fixture
def recovery_service(
    db_session: AsyncSession,
    execution_service: ExecutionService,
    notifications: SchedulerNotificationService,
    publisher: RecordingPublisher,
) -> RecoveryService:
    return RecoveryService(
        JobFailureRepository(db_session),
        ScheduledJobRepository(db_session),
        execution_service,
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def statistics_service(db_session: AsyncSession) -> StatisticsService:
    return StatisticsService(
        SchedulerStatisticRepository(db_session),
        ScheduledJobRepository(db_session),
        JobExecutionRepository(db_session),
    )


@pytest.fixture
def report_service(
    db_session: AsyncSession, statistics_service: StatisticsService
) -> ReportService:
    return ReportService(
        SchedulerReportRepository(db_session),
        ScheduledJobRepository(db_session),
        JobExecutionRepository(db_session),
        JobFailureRepository(db_session),
        statistics_service,
    )


@pytest.fixture
def audit_service(db_session: AsyncSession) -> AuditService:
    return AuditService(SchedulerAuditRepository(db_session))


# ---- helpers --------------------------------------------------------------


MakeJobFn = Callable[..., Any]


@pytest.fixture
def make_job(job_service: JobService, organization_id: uuid.UUID) -> MakeJobFn:
    """Create one job, directly ``ACTIVE``."""

    async def _make(
        name: str = "Nightly inventory sync",
        *,
        job_type: JobType = JobType.CUSTOM_JOB,
        priority: JobPriority = JobPriority.NORMAL,
        **kwargs: Any,
    ) -> Any:
        return await job_service.create(
            organization_id, name=name, job_type=job_type, priority=priority, **kwargs
        )

    return _make


MakeTriggeredJobFn = Callable[..., Any]


@pytest.fixture
def make_job_with_cron_trigger(
    make_job: MakeJobFn, trigger_service: TriggerService, organization_id: uuid.UUID
) -> MakeTriggeredJobFn:
    """A job with one enabled ``cron`` trigger, its schedule already computed."""

    async def _make(*, cron_expression: str = "0 2 * * *", **job_kwargs: Any) -> Any:
        job = await make_job(**job_kwargs)
        await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="cron", cron_expression=cron_expression
        )
        return job

    return _make


@pytest.fixture
def make_job_with_interval_trigger(
    make_job: MakeJobFn, trigger_service: TriggerService, organization_id: uuid.UUID
) -> MakeTriggeredJobFn:
    """A job with one enabled ``interval`` trigger, its schedule already computed."""

    async def _make(*, interval_seconds: float = 3_600, **job_kwargs: Any) -> Any:
        job = await make_job(**job_kwargs)
        await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="interval", interval_seconds=interval_seconds
        )
        return job

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
    "HTTP_OK",
    "HTTP_UNAUTHORIZED",
    "HTTP_UNPROCESSABLE",
    "ago",
    "soon",
    "utcnow",
]
