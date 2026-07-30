"""Shared fixtures for the policy engine service's test suite.

Everything runs against real infrastructure: PostgreSQL with per-test
SAVEPOINT isolation, plus real Redis and RabbitMQ through the application
lifespan.

**One thing this suite deliberately does not trust itself about.** The
``app`` fixture overrides the request session with a SAVEPOINT-isolated
one, which does *not* roll back the way a real request does. Anything
whose correctness depends on transaction lifetime -- the ``DENIED`` audit
path above all -- is therefore tested at the service level against the
real session factory, not over HTTP. That distinction is here because
ignoring it shipped a broken audit trail in
``services/knowledge-graph-service``: the API test passed for as long as
the behaviour was wrong.

Redis test db 23 -- distinct from every other AI-IOS service's own
(... 21 dashboard, 22 knowledge-graph).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from shared_core.config.settings import (
    DatabaseSettings,
    RabbitMQSettings,
    RedisSettings,
)
from shared_core.database.engine import create_engine
from shared_core.notifications.factory import create_notification_framework
from shared_core.security.jwt import encode_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_LOOPBACK = "127.0.0.1"
"""The IPv4 literal, never the name ``localhost``.

On Windows ``localhost`` resolves to ``::1`` first, and Docker Desktop's
IPv6 forwarding hangs rather than refusing, so every connection burns its
full timeout instead of falling back. Diagnosed during Prompt 045.
"""

os.environ.setdefault("AIIOS_DATABASE_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_policy_engine")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "23")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_policy_engine_test_keys"
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

os.environ.setdefault("AIIOS_POLICY_ENGINE_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
# The scheduler polls RabbitMQ and elects a leader; a suite that started
# it would race every test against a background rollup or sweep.
os.environ.setdefault("AIIOS_POLICY_ENGINE_SERVICE_SCHEDULER_ENABLED", "false")

from app.api import deps  # noqa: E402  -- see the env var block above
from app.core.factory import create_app  # noqa: E402
from app.models.enums import (  # noqa: E402
    ActionType,
    AttributeSource,
    LogicalOperator,
    PolicyCategory,
    PolicyEffect,
    PolicyStatus,
    PolicyType,
    ResourceType,
    RuleOperator,
    SubjectType,
)
from app.notifications.policy_notifications import PolicyNotificationService  # noqa: E402
from app.repositories.policy import (  # noqa: E402
    PolicyAttributeRepository,
    PolicyConditionRepository,
    PolicyRepository,
    PolicyRuleRepository,
    PolicyVersionRepository,
)
from app.repositories.runtime import (  # noqa: E402
    PolicyApprovalRepository,
    PolicyAuditRepository,
    PolicyDecisionRepository,
    PolicyExceptionRepository,
    PolicyQuotaRepository,
    PolicyReportRepository,
    PolicySimulationRepository,
    PolicyStatisticsRepository,
    PolicyViolationRepository,
)
from app.rules.engine import Condition, Rule  # noqa: E402
from app.services.approval import ApprovalService  # noqa: E402
from app.services.compliance import AuditService, ComplianceService  # noqa: E402
from app.services.decision import DecisionService  # noqa: E402
from app.services.policy import PolicyService, status_of  # noqa: E402
from app.services.quota import QuotaService  # noqa: E402
from app.services.simulation import SimulationService  # noqa: E402
from app.services.statistics import ReportService, StatisticsService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

HTTP_OK = 200


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_policy_engine",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 23 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=23,
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
    also a tenant-isolation test as a side effect.
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
    """A real :data:`~app.types.EventPublisher` that records events.

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
def notifications() -> PolicyNotificationService:
    """A real notification service with no channels registered.

    Not a mock: the manager, router, dispatcher, and dead-letter store all
    run for real, and with no channel registered every send fails the way
    a misconfigured deployment's would. That is the path worth exercising,
    because every caller here is meant to survive it.
    """
    return PolicyNotificationService(create_notification_framework())


# ---- services ---------------------------------------------------------


@pytest.fixture
def policy_service(db_session: AsyncSession, publisher: RecordingPublisher) -> PolicyService:
    return PolicyService(
        PolicyRepository(db_session),
        PolicyRuleRepository(db_session),
        PolicyConditionRepository(db_session),
        PolicyVersionRepository(db_session),
        publish_event=publisher,
    )


@pytest.fixture
def decision_service(db_session: AsyncSession) -> DecisionService:
    return DecisionService(
        PolicyRepository(db_session),
        PolicyDecisionRepository(db_session),
        PolicyExceptionRepository(db_session),
        PolicyQuotaRepository(db_session),
        PolicyAttributeRepository(db_session),
    )


