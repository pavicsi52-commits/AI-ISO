"""Shared fixtures for the asset management service's test suite.

Everything here runs against real infrastructure (the repository
root's docker-compose Postgres/Redis/RabbitMQ/Neo4j) -- the same
discipline every prior AI-IOS service established. Postgres isolation
uses a per-test SAVEPOINT (``join_transaction_mode="create_savepoint"``),
not a second database: every ``BaseRepository`` write only ``flush()``es,
so an outer, never-committed transaction safely contains everything a
test does.

**Neo4j isolation**: this service is a read-only consumer of the graph
``services/inventory-service`` populates (per docs/038's own framing:
"Inventory identifies assets. Asset Management manages assets."), so
unlike that service's own conftest (which wipes real ``:Asset`` nodes
via its own write-capable ``TopologyGraphClient``), this suite seeds a
disposable graph directly with raw Cypher (``seed_dependency_graph``)
standing in for what that service would have already written --
wiped before and after each test that requests it, safe for the same
reason (a dedicated test/dev instance, never a shared production graph).

**Inventory Service calls**: :class:`~app.assets.inventory_client
.InventoryClient` talks to ``services/inventory-service``'s own REST
API. Rather than running that service as a live process, its
responses are mocked with ``pytest-httpx``, the same "no second live
service in the test loop" precedent ``services/discovery-service``'s
own ``InventorySyncClient`` tests established.

This service's own database (``aiios_asset_management``) is physically
separate from every other AI-IOS service's. Redis test db 11 --
distinct from every other AI-IOS service's own test db (3
authentication, 4 user-management, 5 rbac, 6 organization, 7 project,
8 secrets-management, 9 inventory, 10 discovery).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from neo4j import AsyncDriver
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.config.settings import DatabaseSettings, Neo4jSettings, RedisSettings
from shared_core.database.engine import create_engine
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_asset_management")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "11")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", "localhost")
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")
os.environ.setdefault("AIIOS_NEO4J_HOST", "localhost")
os.environ.setdefault("AIIOS_NEO4J_BOLT_PORT", "7687")
os.environ.setdefault("AIIOS_NEO4J_USER", "neo4j")
os.environ.setdefault("AIIOS_NEO4J_PASSWORD", "change-me-min-8-chars")

# app.config.settings.get_settings() is a process-wide lru_cache singleton,
# so the JWT public key path (like every other env var above) must be fixed
# *before* anything calls it for the first time -- generating a session
# keypair inside a fixture and pointing a per-test tmp_path at it doesn't
# work, since only the first test's path would ever actually be read.
_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_asset_management_test_keys"
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
    "AIIOS_ASSET_MANAGEMENT_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH)
)
os.environ.setdefault(
    "AIIOS_ASSET_MANAGEMENT_SERVICE_INVENTORY_SERVICE_BASE_URL", "http://inventory.internal"
)

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.core.factory import create_app  # noqa: E402
from app.dependencies.client import create_neo4j_driver  # noqa: E402
from app.dependencies.graph_client import DependencyGraphClient  # noqa: E402
from app.models.enums import (  # noqa: E402
    Criticality,
    LifecycleState,
    ManagedAssetStatus,
)
from app.models.managed_asset import ManagedAsset  # noqa: E402
from app.repositories.asset_audit import AssetAuditRepository  # noqa: E402
from app.repositories.asset_change_history import AssetChangeHistoryRepository  # noqa: E402
from app.repositories.asset_retirement import AssetRetirementRepository  # noqa: E402
from app.repositories.managed_asset import ManagedAssetRepository  # noqa: E402
from app.services.audit import AssetAuditService  # noqa: E402
from app.services.lifecycle import LifecycleService  # noqa: E402
from app.services.managed_asset import EventPublisher, ManagedAssetService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

INVENTORY_SERVICE_BASE_URL = "http://inventory.internal"


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios_asset_management",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 11 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=11,
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
def dependency_graph_client(real_neo4j_driver: AsyncDriver) -> DependencyGraphClient:
    return DependencyGraphClient(real_neo4j_driver)


async def seed_dependency_graph(
    driver: AsyncDriver, edges: list[tuple[uuid.UUID, str, uuid.UUID]]
) -> None:
    """Seed disposable ``:Asset`` nodes and relationships directly with
    raw Cypher, standing in for what ``services/inventory-service``'s
    own write-capable topology client would have already populated --
    this service's own :class:`DependencyGraphClient` is read-only, so
    it has no such write method of its own to reuse here.
    """
    async with driver.session(database="neo4j") as session:
        for source_id, relationship_type, target_id in edges:
            await session.run(
                "MERGE (a:Asset {id: $source_id}) SET a.name = $source_id, "
                "a.asset_type = 'server' "
                "MERGE (b:Asset {id: $target_id}) SET b.name = $target_id, "
                "b.asset_type = 'server' "
                f"MERGE (a)-[:{relationship_type}]->(b)",
                source_id=str(source_id),
                target_id=str(target_id),
            )


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


async def make_managed_asset(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    inventory_asset_id: uuid.UUID | None = None,
    business_name: str = "test-managed-asset",
    status: ManagedAssetStatus = ManagedAssetStatus.PLANNED,
    lifecycle_state: LifecycleState = LifecycleState.PROVISIONING,
    criticality: Criticality = Criticality.MEDIUM,
) -> ManagedAsset:
    """Create a bare :class:`ManagedAsset` row directly -- for tests
    exercising code paths that don't need the full
    :class:`ManagedAssetService.create` side-effect chain (history/audit/events).
    """
    managed_asset = ManagedAsset(
        organization_id=organization_id or uuid.uuid4(),
        inventory_asset_id=inventory_asset_id or uuid.uuid4(),
        business_name=business_name,
        status=status,
        lifecycle_state=lifecycle_state,
        criticality=criticality,
    )
    db_session.add(managed_asset)
    await db_session.flush()
    return managed_asset


def build_lifecycle_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> LifecycleService:
    return LifecycleService(
        ManagedAssetRepository(db_session),
        AssetChangeHistoryRepository(db_session),
        AssetRetirementRepository(db_session),
        publish_event=publish_event,
    )


def build_managed_asset_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> ManagedAssetService:
    """Assemble a real, fully-wired :class:`ManagedAssetService` bound
    to *db_session* -- the shared wiring nearly every managed-asset-
    touching service test needs, matching ``app/core/factory.py``'s
    own dependency-graph shape.
    """
    return ManagedAssetService(
        ManagedAssetRepository(db_session),
        build_lifecycle_service(db_session, publish_event=publish_event),
        AssetAuditService(AssetAuditRepository(db_session)),
        publish_event=publish_event,
    )


def utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "INVENTORY_SERVICE_BASE_URL",
    "AuthHeadersFn",
    "app",
    "auth_headers",
    "build_lifecycle_service",
    "build_managed_asset_service",
    "client",
    "db_session",
    "dependency_graph_client",
    "jwt_keypair",
    "make_managed_asset",
    "neo4j_test_settings",
    "pg_engine",
    "postgres_test_settings",
    "real_neo4j_driver",
    "real_redis_client",
    "redis_test_settings",
    "seed_dependency_graph",
    "token_for",
    "utcnow",
]
