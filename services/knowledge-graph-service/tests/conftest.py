"""Shared fixtures for the knowledge graph service's test suite.

Everything runs against real infrastructure: PostgreSQL with per-test
SAVEPOINT isolation, and **a real Neo4j**. That last part is a
departure from ``services/dashboard-service``, which stubbed the driver
-- and it is the right call here, because this service's whole subject
is Cypher. A stub cannot tell you that a write submitted through a read
transaction is refused, which is the guarantee the most dangerous
endpoint rests on.

**Neo4j has no SAVEPOINT equivalent**, so graph isolation is by
*organization id*: every test gets a fresh UUID and the fixture purges
that organization afterwards. Tests therefore never see each other's
nodes even though they share one database, and a failed test cannot
leave rows that break the next one.

Redis test db 22 -- distinct from every other AI-IOS service's own
(... 20 reporting, 21 dashboard).
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

import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from neo4j import AsyncDriver
from redis.exceptions import RedisError
from shared_core.config.settings import DatabaseSettings, Neo4jSettings, RedisSettings
from shared_core.database.engine import create_engine
from shared_core.security.jwt import encode_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_LOOPBACK = "127.0.0.1"
"""The IPv4 literal, never the name ``localhost``.

On Windows ``localhost`` resolves to ``::1`` first, and Docker
Desktop's IPv6 forwarding hangs rather than refusing, so every
connection burns its full timeout instead of falling back. Diagnosed
during Prompt 045.
"""

os.environ.setdefault("AIIOS_DATABASE_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_knowledge_graph")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "22")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")
os.environ.setdefault("AIIOS_NEO4J_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_NEO4J_BOLT_PORT", "7687")
os.environ.setdefault("AIIOS_NEO4J_USER", "neo4j")
os.environ.setdefault("AIIOS_NEO4J_PASSWORD", "change-me-min-8-chars")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_knowledge_graph_test_keys"
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
    "AIIOS_KNOWLEDGE_GRAPH_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH)
)
os.environ.setdefault(
    "AIIOS_KNOWLEDGE_GRAPH_SERVICE_INVENTORY_SERVICE_BASE_URL", "http://inventory.internal"
)
# The scheduler polls RabbitMQ and elects a leader; a suite that started
# it would race every test against a background rollup tick.
os.environ.setdefault("AIIOS_KNOWLEDGE_GRAPH_SERVICE_SCHEDULER_ENABLED", "false")
os.environ.setdefault("AIIOS_KNOWLEDGE_GRAPH_SERVICE_SYNC_SERVICE_TOKEN", "test-service-token")

from app.api import deps  # noqa: E402  -- see the env var block above
from app.clients.platform import PlatformSourceClient, SourceEndpoints  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.graph.client import GraphClient, create_neo4j_driver  # noqa: E402
from app.graph.entities import NodeInput, RelationshipInput  # noqa: E402
from app.graph.repository import GraphRepository  # noqa: E402
from app.graph.schema import apply_schema  # noqa: E402
from app.models.enums import NodeType, RelationshipType  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

HTTP_OK = 200

INVENTORY_BASE_URL = "http://inventory.internal"


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_knowledge_graph",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 22 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=22,
        _env_file=None,
    )


def neo4j_test_settings() -> Neo4jSettings:
    return Neo4jSettings(
        neo4j_host=_LOOPBACK,
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


_SCHEMA_APPLIED = False
"""Whether the graph schema has been applied in this process.

