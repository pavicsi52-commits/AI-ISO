"""Shared fixtures for the discovery service's test suite.

Real infrastructure wherever genuinely feasible in this environment,
matching every prior AI-IOS service's own discipline: the repository
root's docker-compose Postgres/Redis/RabbitMQ, plus two dedicated
containers this package's own test suite starts for protocols with no
docker-compose equivalent (a real OpenSSH server on port 2222, a real
Eclipse Mosquitto broker on port 11883). Where no real or realistically
local target exists at all (WinRM, Redfish, IPMI, SMB, gRPC -- see each
scanner's own module docstring), tests use mocking to exercise the real
request-building/parsing/error-handling logic instead of claiming live
verification that didn't happen.

Postgres isolation uses a per-test SAVEPOINT
(``join_transaction_mode="create_savepoint"``), the same pattern every
prior AI-IOS service established. Redis test db 10 -- distinct from
every other AI-IOS service's own test db (3 authentication, 4
user-management, 5 rbac, 6 organization, 7 project, 8
secrets-management, 9 inventory).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.config.settings import DatabaseSettings, RedisSettings
from shared_core.database.engine import create_engine
from shared_core.enums.job_status import JobStatus
from shared_core.events.base import DomainEvent
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_discovery")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "10")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", "localhost")
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_discovery_test_keys"
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

os.environ.setdefault("AIIOS_DISCOVERY_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.core.factory import create_app  # noqa: E402
from app.discovery.credentials import CredentialResolver  # noqa: E402
from app.discovery.inventory_sync import InventorySyncClient  # noqa: E402
from app.models.discovery_asset import DiscoveryAsset  # noqa: E402
from app.models.discovery_job import DiscoveryJob  # noqa: E402
from app.models.discovery_profile import DiscoveryProfile  # noqa: E402
from app.models.discovery_result import DiscoveryResult  # noqa: E402
from app.models.discovery_target import DiscoveryTarget  # noqa: E402
from app.models.enums import (  # noqa: E402
    AssetClassification,
    DiscoveryMode,
    DiscoveryResultStatus,
    ProfileType,
    ProtocolType,
    TargetType,
)
from app.repositories.discovery_asset import DiscoveryAssetRepository  # noqa: E402
from app.repositories.discovery_audit import DiscoveryAuditRepository  # noqa: E402
from app.repositories.discovery_classification import (  # noqa: E402
    DiscoveryClassificationRepository,
)
from app.repositories.discovery_credential import DiscoveryCredentialRepository  # noqa: E402
from app.repositories.discovery_failure import DiscoveryFailureRepository  # noqa: E402
from app.repositories.discovery_history import DiscoveryHistoryRepository  # noqa: E402
from app.repositories.discovery_job import DiscoveryJobRepository  # noqa: E402
from app.repositories.discovery_profile import DiscoveryProfileRepository  # noqa: E402
from app.repositories.discovery_relationship import DiscoveryRelationshipRepository  # noqa: E402
from app.repositories.discovery_result import DiscoveryResultRepository  # noqa: E402
from app.repositories.discovery_rule import DiscoveryRuleRepository  # noqa: E402
from app.repositories.discovery_target import DiscoveryTargetRepository  # noqa: E402
from app.services.asset import DiscoveryAssetService  # noqa: E402
from app.services.audit import DiscoveryAuditService  # noqa: E402
from app.services.classification import DiscoveryClassificationService  # noqa: E402
from app.services.credential import DiscoveryCredentialService  # noqa: E402
from app.services.discovery_execution import DiscoveryExecutionService  # noqa: E402
from app.services.failure import DiscoveryFailureService  # noqa: E402
from app.services.history import DiscoveryHistoryService  # noqa: E402
from app.services.job import DiscoveryJobService  # noqa: E402
from app.services.relationship import DiscoveryRelationshipService  # noqa: E402
from app.services.result import DiscoveryResultService  # noqa: E402
from app.services.rule import DiscoveryRuleService  # noqa: E402
from app.services.target import DiscoveryTargetService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

SECRETS_SERVICE_BASE_URL = "http://localhost:8006"
INVENTORY_SERVICE_BASE_URL = "http://localhost:8007"

# The real containers this package's own test suite starts (see this
# module's own docstring) -- not part of the repository root
# docker-compose stack, since no other AI-IOS service needs them.
SSH_TEST_HOST = "localhost"
SSH_TEST_PORT = 2222
SSH_TEST_USERNAME = "testuser"
SSH_TEST_PASSWORD = "testpass123"

MQTT_TEST_HOST = "localhost"
MQTT_TEST_PORT = 11883


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios_discovery",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 10 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=10,
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
async def committing_session_factory(
    pg_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A real, non-SAVEPOINT session factory whose commits are durably
    visible to independent connections.
    """
    yield async_sessionmaker(bind=pg_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def real_http_client() -> AsyncIterator[AsyncClient]:
    """A real, unmocked :class:`httpx.AsyncClient` -- matches
    ``app/core/factory.py``'s own process-wide ``app.state.http_client``.
    """
    async with AsyncClient(timeout=10.0) as client:
        yield client


EventPublisher = Callable[[DomainEvent], Awaitable[None]]


def build_execution_service(
    session: AsyncSession,
    http_client: AsyncClient,
    *,
    publish_event: EventPublisher | None = None,
) -> DiscoveryExecutionService:
    """Assemble a real, fully-wired :class:`DiscoveryExecutionService`
    bound to *session* -- matches ``app/core/factory.py``'s own private
    ``_build_execution_service`` shape (duplicated here, not imported,
    the same "public test-helper mirrors a private factory helper"
    precedent ``services/inventory-service``'s own conftest.py
    ``build_asset_service`` established).
    """
    credential_resolver = CredentialResolver(http_client, base_url=SECRETS_SERVICE_BASE_URL)
    inventory_sync = InventorySyncClient(http_client, base_url=INVENTORY_SERVICE_BASE_URL)
    return DiscoveryExecutionService(
        DiscoveryJobService(
            DiscoveryJobRepository(session),
            DiscoveryTargetRepository(session),
            session,
            publish_event=publish_event,
        ),
        DiscoveryTargetService(DiscoveryTargetRepository(session)),
        DiscoveryCredentialService(DiscoveryCredentialRepository(session)),
        DiscoveryResultService(DiscoveryResultRepository(session)),
        DiscoveryAssetService(
            DiscoveryAssetRepository(session), inventory_sync, publish_event=publish_event
        ),
        DiscoveryRelationshipService(
            DiscoveryRelationshipRepository(session), inventory_sync, publish_event=publish_event
        ),
        DiscoveryFailureService(DiscoveryFailureRepository(session)),
        DiscoveryHistoryService(DiscoveryHistoryRepository(session)),
        DiscoveryAuditService(DiscoveryAuditRepository(session)),
        credential_resolver,
        DiscoveryRuleService(DiscoveryRuleRepository(session)),
        DiscoveryClassificationService(DiscoveryClassificationRepository(session)),
        publish_event=publish_event,
    )


async def seed_profile(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    name: str | None = None,
) -> DiscoveryProfile:
    """Insert a real :class:`DiscoveryProfile` row -- ``discovery_targets
    .profile_id``/``discovery_jobs.profile_id``/``discovery_schedules
    .profile_id`` all have a real foreign key to ``discovery_profiles.id``.
    """
    profile = await DiscoveryProfileRepository(session).create(
        DiscoveryProfile(
            organization_id=organization_id,
            name=name or f"seeded-profile-{uuid.uuid4()}",
            profile_type=ProfileType.CUSTOM,
            protocols=[],
        )
    )
    await session.flush()
    return profile


async def seed_job(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    profile_id: uuid.UUID | None = None,
) -> DiscoveryJob:
    """Insert a real :class:`DiscoveryJob` row -- ``discovery_history``/
    ``discovery_failures``/``discovery_results``/``discovery_assets``/
    ``discovery_audit`` all have a real foreign key to ``discovery_jobs
    .id``, so any test exercising those tables needs one to actually
    exist first, not just a random UUID.
    """
    job = await DiscoveryJobRepository(session).create(
        DiscoveryJob(
            organization_id=organization_id,
            profile_id=profile_id,
            mode=DiscoveryMode.MANUAL,
            status=JobStatus.QUEUED,
        )
    )
    await session.flush()
    return job


async def seed_target(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    profile_id: uuid.UUID | None = None,
    address: str = "192.0.2.1",
    protocol: ProtocolType = ProtocolType.TCP,
) -> DiscoveryTarget:
    """Insert a real :class:`DiscoveryTarget` row -- ``discovery_results``
    has a real foreign key to ``discovery_targets.id``.
    """
    target = await DiscoveryTargetRepository(session).create(
        DiscoveryTarget(
            organization_id=organization_id,
            profile_id=profile_id,
            target_type=TargetType.HOST,
            address=address,
            protocol=protocol,
        )
    )
    await session.flush()
    return target


async def seed_result(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    target_id: uuid.UUID,
    status: DiscoveryResultStatus = DiscoveryResultStatus.SUCCESS,
) -> DiscoveryResult:
    """Insert a real :class:`DiscoveryResult` row -- ``discovery_assets``
    has a real foreign key to ``discovery_results.id``.
    """
    result = await DiscoveryResultRepository(session).create(
        DiscoveryResult(
            organization_id=organization_id,
            job_id=job_id,
            target_id=target_id,
            protocol=ProtocolType.TCP,
            status=status,
            latency_ms=1.0,
            raw_data={},
            executed_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return result


async def seed_asset(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    result_id: uuid.UUID,
    name: str = "seeded-asset",
    classification: AssetClassification = AssetClassification.CUSTOM,
) -> DiscoveryAsset:
    """Insert a real :class:`DiscoveryAsset` row -- ``discovery_relationships``
    and ``discovery_classifications`` both have real foreign keys onto
    ``discovery_assets.id``.
    """
    asset = await DiscoveryAssetRepository(session).create(
        DiscoveryAsset(
            organization_id=organization_id,
            job_id=job_id,
            result_id=result_id,
            name=name,
            asset_type="unknown",
            classification=classification,
            fingerprint={},
        )
    )
    await session.flush()
    return asset


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


@pytest.fixture(scope="session")
def jwt_keypair() -> tuple[str, str]:
    return (
        _TEST_PRIVATE_KEY_PATH.read_text(encoding="ascii"),
        _TEST_PUBLIC_KEY_PATH.read_text(encoding="ascii"),
    )


@pytest.fixture
def token_for(jwt_keypair: tuple[str, str]) -> Callable[[uuid.UUID], str]:
    private_key, _public_key = jwt_keypair

    def _mint(user_id: uuid.UUID) -> str:
        return encode_token({"sub": str(user_id)}, private_key=private_key)

    return _mint


@pytest.fixture
def auth_headers(token_for: Callable[[uuid.UUID], str]) -> Callable[[uuid.UUID], dict[str, str]]:
    def _headers(user_id: uuid.UUID) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(user_id)}"}

    return _headers


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    ``get_db_session`` is overridden to hand out this test's SAVEPOINT
    session, so every request made through ``client`` in a given test
    shares one transaction that is rolled back at teardown.
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


__all__ = [
    "INVENTORY_SERVICE_BASE_URL",
    "MQTT_TEST_HOST",
    "MQTT_TEST_PORT",
    "SECRETS_SERVICE_BASE_URL",
    "SSH_TEST_HOST",
    "SSH_TEST_PASSWORD",
    "SSH_TEST_PORT",
    "SSH_TEST_USERNAME",
    "app",
    "auth_headers",
    "build_execution_service",
    "client",
    "committing_session_factory",
    "db_session",
    "jwt_keypair",
    "pg_engine",
    "postgres_test_settings",
    "real_http_client",
    "real_redis_client",
    "redis_test_settings",
    "seed_asset",
    "seed_job",
    "seed_profile",
    "seed_result",
    "seed_target",
    "token_for",
]
