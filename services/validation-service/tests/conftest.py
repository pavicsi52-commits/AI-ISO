"""Shared fixtures for the validation service's test suite.

Everything here runs against real infrastructure (the repository
root's docker-compose Postgres/Redis/RabbitMQ) -- the same discipline
every prior AI-IOS service established. Postgres isolation uses a
per-test SAVEPOINT (``join_transaction_mode="create_savepoint"``), not
a second database: every ``BaseRepository`` write only ``flush()``es,
so an outer, never-committed transaction safely contains everything a
test does.

No Neo4j fixture exists here -- docs/043 names no graph concept for
this service.

**Collector testing**: real network collectors
(:mod:`app.collectors.network`) are exercised against genuine local
TCP/TLS state where practical; every cross-service collector
(:mod:`app.collectors.remote`/:mod:`app.collectors.service_state`) is
tested via ``pytest-httpx`` against Inventory/Configuration
Management/Automation/Workflow Runtime/Discovery's own real documented
response shapes, never a live account, the same precedent
``services/workflow-runtime-service``'s own cross-service tests
established.

This service's own database (``aiios_validation``) is physically
separate from every other AI-IOS service's. Redis test db 16 --
distinct from every other AI-IOS service's own test db (3
authentication, 4 user-management, 5 rbac, 6 organization, 7 project, 8
secrets-management, 9 inventory, 10 discovery, 11 asset-management, 12
configuration-management, 13 automation, 14 playbook, 15
workflow-runtime).
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_validation")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "16")
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
_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_validation_test_keys"
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

os.environ.setdefault("AIIOS_VALIDATION_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault(
    "AIIOS_VALIDATION_SERVICE_INVENTORY_SERVICE_BASE_URL", "http://inventory.internal"
)
os.environ.setdefault(
    "AIIOS_VALIDATION_SERVICE_CONFIGURATION_SERVICE_BASE_URL", "http://configuration.internal"
)
os.environ.setdefault(
    "AIIOS_VALIDATION_SERVICE_AUTOMATION_SERVICE_BASE_URL", "http://automation.internal"
)
os.environ.setdefault(
    "AIIOS_VALIDATION_SERVICE_WORKFLOW_RUNTIME_SERVICE_BASE_URL", "http://workflow.internal"
)
os.environ.setdefault(
    "AIIOS_VALIDATION_SERVICE_DISCOVERY_SERVICE_BASE_URL", "http://discovery.internal"
)

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.collectors.registry import CollectorRegistry  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.enums import (  # noqa: E402
    ValidationCheckType,
    ValidationConcurrencyStrategy,
    ValidationExecutionStatus,
    ValidationProfileType,
    ValidationTargetType,
    ValidationTriggerType,
)
from app.models.validation_check import ValidationCheck  # noqa: E402
from app.models.validation_execution import ValidationExecution  # noqa: E402
from app.models.validation_profile import ValidationProfile  # noqa: E402
from app.models.validation_rule import ValidationRule  # noqa: E402
from app.models.validation_target import ValidationTarget  # noqa: E402
from app.repositories.validation_category import ValidationCategoryRepository  # noqa: E402
from app.repositories.validation_check import ValidationCheckRepository  # noqa: E402
from app.repositories.validation_execution import ValidationExecutionRepository  # noqa: E402
from app.repositories.validation_failure import ValidationFailureRepository  # noqa: E402
from app.repositories.validation_history import ValidationHistoryRepository  # noqa: E402
from app.repositories.validation_profile import ValidationProfileRepository  # noqa: E402
from app.repositories.validation_result import ValidationResultRepository  # noqa: E402
from app.repositories.validation_result_detail import (  # noqa: E402
    ValidationResultDetailRepository,
)
from app.repositories.validation_rule import ValidationRuleRepository  # noqa: E402
from app.repositories.validation_score import ValidationScoreRepository  # noqa: E402
from app.repositories.validation_target import ValidationTargetRepository  # noqa: E402
from app.services.execution import EventPublisher, ValidationExecutionService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

INVENTORY_SERVICE_BASE_URL = "http://inventory.internal"
CONFIGURATION_SERVICE_BASE_URL = "http://configuration.internal"
AUTOMATION_SERVICE_BASE_URL = "http://automation.internal"
WORKFLOW_SERVICE_BASE_URL = "http://workflow.internal"
DISCOVERY_SERVICE_BASE_URL = "http://discovery.internal"


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios_validation",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 16 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=16,
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
async def db_session(pg_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """One SAVEPOINT-isolated session per test, always rolled back."""
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        session_factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with session_factory() as session:
            yield session
        await trans.rollback()


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
    """A real :class:`~shared_core.queue.factory.QueueFramework`, backing
    :func:`~app.workers.execution_worker.build_execution_worker`'s own
    queue-producer-shaped tests -- no in-memory fake.
    """
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


async def make_check(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    check_type: ValidationCheckType = ValidationCheckType.CONNECTIVITY,
    collector_key: str = "connectivity",
    parameters: dict[str, Any] | None = None,
    category_id: uuid.UUID | None = None,
) -> ValidationCheck:
    """Create a bare :class:`ValidationCheck` row directly."""
    check = ValidationCheck(
        organization_id=organization_id or uuid.uuid4(),
        category_id=category_id,
        check_type=check_type,
        name=f"test-check-{uuid.uuid4().hex[:8]}",
        collector_key=collector_key,
        parameters=parameters or {},
    )
    db_session.add(check)
    await db_session.flush()
    return check


async def make_rule(
    db_session: AsyncSession,
    check: ValidationCheck,
    *,
    condition: str = "reachable == false",
    priority: int = 0,
) -> ValidationRule:
    """Create a bare :class:`ValidationRule` row directly."""
    rule = ValidationRule(
        organization_id=check.organization_id,
        check_id=check.id,
        name=f"test-rule-{uuid.uuid4().hex[:8]}",
        condition=condition,
        priority=priority,
    )
    db_session.add(rule)
    await db_session.flush()
    return rule


async def make_profile(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    check_ids: list[uuid.UUID] | None = None,
    concurrency_strategy: ValidationConcurrencyStrategy = ValidationConcurrencyStrategy.SEQUENTIAL,
) -> ValidationProfile:
    """Create a bare :class:`ValidationProfile` row directly."""
    profile = ValidationProfile(
        organization_id=organization_id or uuid.uuid4(),
        name=f"test-profile-{uuid.uuid4().hex[:8]}",
        profile_type=ValidationProfileType.INFRASTRUCTURE,
        check_ids=[str(check_id) for check_id in (check_ids or [])],
        concurrency_strategy=str(concurrency_strategy),
        current_version_number="1.0.0",
    )
    db_session.add(profile)
    await db_session.flush()
    return profile


async def make_target(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    target_type: ValidationTargetType = ValidationTargetType.PHYSICAL_SERVER,
    external_id: str | None = None,
    target_metadata: dict[str, Any] | None = None,
) -> ValidationTarget:
    """Create a bare :class:`ValidationTarget` row directly."""
    target = ValidationTarget(
        organization_id=organization_id or uuid.uuid4(),
        target_type=target_type,
        external_id=external_id or str(uuid.uuid4()),
        name=f"test-target-{uuid.uuid4().hex[:8]}",
        target_metadata=target_metadata or {},
    )
    db_session.add(target)
    await db_session.flush()
    return target


async def make_execution(
    db_session: AsyncSession,
    profile: ValidationProfile,
    targets: list[ValidationTarget],
    *,
    concurrency_strategy: ValidationConcurrencyStrategy = ValidationConcurrencyStrategy.SEQUENTIAL,
    trigger_type: ValidationTriggerType = ValidationTriggerType.MANUAL,
    status: ValidationExecutionStatus = ValidationExecutionStatus.QUEUED,
) -> ValidationExecution:
    """Create a bare :class:`ValidationExecution` row directly."""
    execution = ValidationExecution(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        target_ids=[str(target.id) for target in targets],
        concurrency_strategy=concurrency_strategy,
        trigger_type=trigger_type,
        status=status,
    )
    db_session.add(execution)
    await db_session.flush()
    return execution


def build_execution_service(
    db_session: AsyncSession,
    *,
    http_client: AsyncClient,
    collectors: CollectorRegistry | None = None,
    publish_event: EventPublisher | None = None,
    max_parallel_checks: int = 10,
) -> ValidationExecutionService:
    """Assemble a real, fully-wired :class:`ValidationExecutionService`
    bound to *db_session* -- the shared wiring nearly every
    execution-touching service test needs, matching ``app/core
    /factory.py``'s own dependency-graph shape.
    """

    async def _noop_publish(_event: object) -> None:
        return None

    return ValidationExecutionService(
        ValidationExecutionRepository(db_session),
        ValidationProfileRepository(db_session),
        ValidationCheckRepository(db_session),
        ValidationCategoryRepository(db_session),
        ValidationRuleRepository(db_session),
        ValidationTargetRepository(db_session),
        ValidationResultRepository(db_session),
        ValidationResultDetailRepository(db_session),
        ValidationFailureRepository(db_session),
        ValidationScoreRepository(db_session),
        ValidationHistoryRepository(db_session),
        http_client,
        collectors or CollectorRegistry(),
        inventory_base_url=INVENTORY_SERVICE_BASE_URL,
        configuration_base_url=CONFIGURATION_SERVICE_BASE_URL,
        automation_base_url=AUTOMATION_SERVICE_BASE_URL,
        workflow_base_url=WORKFLOW_SERVICE_BASE_URL,
        discovery_base_url=DISCOVERY_SERVICE_BASE_URL,
        publish_event=publish_event or _noop_publish,
        max_parallel_checks=max_parallel_checks,
    )


__all__ = [
    "AUTOMATION_SERVICE_BASE_URL",
    "CONFIGURATION_SERVICE_BASE_URL",
    "DISCOVERY_SERVICE_BASE_URL",
    "INVENTORY_SERVICE_BASE_URL",
    "WORKFLOW_SERVICE_BASE_URL",
    "AuthHeadersFn",
    "app",
    "auth_headers",
    "build_execution_service",
    "client",
    "db_session",
    "jwt_keypair",
    "make_check",
    "make_execution",
    "make_profile",
    "make_rule",
    "make_target",
    "pg_engine",
    "postgres_test_settings",
    "rabbitmq_test_settings",
    "real_queue_framework",
    "real_redis_client",
    "redis_test_settings",
    "token_for",
]
