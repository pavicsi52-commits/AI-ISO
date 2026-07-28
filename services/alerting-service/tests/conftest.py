"""Shared fixtures for the alerting service's test suite.

Everything here runs against real infrastructure (the repository
root's docker-compose Postgres/Redis/RabbitMQ) -- the same discipline
every prior AI-IOS service established. Postgres isolation uses a
per-test SAVEPOINT (``join_transaction_mode="create_savepoint"``), not
a second database: every ``BaseRepository`` write only ``flush()``es,
so an outer, never-committed transaction safely contains everything a
test does.

This service's own database (``aiios_alerting``) is physically
separate from every other AI-IOS service's. Redis test db 18 --
distinct from every other AI-IOS service's own test db (... 16
validation, 17 monitoring). The shared Redis container was already
raised to ``--databases 32`` during Prompt 043, so no further
infrastructure change is needed here.
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
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.config.settings import DatabaseSettings, RabbitMQSettings, RedisSettings
from shared_core.database.engine import create_engine
from shared_core.enums.severity import Severity
from shared_core.queue.factory import QueueFramework, create_queue_framework
from shared_core.security.jwt import encode_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_LOOPBACK = "127.0.0.1"
"""Deliberately the IPv4 literal, never the name ``localhost``.

On Windows, ``localhost`` resolves to ``::1`` (IPv6) *first*, and
Docker Desktop's own IPv6 port forwarding silently **hangs** rather
than refusing the connection -- so the usual fast fallback to IPv4
never happens and every connection attempt burns its full timeout
instead. Diagnosed directly here: ``asyncio.open_connection`` to
``localhost:5433`` times out while ``127.0.0.1:5433`` connects
immediately, with ``socket.getaddrinfo`` confirming ``::1`` is
returned ahead of ``127.0.0.1``. Prior AI-IOS services' own conftests
use ``localhost`` and are exposed to the same stall on a host in this
state.
"""

# Must be set before shared_core.config.cache.get_settings() is first called
# (a process-wide lru_cache singleton), so this whole block runs at import
# time -- ahead of app.api.deps/app.core.factory being imported below, and
# ahead of any fixture or test -- exactly like every other AIIOS_* default
# already set the same way in every prior AI-IOS service's own conftest.
os.environ.setdefault("AIIOS_DATABASE_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_alerting")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "18")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

# app.config.settings.get_settings() is a process-wide lru_cache singleton,
# so the JWT public key path (like every other env var above) must be fixed
# *before* anything calls it for the first time -- generating a session
# keypair inside a fixture and pointing a per-test tmp_path at it doesn't
# work, since only the first test's path would ever actually be read.
_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_alerting_test_keys"
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

os.environ.setdefault("AIIOS_ALERTING_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault(
    "AIIOS_ALERTING_SERVICE_MONITORING_SERVICE_BASE_URL", "http://monitoring.internal"
)
os.environ.setdefault(
    "AIIOS_ALERTING_SERVICE_VALIDATION_SERVICE_BASE_URL", "http://validation.internal"
)
os.environ.setdefault(
    "AIIOS_ALERTING_SERVICE_AUTOMATION_SERVICE_BASE_URL", "http://automation.internal"
)
os.environ.setdefault(
    "AIIOS_ALERTING_SERVICE_WORKFLOW_RUNTIME_SERVICE_BASE_URL", "http://workflow.internal"
)
os.environ.setdefault(
    "AIIOS_ALERTING_SERVICE_CONFIGURATION_SERVICE_BASE_URL", "http://configuration.internal"
)
os.environ.setdefault(
    "AIIOS_ALERTING_SERVICE_DISCOVERY_SERVICE_BASE_URL", "http://discovery.internal"
)
os.environ.setdefault(
    "AIIOS_ALERTING_SERVICE_INVENTORY_SERVICE_BASE_URL", "http://inventory.internal"
)

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.core.factory import create_app  # noqa: E402
from app.models.alert_escalation import AlertEscalationPolicy  # noqa: E402
from app.models.alert_instance import AlertInstance  # noqa: E402
from app.models.alert_maintenance_window import AlertMaintenanceWindow  # noqa: E402
from app.models.alert_oncall_schedule import AlertOnCallSchedule  # noqa: E402
from app.models.alert_route import AlertRoute  # noqa: E402
from app.models.alert_rule import AlertRule  # noqa: E402
from app.models.alert_suppression import AlertSuppression  # noqa: E402
from app.models.enums import (  # noqa: E402
    AlertRouteChannel,
    AlertRuleType,
    AlertSource,
    AlertStatus,
    BooleanOperator,
    MaintenanceWindowScope,
    MaintenanceWindowType,
    OnCallRotationType,
    RouteTargetType,
    SuppressionType,
)

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

MONITORING_SERVICE_BASE_URL = "http://monitoring.internal"
VALIDATION_SERVICE_BASE_URL = "http://validation.internal"
AUTOMATION_SERVICE_BASE_URL = "http://automation.internal"
WORKFLOW_SERVICE_BASE_URL = "http://workflow.internal"
CONFIGURATION_SERVICE_BASE_URL = "http://configuration.internal"
DISCOVERY_SERVICE_BASE_URL = "http://discovery.internal"
INVENTORY_SERVICE_BASE_URL = "http://inventory.internal"


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_alerting",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 18 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=18,
        _env_file=None,
    )


def rabbitmq_test_settings() -> RabbitMQSettings:
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
    """A session factory bound to one per-test SAVEPOINT-isolated
    connection, always rolled back -- exposed separately from
    :func:`db_session` so worker tests can build their own
    ``shared_core.database.factory.DatabaseFramework`` sharing the same
    test transaction.
    """
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


@pytest_asyncio.fixture
async def real_redis_client() -> AsyncIterator[Redis]:
    settings = redis_test_settings()
    client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password or None,
        decode_responses=False,
    )
    try:
        await asyncio.wait_for(client.ping(), timeout=5)
    except UNREACHABLE_ERRORS as exc:
        await client.aclose()
        pytest.skip(f"Redis is not reachable: {exc}")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture
async def real_queue_framework() -> AsyncIterator[QueueFramework]:
    """A real :class:`~shared_core.queue.factory.QueueFramework` -- no in-memory fake."""
    try:
        framework = await asyncio.wait_for(
            create_queue_framework(rabbitmq_test_settings()), timeout=5
        )
    except UNREACHABLE_ERRORS as exc:
        pytest.skip(f"RabbitMQ is not reachable: {exc}")
    yield framework
    await framework.shutdown()


@pytest.fixture(scope="session")
def jwt_keypair() -> tuple[str, str]:
    """The test session's fixed RSA keypair."""
    return (
        _TEST_PRIVATE_KEY_PATH.read_text(encoding="ascii"),
        _TEST_PUBLIC_KEY_PATH.read_text(encoding="ascii"),
    )