A module-level flag rather than a session-scoped fixture, because the
driver below has to be **function**-scoped: this suite runs on
pytest-asyncio's default function-scoped event loop, and an
``AsyncDriver`` built on one loop and used from another fails with
``NoneType object has no attribute send`` -- an error that names nothing
useful. Building the driver per test is cheap (it connects lazily); the
schema is the expensive part, so that is what gets cached.
"""


@pytest_asyncio.fixture
async def neo4j_driver() -> AsyncIterator[AsyncDriver]:
    """A Neo4j driver bound to this test's event loop.

    Function-scoped deliberately -- see :data:`_SCHEMA_APPLIED`.
    """
    driver = create_neo4j_driver(neo4j_test_settings())
    if driver is None:
        pytest.skip("Neo4j could not be configured.")
    try:
        await asyncio.wait_for(driver.verify_connectivity(), timeout=10)
    except Exception as exc:
        await driver.close()
        pytest.skip(f"Neo4j is not reachable: {exc}")
    yield driver
    await driver.close()


@pytest_asyncio.fixture
async def graph_schema(neo4j_driver: AsyncDriver) -> None:
    """Apply the graph schema, once per process.

    Every statement is ``IF NOT EXISTS``, so re-running is harmless --
    but index creation is the slowest thing in this suite, and doing it
    per test would dominate the runtime.
    """
    global _SCHEMA_APPLIED
    if not _SCHEMA_APPLIED:
        await apply_schema(GraphClient(neo4j_driver))
        _SCHEMA_APPLIED = True


@pytest.fixture
def organization_id() -> uuid.UUID:
    """A fresh organization id per test.

    This is the graph's isolation mechanism. Neo4j has no SAVEPOINT, so
    every test works inside its own tenant and the graph fixture purges
    it afterwards -- which also exercises the tenant scoping that every
    query in this service depends on.
    """
    return uuid.uuid4()


@pytest_asyncio.fixture
async def graph_client(neo4j_driver: AsyncDriver, graph_schema: None) -> AsyncIterator[GraphClient]:
    """A graph client bound to the session driver."""
    del graph_schema
    yield GraphClient(neo4j_driver, database="neo4j", max_records=5_000)


@pytest_asyncio.fixture
async def graph(
    graph_client: GraphClient, organization_id: uuid.UUID
) -> AsyncIterator[GraphRepository]:
    """A graph repository whose organization is purged afterwards."""
    repository = GraphRepository(graph_client, max_depth=6, max_nodes=5_000)
    yield repository
    await repository.purge_organization(organization_id)


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
    publish path executes for real and tests can assert exactly which
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


SAMPLE_ASSETS: list[dict[str, Any]] = [
    {
        "id": "host-1",
        "name": "host-1",
        "asset_type": "physical_server",
        "environment": "prod",
        "updated_at": "2026-07-01T10:00:00Z",
    },
    {
        "id": "vm-1",
        "name": "vm-1",
        "asset_type": "virtual_machine",
        "host_id": "host-1",
        "environment": "prod",
        "updated_at": "2026-07-02T10:00:00Z",
    },
    {
        "id": "db-1",
        "name": "billing-db",
        "asset_type": "database",
        "host_id": "vm-1",
        "environment": "prod",
        "updated_at": "2026-07-03T10:00:00Z",
    },
]
"""Rows the stubbed inventory source returns.

