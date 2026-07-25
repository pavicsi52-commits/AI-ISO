"""Shared fixtures for the inventory service's test suite.

Everything here runs against real infrastructure (the repository
root's docker-compose Postgres/Redis/RabbitMQ/MinIO/Neo4j) -- the same
discipline every prior AI-IOS service established. Postgres isolation
uses a per-test SAVEPOINT (``join_transaction_mode="create_savepoint"``),
not a second database: every ``BaseRepository`` write only ``flush()``es,
so an outer, never-committed transaction safely contains everything a
test does.

**A deliberate exception**: :class:`~app.services.import_service
.AssetImportService`/:class:`~app.services.export_service
.AssetExportService` explicitly ``commit()`` their own job row (see
that module's own docstring for why -- a queue-consumer worker on a
separate connection must see it). Tests exercising those two services'
``create_job`` directly therefore use the real, committing
``pg_engine``-backed session fixtures, not the rolled-back
``db_session`` fixture every other test uses.

**Neo4j isolation**: unlike Postgres, Neo4j has no SAVEPOINT-style
rollback available here, so ``real_neo4j_driver`` wipes every ``:Asset``
node (and every relationship touching one) both before and after each
test that requests it -- safe because this is a dedicated test/dev
instance the whole suite runs against sequentially, never a shared
production graph.

This service's own database (``aiios_inventory``) is physically
separate from every other AI-IOS service's, the same "database per
service" isolation every prior AI-IOS service's own conftest documents.
Redis test db 9 -- distinct from every other AI-IOS service's own test
db (3 authentication, 4 user-management, 5 rbac, 6 organization, 7
project, 8 secrets-management).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from minio import Minio
from neo4j import AsyncDriver
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.config.settings import (
    DatabaseSettings,
    MinioSettings,
    Neo4jSettings,
    RedisSettings,
)
from shared_core.database.engine import create_engine
from shared_core.security.jwt import encode_token
from shared_core.storage import StorageWrapper, create_minio_client
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Must be set before shared_core.config.cache.get_settings() is first called
# (a process-wide lru_cache singleton), so this whole block runs at import
# time -- ahead of app.api.deps/app.core.factory being imported below, and
# ahead of any fixture or test -- exactly like every other AIIOS_* default
# already set the same way in every prior AI-IOS service's own conftest.
os.environ.setdefault("AIIOS_DATABASE_HOST", "localhost")
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_inventory")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "9")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", "localhost")
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")
os.environ.setdefault("AIIOS_NEO4J_HOST", "localhost")
os.environ.setdefault("AIIOS_NEO4J_BOLT_PORT", "7687")
os.environ.setdefault("AIIOS_NEO4J_USER", "neo4j")
os.environ.setdefault("AIIOS_NEO4J_PASSWORD", "change-me-min-8-chars")
os.environ.setdefault("AIIOS_MINIO_HOST", "localhost")
os.environ.setdefault("AIIOS_MINIO_PORT", "9000")
os.environ.setdefault("AIIOS_MINIO_ACCESS_KEY", "aiios")
os.environ.setdefault("AIIOS_MINIO_SECRET_KEY", "change-me-min-8-chars")
os.environ.setdefault("AIIOS_MINIO_USE_SSL", "false")
os.environ.setdefault(
    "AIIOS_INVENTORY_SERVICE_IMPORT_EXPORT_BUCKET", "inventory-import-export-test"
)

# app.config.settings.get_settings() is a process-wide lru_cache singleton,
# so the JWT public key path (like every other env var above) must be fixed
# *before* anything calls it for the first time -- generating a session
# keypair inside a fixture and pointing a per-test tmp_path at it doesn't
# work, since only the first test's path would ever actually be read.
_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_inventory_test_keys"
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

os.environ.setdefault("AIIOS_INVENTORY_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.core.factory import create_app  # noqa: E402
from app.models.asset import Asset  # noqa: E402
from app.models.enums import (  # noqa: E402
    AssetStatus,
    AssetType,
    Criticality,
    HealthStatus,
    LifecycleState,
)
from app.repositories.asset import AssetRepository  # noqa: E402
from app.repositories.asset_health_history import AssetHealthHistoryRepository  # noqa: E402
from app.repositories.asset_history import AssetHistoryRepository  # noqa: E402
from app.repositories.asset_lifecycle_history import AssetLifecycleHistoryRepository  # noqa: E402
from app.repositories.asset_status_history import AssetStatusHistoryRepository  # noqa: E402
from app.repositories.asset_tag import AssetTagRepository  # noqa: E402
from app.repositories.asset_topology_cache import AssetTopologyCacheRepository  # noqa: E402
from app.repositories.asset_version import AssetVersionRepository  # noqa: E402
from app.repositories.inventory_audit import InventoryAuditRepository  # noqa: E402
from app.services.asset import AssetService, EventPublisher  # noqa: E402
from app.services.audit import InventoryAuditService  # noqa: E402
from app.services.health_history import AssetHealthHistoryService  # noqa: E402
from app.services.history import AssetHistoryService  # noqa: E402
from app.services.lifecycle_history import AssetLifecycleHistoryService  # noqa: E402
from app.services.status_history import AssetStatusHistoryService  # noqa: E402
from app.services.tag import AssetTagService  # noqa: E402
from app.services.topology import TopologyService  # noqa: E402
from app.services.version import AssetVersionService  # noqa: E402
from app.topology.client import create_neo4j_driver  # noqa: E402
from app.topology.graph import TopologyGraphClient  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios_inventory",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 9 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=9,
        _env_file=None,
    )


def minio_test_settings() -> MinioSettings:
    return MinioSettings(
        minio_host="localhost",
        minio_port=9000,
        minio_access_key="aiios",
        minio_secret_key="change-me-min-8-chars",
        minio_use_ssl=False,
        _env_file=None,
    )


def neo4j_test_settings() -> Neo4jSettings:
    return Neo4jSettings(
        neo4j_host="localhost",
        neo4j_bolt_port=7687,
        neo4j_user="neo4j",
        neo4j_password="change-me-min-8-chars",
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
    visible to independent connections -- used by the import/export
    ``create_job`` regression tests, which construct their own session
    per unit of work the same way ``app/core/factory.py``'s worker
    service builders do.
    """
    yield async_sessionmaker(bind=pg_engine, expire_on_commit=False)


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
async def minio_client() -> AsyncIterator[Minio]:
    client = create_minio_client(minio_test_settings())
    try:
        await asyncio.wait_for(asyncio.to_thread(client.list_buckets), timeout=5)
    except UNREACHABLE_ERRORS as exc:
        pytest.skip(f"MinIO is not reachable: {exc}")
    yield client