@pytest.fixture
def token_for(jwt_keypair: tuple[str, str]) -> Callable[[uuid.UUID], str]:
    """Return a function minting a valid access token for a given user id."""
    private_key, _public_key = jwt_keypair

    def _mint(user_id: uuid.UUID) -> str:
        return encode_token({"sub": str(user_id)}, private_key=private_key)

    return _mint


AuthHeadersFn = Callable[[uuid.UUID], dict[str, str]]
"""The type of the ``auth_headers`` fixture."""


@pytest.fixture
def auth_headers(token_for: Callable[[uuid.UUID], str]) -> AuthHeadersFn:
    """Return a function building ``Authorization`` headers for a given user id."""

    def _headers(user_id: uuid.UUID) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(user_id)}"}

    return _headers


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    ``get_db_session`` is overridden to hand out this test's SAVEPOINT
    session, so every request made through ``client`` in a given test
    shares one transaction, rolled back at teardown.
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


async def make_alert(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    source: AlertSource = AlertSource.MONITORING,
    severity: Severity = Severity.HIGH,
    status: AlertStatus = AlertStatus.OPEN,
    fingerprint: str | None = None,
    source_reference: dict[str, Any] | None = None,
    triggered_at: datetime | None = None,
    rule_id: uuid.UUID | None = None,
) -> AlertInstance:
    """Create a bare :class:`AlertInstance` row directly."""
    alert = AlertInstance(
        organization_id=organization_id or uuid.uuid4(),
        rule_id=rule_id,
        source=source,
        severity=severity,
        status=status,
        title=f"test-alert-{uuid.uuid4().hex[:8]}",
        message="Test alert message.",
        fingerprint=fingerprint or uuid.uuid4().hex,
        source_reference=source_reference or {},
        triggered_at=triggered_at or datetime.now(UTC),
    )
    db_session.add(alert)
    await db_session.flush()
    return alert


async def make_rule(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    rule_type: AlertRuleType = AlertRuleType.METRIC_THRESHOLD,
    source: AlertSource = AlertSource.MONITORING,
    boolean_operator: BooleanOperator = BooleanOperator.AND,
    severity: Severity = Severity.HIGH,
    enabled: bool = True,
) -> AlertRule:
    """Create a bare :class:`AlertRule` row directly."""
    rule = AlertRule(
        organization_id=organization_id or uuid.uuid4(),
        name=f"test-rule-{uuid.uuid4().hex[:8]}",
        rule_type=rule_type,
        source=source,
        boolean_operator=boolean_operator,
        severity=severity,
        enabled=enabled,
    )
    db_session.add(rule)
    await db_session.flush()
    return rule