@pytest.fixture
def approval_service(
    db_session: AsyncSession,
    notifications: PolicyNotificationService,
    publisher: RecordingPublisher,
) -> ApprovalService:
    return ApprovalService(
        PolicyApprovalRepository(db_session),
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def quota_service(
    db_session: AsyncSession,
    notifications: PolicyNotificationService,
    publisher: RecordingPublisher,
) -> QuotaService:
    return QuotaService(
        PolicyQuotaRepository(db_session),
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def simulation_service(
    db_session: AsyncSession,
    notifications: PolicyNotificationService,
    publisher: RecordingPublisher,
) -> SimulationService:
    return SimulationService(
        PolicyRepository(db_session),
        PolicySimulationRepository(db_session),
        notifications,
        PolicyRuleRepository(db_session),
        PolicyConditionRepository(db_session),
        publish_event=publisher,
    )


@pytest.fixture
def compliance_service(
    db_session: AsyncSession,
    notifications: PolicyNotificationService,
    publisher: RecordingPublisher,
) -> ComplianceService:
    return ComplianceService(
        PolicyViolationRepository(db_session),
        PolicyExceptionRepository(db_session),
        notifications,
        publish_event=publisher,
    )


@pytest.fixture
def audit_service(db_session: AsyncSession) -> AuditService:
    return AuditService(PolicyAuditRepository(db_session))


@pytest.fixture
def statistics_service(db_session: AsyncSession) -> StatisticsService:
    return StatisticsService(
        PolicyRepository(db_session),
        PolicyDecisionRepository(db_session),
        PolicyViolationRepository(db_session),
        PolicyApprovalRepository(db_session),
        PolicyStatisticsRepository(db_session),
    )


@pytest.fixture
def report_service(
    db_session: AsyncSession, statistics_service: StatisticsService
) -> ReportService:
    return ReportService(
        PolicyReportRepository(db_session),
        PolicyRepository(db_session),
        PolicyDecisionRepository(db_session),
        PolicyViolationRepository(db_session),
        PolicyApprovalRepository(db_session),
        statistics_service,
    )


# ---- helpers ----------------------------------------------------------


def simple_rule(
    path: str = "department",
    operator: RuleOperator = RuleOperator.EQUALS,
    value: Any = "platform",
    *,
    source: AttributeSource = AttributeSource.SUBJECT,
) -> Rule:
    """A one-condition rule, for policies whose match is obvious."""
    return Rule(
        name="root",
        logical_operator=LogicalOperator.ALL,
        conditions=[Condition(source=source, path=path, operator=operator, value=value)],
    )


async def approve(
    policy_service: PolicyService, organization_id: uuid.UUID, policy_id: uuid.UUID
) -> None:
    """Walk a policy to APPROVED from wherever it currently is.

    Publishing is only legal from APPROVED, so every test that wants a
    live policy has to come through the review states -- including the
    second time around, since re-issuing a live policy means
    PUBLISHED -> DRAFT -> REVIEW -> APPROVED again.
    """
    route: dict[PolicyStatus, tuple[PolicyStatus, ...]] = {
        PolicyStatus.DRAFT: (PolicyStatus.REVIEW, PolicyStatus.APPROVED),
        PolicyStatus.REVIEW: (PolicyStatus.APPROVED,),
        PolicyStatus.APPROVED: (),
        PolicyStatus.PUBLISHED: (
            PolicyStatus.DRAFT,
            PolicyStatus.REVIEW,
            PolicyStatus.APPROVED,
        ),
    }
    current = status_of(await policy_service.get_policy(organization_id, policy_id))
    for target in route[current]:
        await policy_service.transition(organization_id, policy_id, target=target)


PublishedPolicyFn = Callable[..., Any]


@pytest.fixture
def make_policy(policy_service: PolicyService, organization_id: uuid.UUID) -> PublishedPolicyFn:
    """Author, rule, and publish one policy in a single call.

    Returns an awaitable factory. Most tests need a *published* policy --
    a draft cannot influence a decision, which is the whole point of the
    lifecycle -- and doing the three steps by hand in every test would
    bury what each one is actually asserting.
    """

    async def _make(
        slug: str,
        effect: PolicyEffect,
        *,
        rule: Rule | None = None,
        priority: int = 100,
        category: PolicyCategory = PolicyCategory.AUTHORIZATION,
        policy_type: PolicyType = PolicyType.ABAC,
        resource_types: list[str] | None = None,
        actions: list[str] | None = None,
        subject_types: list[str] | None = None,
        obligations: dict[str, Any] | None = None,
        risk_weight: float = 0.0,
        publish: bool = True,
    ) -> Any:
        created = await policy_service.create_policy(
            organization_id,
            slug=slug,
            name=slug.replace("-", " ").title(),
            effect=effect,
            category=category,
            policy_type=policy_type,
            priority=priority,
            resource_types=resource_types or [],
            actions=actions or [],
            subject_types=subject_types or [],
            obligations=obligations or {},
            risk_weight=risk_weight,
        )
        await policy_service.set_rule_tree(organization_id, created.id, rule or simple_rule())
        if not publish:
            return created
        # Draft -> review -> approved -> published, in full: publish
        # refuses anything that is not APPROVED, which is the whole
        # reason the review states exist.
        await approve(policy_service, organization_id, created.id)
        return await policy_service.publish(organization_id, created.id)

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


__all__ = [
    "HTTP_OK",
    "ActionType",
    "AuthHeadersFn",
    "PublishedPolicyFn",
    "RecordingPublisher",
    "ResourceType",
    "SubjectType",
    "app",
    "approval_service",
    "audit_service",
    "auth_headers",
    "client",
    "compliance_service",
    "db_session",
    "db_session_factory",
    "decision_service",
    "jwt_keypair",
    "make_policy",
    "notifications",
    "organization_id",
    "pg_engine",
    "policy_service",
    "postgres_test_settings",
    "publisher",
    "quota_service",
    "rabbitmq_test_settings",
    "redis_test_settings",
    "report_service",
    "simple_rule",
    "simulation_service",
    "statistics_service",
    "utcnow",
]
