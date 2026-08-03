"""Test fixtures for the compliance service.

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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_compliance")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "24")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_compliance_test_keys"
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

os.environ.setdefault("AIIOS_COMPLIANCE_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault("AIIOS_COMPLIANCE_SERVICE_SCHEDULER_ENABLED", "false")

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
    ControlSeverity,
    ControlStatus,
    EvidenceKind,
    EvidenceSource,
)
from app.notifications.compliance_notifications import (  # noqa: E402
    ComplianceNotificationService,
)
from app.repositories.catalogue import (  # noqa: E402
    ControlMappingRepository,
    ControlRepository,
    FrameworkRepository,
)
from app.repositories.governance import (  # noqa: E402
    AuditRepository,
    ExceptionRepository,
    FindingRepository,
    RemediationRepository,
    ReportRepository,
    RiskRepository,
    ScoreRepository,
    StatisticRepository,
)
from app.repositories.runs import (  # noqa: E402
    AssessmentRepository,
    EvidenceRepository,
    ResultRepository,
    ScanRepository,
)
from app.rules.engine import Check, CheckOperator, Rule  # noqa: E402
from app.services.assessment import AssessmentService  # noqa: E402
from app.services.catalogue import CatalogueService  # noqa: E402
from app.services.evidence import EvidenceService  # noqa: E402
from app.services.finding import FindingService  # noqa: E402
from app.services.governance import (  # noqa: E402
    ExceptionService,
    RemediationService,
    RiskService,
)
from app.services.reporting import (  # noqa: E402
    AuditService,
    ReportService,
    StatisticsService,
)
from app.services.scoring import ScoringService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_compliance",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 24 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=24,
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
def notifications() -> ComplianceNotificationService:
    """A real notification service with no channels registered.

    Not a mock: the manager, router, dispatcher, and dead-letter store all
    run for real, and with no channel registered every send fails the way
    a misconfigured deployment's would. That is the path worth exercising,
    because every caller here is meant to survive it.
    """
    return ComplianceNotificationService(create_notification_framework())


# ---- services ---------------------------------------------------------


@pytest.fixture
def catalogue_service(db_session: AsyncSession) -> CatalogueService:
    return CatalogueService(
        FrameworkRepository(db_session),
        ControlRepository(db_session),
        ControlMappingRepository(db_session),
    )


@pytest.fixture
def evidence_service(db_session: AsyncSession, publisher: RecordingPublisher) -> EvidenceService:
    return EvidenceService(EvidenceRepository(db_session), publish_event=publisher)


@pytest.fixture
def assessment_service(
    db_session: AsyncSession, publisher: RecordingPublisher
) -> AssessmentService:
    return AssessmentService(
        AssessmentRepository(db_session),
        ResultRepository(db_session),
        ControlRepository(db_session),
        FrameworkRepository(db_session),
        ExceptionRepository(db_session),
        EvidenceRepository(db_session),
        publish_event=publisher,
    )


@pytest.fixture
def finding_service(
    db_session: AsyncSession,
    notifications: ComplianceNotificationService,
    publisher: RecordingPublisher,
) -> FindingService:
    return FindingService(FindingRepository(db_session), notifications, publish_event=publisher)


@pytest.fixture
def exception_service(
    db_session: AsyncSession,
    notifications: ComplianceNotificationService,
    publisher: RecordingPublisher,
) -> ExceptionService:
    return ExceptionService(
        ExceptionRepository(db_session),
        ControlRepository(db_session),
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def risk_service(
    db_session: AsyncSession,
    notifications: ComplianceNotificationService,
    publisher: RecordingPublisher,
) -> RiskService:
    return RiskService(RiskRepository(db_session), notifications, publish_event=publisher)


@pytest.fixture
def remediation_service(
    db_session: AsyncSession,
    notifications: ComplianceNotificationService,
    publisher: RecordingPublisher,
) -> RemediationService:
    return RemediationService(
        RemediationRepository(db_session),
        FindingRepository(db_session),
        ResultRepository(db_session),
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def scoring_service(db_session: AsyncSession, publisher: RecordingPublisher) -> ScoringService:
    return ScoringService(
        ScoreRepository(db_session),
        ResultRepository(db_session),
        AssessmentRepository(db_session),
        FrameworkRepository(db_session),
        ControlRepository(db_session),
        publish_event=publisher,
    )


@pytest.fixture
def statistics_service(db_session: AsyncSession) -> StatisticsService:
    return StatisticsService(
        StatisticRepository(db_session),
        AssessmentRepository(db_session),
        ScanRepository(db_session),
        ResultRepository(db_session),
        EvidenceRepository(db_session),
        FindingRepository(db_session),
        RiskRepository(db_session),
        ExceptionRepository(db_session),
        RemediationRepository(db_session),
        ScoreRepository(db_session),
        ControlRepository(db_session),
        FrameworkRepository(db_session),
    )


@pytest.fixture
def report_service(
    db_session: AsyncSession, statistics_service: StatisticsService
) -> ReportService:
    return ReportService(
        ReportRepository(db_session),
        statistics_service,
        FindingRepository(db_session),
        RiskRepository(db_session),
        ExceptionRepository(db_session),
        ControlRepository(db_session),
        FrameworkRepository(db_session),
        EvidenceRepository(db_session),
        AssessmentRepository(db_session),
        ResultRepository(db_session),
        ScoreRepository(db_session),
        AuditRepository(db_session),
    )


@pytest.fixture
def audit_service(db_session: AsyncSession) -> AuditService:
    return AuditService(AuditRepository(db_session))


# ---- helpers ----------------------------------------------------------


def firewall_rule(name: str = "fw") -> Rule:
    """A one-check rule whose verdict is obvious."""
    return Rule(name=name, checks=[Check(path="firewall.enabled", operator=CheckOperator.IS_TRUE)])


MakeControlFn = Callable[..., Any]


@pytest.fixture
def make_framework(
    catalogue_service: CatalogueService, organization_id: uuid.UUID
) -> MakeControlFn:
    """Create one framework."""

    async def _make(slug: str = "custom", **kwargs: Any) -> Any:
        return await catalogue_service.create_framework(
            organization_id, slug=slug, name=slug.title(), **kwargs
        )

    return _make


@pytest.fixture
def make_control(catalogue_service: CatalogueService, organization_id: uuid.UUID) -> MakeControlFn:
    """Create one control inside a framework."""

    async def _make(
        framework_id: uuid.UUID,
        code: str = "C-1",
        *,
        severity: ControlSeverity = ControlSeverity.HIGH,
        status: ControlStatus = ControlStatus.IMPLEMENTED,
        rule: Rule | None = None,
        **kwargs: Any,
    ) -> Any:
        return await catalogue_service.create_control(
            organization_id,
            framework_id,
            code=code,
            title=f"Control {code}",
            severity=severity,
            status=status,
            rule=rule if rule is not None else firewall_rule(code),
            remediation_guidance="Turn it on.",
            **kwargs,
        )

    return _make


@pytest.fixture
def make_evidence(evidence_service: EvidenceService, organization_id: uuid.UUID) -> MakeControlFn:
    """Record one piece of evidence."""

    async def _make(
        target_id: str = "host-1",
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return await evidence_service.collect(
            organization_id,
            kind=EvidenceKind.CONFIGURATION_SNAPSHOT,
            source=EvidenceSource.DISCOVERY,
            title=f"Snapshot of {target_id}",
            payload=payload if payload is not None else {"firewall": {"enabled": True}},
            target_id=target_id,
            target_type="server",
            **kwargs,
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


def soon(days: int = 30) -> datetime:
    """A moment *days* in the future."""
    return datetime.now(UTC) + timedelta(days=days)