async def make_route(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    channel: AlertRouteChannel = AlertRouteChannel.EMAIL,
    target_type: RouteTargetType = RouteTargetType.USER,
    target_reference: str | None = None,
    severity_filter: Severity | None = None,
    enabled: bool = True,
) -> AlertRoute:
    """Create a bare :class:`AlertRoute` row directly."""
    route = AlertRoute(
        organization_id=organization_id or uuid.uuid4(),
        name=f"test-route-{uuid.uuid4().hex[:8]}",
        channel=channel,
        target_type=target_type,
        target_reference=target_reference or str(uuid.uuid4()),
        severity_filter=severity_filter,
        enabled=enabled,
    )
    db_session.add(route)
    await db_session.flush()
    return route


async def make_suppression(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    suppression_type: SuppressionType = SuppressionType.MANUAL,
    scope_reference: str | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    enabled: bool = True,
) -> AlertSuppression:
    """Create a bare :class:`AlertSuppression` row directly."""
    suppression = AlertSuppression(
        organization_id=organization_id or uuid.uuid4(),
        suppression_type=suppression_type,
        scope_reference=scope_reference,
        reason="Test suppression.",
        starts_at=starts_at or datetime.now(UTC) - timedelta(minutes=5),
        ends_at=ends_at,
        enabled=enabled,
    )
    db_session.add(suppression)
    await db_session.flush()
    return suppression


async def make_maintenance_window(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    window_type: MaintenanceWindowType = MaintenanceWindowType.SCHEDULED,
    scope: MaintenanceWindowScope = MaintenanceWindowScope.ORGANIZATION,
    scope_reference: str | None = None,
    recurrence_rule: str | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    enabled: bool = True,
) -> AlertMaintenanceWindow:
    """Create a bare :class:`AlertMaintenanceWindow` row directly."""
    now = datetime.now(UTC)
    window = AlertMaintenanceWindow(
        organization_id=organization_id or uuid.uuid4(),
        name=f"test-window-{uuid.uuid4().hex[:8]}",
        window_type=window_type,
        scope=scope,
        scope_reference=scope_reference,
        recurrence_rule=recurrence_rule,
        starts_at=starts_at or now - timedelta(minutes=5),
        ends_at=ends_at or now + timedelta(hours=1),
        enabled=enabled,
    )
    db_session.add(window)
    await db_session.flush()
    return window


async def make_escalation_policy(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    levels: list[dict[str, Any]] | None = None,
    enabled: bool = True,
) -> AlertEscalationPolicy:
    """Create a bare :class:`AlertEscalationPolicy` row directly."""
    policy = AlertEscalationPolicy(
        organization_id=organization_id or uuid.uuid4(),
        name=f"test-policy-{uuid.uuid4().hex[:8]}",
        levels=levels if levels is not None else [],
        enabled=enabled,
    )
    db_session.add(policy)
    await db_session.flush()
    return policy


async def make_oncall_schedule(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    rotation_type: OnCallRotationType = OnCallRotationType.WEEKLY,
    participants: list[str] | None = None,
    overrides: list[dict[str, Any]] | None = None,
    holiday_calendar: list[str] | None = None,
    enabled: bool = True,
) -> AlertOnCallSchedule:
    """Create a bare :class:`AlertOnCallSchedule` row directly."""
    schedule = AlertOnCallSchedule(
        organization_id=organization_id or uuid.uuid4(),
        name=f"test-schedule-{uuid.uuid4().hex[:8]}",
        rotation_type=rotation_type,
        timezone="UTC",
        participants=participants if participants is not None else [],
        overrides=overrides if overrides is not None else [],
        holiday_calendar=holiday_calendar if holiday_calendar is not None else [],
        enabled=enabled,
    )
    db_session.add(schedule)
    await db_session.flush()
    return schedule


__all__ = [
    "AUTOMATION_SERVICE_BASE_URL",
    "CONFIGURATION_SERVICE_BASE_URL",
    "DISCOVERY_SERVICE_BASE_URL",
    "INVENTORY_SERVICE_BASE_URL",
    "MONITORING_SERVICE_BASE_URL",
    "VALIDATION_SERVICE_BASE_URL",
    "WORKFLOW_SERVICE_BASE_URL",
    "AuthHeadersFn",
    "app",
    "auth_headers",
    "client",
    "db_session",
    "db_session_factory",
    "jwt_keypair",
    "make_alert",
    "make_escalation_policy",
    "make_maintenance_window",
    "make_oncall_schedule",
    "make_route",
    "make_rule",
    "make_suppression",
    "pg_engine",
    "postgres_test_settings",
    "rabbitmq_test_settings",
    "real_queue_framework",
    "real_redis_client",
    "redis_test_settings",
    "token_for",
]
