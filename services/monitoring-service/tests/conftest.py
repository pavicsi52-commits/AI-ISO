"""Shared fixtures for the monitoring service's test suite.

Everything here runs against real infrastructure (the repository
root's docker-compose Postgres/Redis/RabbitMQ) -- the same discipline
every prior AI-IOS service established. Postgres isolation uses a
per-test SAVEPOINT (``join_transaction_mode="create_savepoint"``), not
a second database: every ``BaseRepository`` write only ``flush()``es,
so an outer, never-committed transaction safely contains everything a
test does.

No Neo4j fixture exists here -- docs/044 names no graph concept for
this service.

**Collector testing**: real native collectors
(:mod:`app.collectors.network`) are exercised against genuine local
TCP/DNS/TLS state where practical; every cross-service collector
(:mod:`app.collectors.remote`/:mod:`app.collectors.service_state`) is
tested via ``pytest-httpx`` against Inventory/Discovery/Configuration
Management/Automation/Workflow Runtime/Validation's own real documented
response shapes, never a live account, the same precedent
``services/validation-service``'s own cross-service tests established.

This service's own database (``aiios_monitoring``) is physically
separate from every other AI-IOS service's. Redis test db 17 --
distinct from every other AI-IOS service's own test db (... 15
workflow-runtime, 16 validation).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
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
from shared_core.queue.factory import QueueFramework, create_queue_framework
from shared_core.security.jwt import encode_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Must be set before shared_core.config.cache.get_settings() is first called
# (a process-wide lru_cache singleton), so this whole block runs at import
# time -- ahead of app.api.deps/app.core.factory being imported below, and
# ahead of any fixture or test -- exactly like every other AIIOS_* default
# already set the same way in every prior AI-IOS service's own conftest.
os.environ.setdefault("AIIOS_DATABASE_HOST", "localhost")
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_monitoring")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "17")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", "localhost")
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

# app.config.settings.get_settings() is a process-wide lru_cache singleton,
# so the JWT public key path (like every other env var above) must be fixed
# *before* anything calls it for the first time -- generating a session
# keypair inside a fixture and pointing a per-test tmp_path at it doesn't
# work, since only the first test's path would ever actually be read.
_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_monitoring_test_keys"
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

os.environ.setdefault("AIIOS_MONITORING_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault(
    "AIIOS_MONITORING_SERVICE_INVENTORY_SERVICE_BASE_URL", "http://inventory.internal"
)
os.environ.setdefault(
    "AIIOS_MONITORING_SERVICE_DISCOVERY_SERVICE_BASE_URL", "http://discovery.internal"
)
os.environ.setdefault(
    "AIIOS_MONITORING_SERVICE_CONFIGURATION_SERVICE_BASE_URL", "http://configuration.internal"
)
os.environ.setdefault(
    "AIIOS_MONITORING_SERVICE_AUTOMATION_SERVICE_BASE_URL", "http://automation.internal"
)
os.environ.setdefault(
    "AIIOS_MONITORING_SERVICE_WORKFLOW_RUNTIME_SERVICE_BASE_URL", "http://workflow.internal"
)
os.environ.setdefault(
    "AIIOS_MONITORING_SERVICE_VALIDATION_SERVICE_BASE_URL", "http://validation.internal"
)

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.clients.automation_client import AutomationClient  # noqa: E402
from app.clients.configuration_client import ConfigurationClient  # noqa: E402
from app.clients.discovery_client import DiscoveryClient  # noqa: E402
from app.clients.inventory_client import InventoryClient  # noqa: E402
from app.clients.validation_client import ValidationClient  # noqa: E402
from app.clients.workflow_client import WorkflowRuntimeClient  # noqa: E402
from app.collectors.context import CollectorContext  # noqa: E402
from app.collectors.registry import CollectorRegistry  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.enums import (  # noqa: E402
    MetricType,
    MonitoringTargetType,
    SyntheticCheckType,
    ThresholdType,
)
from app.models.monitoring_collector import MonitoringCollector  # noqa: E402
from app.models.monitoring_metric import MonitoringMetric  # noqa: E402
from app.models.monitoring_synthetic_test import MonitoringSyntheticTest  # noqa: E402
from app.models.monitoring_target import MonitoringTarget  # noqa: E402
from app.models.monitoring_threshold import MonitoringThreshold  # noqa: E402
from app.repositories.monitoring_availability import MonitoringAvailabilityRepository  # noqa: E402
from app.repositories.monitoring_health import MonitoringHealthRepository  # noqa: E402
from app.repositories.monitoring_metric import MonitoringMetricRepository  # noqa: E402
from app.repositories.monitoring_metric_series import (  # noqa: E402
    MonitoringMetricSeriesRepository,
)
from app.repositories.monitoring_rule import MonitoringRuleRepository  # noqa: E402
from app.repositories.monitoring_target import MonitoringTargetRepository  # noqa: E402
from app.repositories.monitoring_threshold import MonitoringThresholdRepository  # noqa: E402
from app.services.availability import MonitoringAvailabilityService  # noqa: E402
from app.services.collection import EventPublisher, MonitoringCollectionService  # noqa: E402
from app.services.health import MonitoringHealthService  # noqa: E402
from app.services.metric import MonitoringMetricService  # noqa: E402
from app.services.metric_series import MonitoringMetricSeriesService  # noqa: E402
from app.services.synthetic_execution import MonitoringSyntheticExecutionService  # noqa: E402
from app.services.target import MonitoringTargetService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

INVENTORY_SERVICE_BASE_URL = "http://inventory.internal"
DISCOVERY_SERVICE_BASE_URL = "http://discovery.internal"
CONFIGURATION_SERVICE_BASE_URL = "http://configuration.internal"
AUTOMATION_SERVICE_BASE_URL = "http://automation.internal"
WORKFLOW_SERVICE_BASE_URL = "http://workflow.internal"
VALIDATION_SERVICE_BASE_URL = "http://validation.internal"


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios_monitoring",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 17 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=17,
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
    test transaction (a worker opens its own session via
    ``session_scope(database.session_factory)`` rather than receiving
    one directly).
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


def rabbitmq_test_settings() -> RabbitMQSettings:
    return RabbitMQSettings(
        rabbitmq_host="localhost",
        rabbitmq_port=5672,
        rabbitmq_user="aiios",
        rabbitmq_password="change-me",
        rabbitmq_vhost="/aiios",
        _env_file=None,
    )


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
    """The test session's fixed RSA keypair -- see the module-level key
    generation above for why this can't be regenerated per-test.
    """
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
"""The type of the ``auth_headers`` fixture -- exported so every test
module can annotate its own ``auth_headers`` parameter without
repeating the ``Callable[...]`` shape.
"""


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


async def make_target(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    target_type: MonitoringTargetType = MonitoringTargetType.PHYSICAL_SERVER,
    external_id: str | None = None,
    target_metadata: dict[str, Any] | None = None,
) -> MonitoringTarget:
    """Create a bare :class:`MonitoringTarget` row directly."""
    target = MonitoringTarget(
        organization_id=organization_id or uuid.uuid4(),
        target_type=target_type,
        external_id=external_id or str(uuid.uuid4()),
        name=f"test-target-{uuid.uuid4().hex[:8]}",
        target_metadata=target_metadata or {},
    )
    db_session.add(target)
    await db_session.flush()
    return target


async def make_collector(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    collector_key: str = "connectivity",
    target_types: list[MonitoringTargetType] | None = None,
    parameters: dict[str, Any] | None = None,
    interval_seconds: float = 60.0,
) -> MonitoringCollector:
    """Create a bare :class:`MonitoringCollector` row directly."""
    collector = MonitoringCollector(
        organization_id=organization_id or uuid.uuid4(),
        name=f"test-collector-{uuid.uuid4().hex[:8]}",
        collector_key=collector_key,
        target_types=[str(t) for t in (target_types or [])],
        parameters=parameters or {},
        interval_seconds=interval_seconds,
    )
    db_session.add(collector)
    await db_session.flush()
    return collector


async def make_metric(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    collector_id: uuid.UUID | None = None,
    metric_type: MetricType = MetricType.LATENCY,
    name: str | None = None,
) -> MonitoringMetric:
    """Create a bare :class:`MonitoringMetric` row directly."""
    metric = MonitoringMetric(
        organization_id=organization_id or uuid.uuid4(),
        collector_id=collector_id,
        metric_type=metric_type,
        name=name or f"test-metric-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(metric)
    await db_session.flush()
    return metric


async def make_threshold(
    db_session: AsyncSession,
    metric: MonitoringMetric,
    *,
    threshold_type: ThresholdType = ThresholdType.STATIC,
    high: float | None = 100.0,
    critical: float | None = 200.0,
) -> MonitoringThreshold:
    """Create a bare :class:`MonitoringThreshold` row directly."""
    threshold = MonitoringThreshold(
        organization_id=metric.organization_id,
        metric_id=metric.id,
        threshold_type=threshold_type,
        high=high,
        critical=critical,
    )
    db_session.add(threshold)
    await db_session.flush()
    return threshold


async def make_synthetic_test(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    check_type: SyntheticCheckType = SyntheticCheckType.HTTP,
    parameters: dict[str, Any] | None = None,
    interval_seconds: float = 300.0,
) -> MonitoringSyntheticTest:
    """Create a bare :class:`MonitoringSyntheticTest` row directly."""
    test = MonitoringSyntheticTest(
        organization_id=organization_id or uuid.uuid4(),
        target_id=target_id,
        check_type=check_type,
        name=f"test-synthetic-{uuid.uuid4().hex[:8]}",
        parameters=parameters or {},
        interval_seconds=interval_seconds,
    )
    db_session.add(test)
    await db_session.flush()
    return test


def build_collector_context(
    http_client: AsyncClient,
    *,
    caller_token: str = "test-token",
) -> CollectorContext:
    """Assemble a real, fully-wired :class:`CollectorContext` pointed at
    the internal test base URLs every ``pytest-httpx`` test mocks.
    """
    return CollectorContext(
        inventory=InventoryClient(
            http_client, base_url=INVENTORY_SERVICE_BASE_URL, caller_token=caller_token
        ),
        configuration=ConfigurationClient(
            http_client, base_url=CONFIGURATION_SERVICE_BASE_URL, caller_token=caller_token
        ),
        automation=AutomationClient(
            http_client, base_url=AUTOMATION_SERVICE_BASE_URL, caller_token=caller_token
        ),
        workflow=WorkflowRuntimeClient(
            http_client, base_url=WORKFLOW_SERVICE_BASE_URL, caller_token=caller_token
        ),
        discovery=DiscoveryClient(
            http_client, base_url=DISCOVERY_SERVICE_BASE_URL, caller_token=caller_token
        ),
        validation=ValidationClient(
            http_client, base_url=VALIDATION_SERVICE_BASE_URL, caller_token=caller_token
        ),
    )


def build_collection_service(
    db_session: AsyncSession,
    *,
    context: CollectorContext,
    registry: CollectorRegistry | None = None,
    publish_event: EventPublisher | None = None,
    max_parallel_collections: int = 10,
) -> MonitoringCollectionService:
    """Assemble a real, fully-wired :class:`MonitoringCollectionService`
    bound to *db_session*.
    """

    async def _noop_publish(_event: object) -> None:
        return None

    return MonitoringCollectionService(
        MonitoringMetricRepository(db_session),
        MonitoringThresholdRepository(db_session),
        MonitoringRuleRepository(db_session),
        MonitoringMetricSeriesService(MonitoringMetricSeriesRepository(db_session)),
        _health_service(db_session),
        _availability_service(db_session),
        registry or CollectorRegistry(),
        context,
        publish_event=publish_event or _noop_publish,
        max_parallel_collections=max_parallel_collections,
    )


def _health_service(db_session: AsyncSession) -> MonitoringHealthService:
    return MonitoringHealthService(MonitoringHealthRepository(db_session))


def _availability_service(db_session: AsyncSession) -> MonitoringAvailabilityService:
    return MonitoringAvailabilityService(MonitoringAvailabilityRepository(db_session))


def build_synthetic_execution_service(
    db_session: AsyncSession,
    *,
    context: CollectorContext,
    publish_event: EventPublisher | None = None,
) -> MonitoringSyntheticExecutionService:
    """Assemble a real, fully-wired :class:`MonitoringSyntheticExecutionService`
    bound to *db_session*.
    """

    async def _noop_publish(_event: object) -> None:
        return None

    return MonitoringSyntheticExecutionService(
        _health_service(db_session),
        MonitoringMetricSeriesService(MonitoringMetricSeriesRepository(db_session)),
        MonitoringMetricService(MonitoringMetricRepository(db_session)),
        MonitoringTargetService(MonitoringTargetRepository(db_session)),
        context,
        publish_event=publish_event or _noop_publish,
    )


__all__ = [
    "AUTOMATION_SERVICE_BASE_URL",
    "CONFIGURATION_SERVICE_BASE_URL",
    "DISCOVERY_SERVICE_BASE_URL",
    "INVENTORY_SERVICE_BASE_URL",
    "VALIDATION_SERVICE_BASE_URL",
    "WORKFLOW_SERVICE_BASE_URL",
    "AuthHeadersFn",
    "app",
    "auth_headers",
    "build_collection_service",
    "build_collector_context",
    "build_synthetic_execution_service",
    "client",
    "db_session",
    "jwt_keypair",
    "make_collector",
    "make_metric",
    "make_synthetic_test",
    "make_target",
    "make_threshold",
    "pg_engine",
    "postgres_test_settings",
    "rabbitmq_test_settings",
    "real_queue_framework",
    "real_redis_client",
    "redis_test_settings",
    "token_for",
]