Deliberately a chain -- database on VM on host -- so dependency,
impact, and blast-radius traversals all have something with real depth
to walk.
"""


def source_handler(
    rows: list[dict[str, Any]] | None = None, *, status_code: int = HTTP_OK
) -> Callable[[httpx.Request], httpx.Response]:
    """Build a ``MockTransport`` handler serving the platform envelope.

    Returns the rows on the first page and nothing after, so the sync
    engine's paging loop terminates rather than reading the same page
    two hundred times.
    """
    payload = SAMPLE_ASSETS if rows is None else rows

    def _handle(request: httpx.Request) -> httpx.Response:
        if status_code != HTTP_OK:
            return httpx.Response(status_code, json={"error": "unavailable"})
        offset = int(request.url.params.get("offset", 0))
        page = payload if offset == 0 else []
        return httpx.Response(HTTP_OK, json={"success": True, "data": page})

    return _handle


@pytest.fixture
def source_endpoints() -> SourceEndpoints:
    """Every sync source pointed at one stub host."""
    return SourceEndpoints(
        inventory=INVENTORY_BASE_URL,
        discovery=INVENTORY_BASE_URL,
        configuration=INVENTORY_BASE_URL,
        automation=INVENTORY_BASE_URL,
        workflow=INVENTORY_BASE_URL,
        validation=INVENTORY_BASE_URL,
        monitoring=INVENTORY_BASE_URL,
        alerting=INVENTORY_BASE_URL,
        reporting=INVENTORY_BASE_URL,
        administration=INVENTORY_BASE_URL,
    )


@pytest_asyncio.fixture
async def stub_sources(
    source_endpoints: SourceEndpoints,
) -> AsyncIterator[PlatformSourceClient]:
    """A source client whose transport serves :data:`SAMPLE_ASSETS`."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(source_handler())) as client:
        yield PlatformSourceClient(client, source_endpoints, service_token="test-token")


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    The outbound HTTP client is replaced after startup so sync sources
    stay deterministic, but PostgreSQL, Redis, RabbitMQ, Neo4j, the
    graph schema, and key loading all run for real.
    """
    application = create_app()
    async with application.router.lifespan_context(application):

        async def _override_db_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        application.dependency_overrides[deps.get_db_session] = _override_db_session
        await application.state.http_client.aclose()
        application.state.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(source_handler())
        )
        yield application
        await application.state.http_client.aclose()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seeded_graph(graph: GraphRepository, organization_id: uuid.UUID) -> GraphRepository:
    """A small but genuinely shaped graph: app -> vm -> host, app -> db.

    Not a line: the branch is what makes shortest-path, blast-radius
    scoring, and betweenness produce answers that differ from a trivial
    chain, so a bug in any of them shows up rather than being masked.
    """
    await graph.upsert_nodes(
        organization_id,
        [
            NodeInput(key="app-1", node_type=NodeType.APPLICATION, name="Billing"),
            NodeInput(key="vm-1", node_type=NodeType.VIRTUAL_MACHINE, name="vm-1"),
            NodeInput(key="vm-2", node_type=NodeType.VIRTUAL_MACHINE, name="vm-2"),
            NodeInput(key="db-1", node_type=NodeType.DATABASE, name="billing-db"),
            NodeInput(key="host-1", node_type=NodeType.PHYSICAL_SERVER, name="host-1"),
        ],
        source="test",
    )
    await graph.upsert_relationships(
        organization_id,
        [
            RelationshipInput(
                from_key="app-1", to_key="vm-1", relationship_type=RelationshipType.RUNS_ON
            ),
            RelationshipInput(
                from_key="app-1", to_key="db-1", relationship_type=RelationshipType.DEPENDS_ON
            ),
            RelationshipInput(
                from_key="vm-1", to_key="host-1", relationship_type=RelationshipType.RUNS_ON
            ),
            RelationshipInput(
                from_key="db-1", to_key="vm-2", relationship_type=RelationshipType.RUNS_ON
            ),
            RelationshipInput(
                from_key="vm-2", to_key="host-1", relationship_type=RelationshipType.RUNS_ON
            ),
        ],
    )
    return graph


def utcnow() -> datetime:
    """The current moment, timezone-aware."""
    return datetime.now(UTC)


__all__ = [
    "HTTP_OK",
    "INVENTORY_BASE_URL",
    "SAMPLE_ASSETS",
    "AuthHeadersFn",
    "RecordingPublisher",
    "app",
    "auth_headers",
    "client",
    "db_session",
    "db_session_factory",
    "graph",
    "graph_client",
    "jwt_keypair",
    "neo4j_driver",
    "neo4j_test_settings",
    "organization_id",
    "pg_engine",
    "postgres_test_settings",
    "publisher",
    "redis_test_settings",
    "seeded_graph",
    "source_endpoints",
    "source_handler",
    "stub_sources",
    "utcnow",
]