@pytest.fixture
def storage_wrapper(minio_client: Minio) -> StorageWrapper:
    return StorageWrapper(minio_client)


async def _wipe_asset_graph(driver: AsyncDriver) -> None:
    async with driver.session(database="neo4j") as session:
        await session.run("MATCH (n:Asset) DETACH DELETE n")


@pytest_asyncio.fixture
async def real_neo4j_driver() -> AsyncIterator[AsyncDriver]:
    """A real Neo4j driver, with every ``:Asset`` node wiped before and
    after the test -- see this module's own docstring for why.
    """
    driver = create_neo4j_driver(neo4j_test_settings())
    try:
        await asyncio.wait_for(driver.verify_connectivity(), timeout=5)
    except UNREACHABLE_ERRORS as exc:
        await driver.close()
        pytest.skip(f"Neo4j is not reachable: {exc}")
    await _wipe_asset_graph(driver)
    yield driver
    await _wipe_asset_graph(driver)
    await driver.close()


@pytest.fixture
def topology_graph_client(real_neo4j_driver: AsyncDriver) -> TopologyGraphClient:
    return TopologyGraphClient(real_neo4j_driver)


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


@pytest.fixture
def auth_headers(token_for: Callable[[uuid.UUID], str]) -> Callable[[uuid.UUID], dict[str, str]]:
    """Return a function building ``Authorization`` headers for a given user id."""

    def _headers(user_id: uuid.UUID) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(user_id)}"}

    return _headers


@pytest_asyncio.fixture
async def app(db_session: AsyncSession, real_neo4j_driver: AsyncDriver) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    ``get_db_session`` is overridden to hand out this test's SAVEPOINT
    session, and ``get_neo4j_driver`` to hand out this test's own
    wiped-clean driver, so every request made through ``client`` in a
    given test shares one transaction (rolled back at teardown) and one
    graph (wiped at teardown).
    """
    application = create_app()
    async with application.router.lifespan_context(application):

        async def _override_db_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        application.dependency_overrides[deps.get_db_session] = _override_db_session
        application.dependency_overrides[deps.get_neo4j_driver] = lambda: real_neo4j_driver
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def make_asset(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    name: str = "test-asset",
    hostname: str | None = None,
    asset_type: AssetType = AssetType.VIRTUAL_MACHINE,
    status: AssetStatus = AssetStatus.DISCOVERED,
    health: HealthStatus = HealthStatus.UNKNOWN,
    lifecycle_state: LifecycleState = LifecycleState.PLANNED,
    criticality: Criticality = Criticality.MEDIUM,
    location_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
) -> Asset:
    """Create a bare :class:`Asset` row directly -- for tests exercising
    code paths that don't need the full :class:`AssetService.create`
    side-effect chain (history/audit/tags/Neo4j sync).
    """
    asset = Asset(
        organization_id=organization_id or uuid.uuid4(),
        project_id=project_id,
        name=name,
        hostname=hostname,
        asset_type=asset_type,
        status=status,
        health=health,
        lifecycle_state=lifecycle_state,
        criticality=criticality,
        location_id=location_id,
        owner_id=owner_id,
        current_version=1,
    )
    db_session.add(asset)
    await db_session.flush()
    return asset


def build_asset_service(
    db_session: AsyncSession,
    graph: TopologyGraphClient,
    *,
    publish_event: EventPublisher | None = None,
) -> AssetService:
    """Assemble a real, fully-wired :class:`AssetService` bound to
    *db_session* -- the shared wiring nearly every asset-touching
    service test needs, matching ``app/core/factory.py``'s own
    ``_build_asset_service`` shape.
    """
    return AssetService(
        AssetRepository(db_session),
        AssetVersionService(AssetVersionRepository(db_session)),
        AssetTagService(AssetTagRepository(db_session)),
        AssetStatusHistoryService(AssetStatusHistoryRepository(db_session)),
        AssetHealthHistoryService(AssetHealthHistoryRepository(db_session)),
        AssetLifecycleHistoryService(AssetLifecycleHistoryRepository(db_session)),
        AssetHistoryService(AssetHistoryRepository(db_session)),
        InventoryAuditService(InventoryAuditRepository(db_session)),
        TopologyService(graph, AssetTopologyCacheRepository(db_session)),
        publish_event=publish_event,
    )


__all__ = [
    "app",
    "auth_headers",
    "build_asset_service",
    "client",
    "committing_session_factory",
    "db_session",
    "jwt_keypair",
    "make_asset",
    "minio_client",
    "minio_test_settings",
    "neo4j_test_settings",
    "pg_engine",
    "postgres_test_settings",
    "real_neo4j_driver",
    "real_redis_client",
    "redis_test_settings",
    "storage_wrapper",
    "token_for",
    "topology_graph_client",
]
