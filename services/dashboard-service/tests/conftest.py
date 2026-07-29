"""Shared fixtures for the dashboard service's test suite.

Everything runs against real infrastructure (the repository root's
docker-compose Postgres/Redis/RabbitMQ) with per-test SAVEPOINT
isolation -- the discipline every prior AI-IOS service established.

**Data sources are the one thing not called for real.** Every platform
service this reads lives behind an ``httpx.MockTransport`` serving the
platform's own response envelope. A dashboard test suite cannot stand
up twelve other services, and what actually needs verifying here is
this service's own resolving, filtering, layout, sharing, and streaming
-- all of which run for real against real Postgres.

**Neo4j is stubbed, not skipped.** The topology reader is driven
through a fake async driver that yields the exact record shape Neo4j
returns for the module's own Cypher, so the query construction, depth
validation, and de-duplication are all genuinely exercised.

Redis test db 21 -- distinct from every other AI-IOS service's own
(... 18 alerting, 19 ai-assistant, 20 reporting).
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
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.config.settings import DatabaseSettings, RedisSettings
from shared_core.database.engine import create_engine
from shared_core.security.jwt import encode_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_LOOPBACK = "127.0.0.1"
"""The IPv4 literal, never the name ``localhost``.

On Windows ``localhost`` resolves to ``::1`` first, and Docker
Desktop's IPv6 forwarding hangs rather than refusing, so every
connection burns its full timeout instead of falling back. Diagnosed
and fixed during Prompt 045; see that service's own README.
"""

os.environ.setdefault("AIIOS_DATABASE_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_dashboard")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "21")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_dashboard_test_keys"
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

os.environ.setdefault("AIIOS_DASHBOARD_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault(
    "AIIOS_DASHBOARD_SERVICE_INVENTORY_SERVICE_BASE_URL", "http://inventory.internal"
)
os.environ.setdefault(
    "AIIOS_DASHBOARD_SERVICE_MONITORING_SERVICE_BASE_URL", "http://monitoring.internal"
)
os.environ.setdefault(
    "AIIOS_DASHBOARD_SERVICE_ALERTING_SERVICE_BASE_URL", "http://alerting.internal"
)
os.environ.setdefault("AIIOS_DASHBOARD_SERVICE_AI_ASSISTANT_SERVICE_BASE_URL", "http://ai.internal")
# The scheduler polls RabbitMQ and elects a leader; a suite that started
# it would race every test against a background rollup tick.
os.environ.setdefault("AIIOS_DASHBOARD_SERVICE_SCHEDULER_ENABLED", "false")
# The refresh loop would publish frames underneath tests asserting on
# exactly what a subscriber received. It is exercised directly instead,
# by calling its own ``tick()``.
os.environ.setdefault("AIIOS_DASHBOARD_SERVICE_REFRESH_WORKER_ENABLED", "false")
# No Neo4j in the test environment; topology is driven through a fake
# driver so the Cypher and graph assembly are still genuinely covered.
os.environ.setdefault("AIIOS_DASHBOARD_SERVICE_TOPOLOGY_ENABLED", "false")

from app.api import deps  # noqa: E402  -- see the env var block above
from app.clients.platform import PlatformSourceClient, SourceEndpoints  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.dashboard import Dashboard  # noqa: E402
from app.models.dashboard_widget import DashboardWidget  # noqa: E402
from app.models.enums import (  # noqa: E402
    DashboardType,
    DashboardVisibility,
    DataSource,
    RefreshMode,
    WidgetType,
)
from app.widgets.resolver import WidgetResolver  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

HTTP_OK = 200

INVENTORY_BASE_URL = "http://inventory.internal"
MONITORING_BASE_URL = "http://monitoring.internal"
ALERTING_BASE_URL = "http://alerting.internal"
AI_BASE_URL = "http://ai.internal"

SAMPLE_ROWS: list[dict[str, Any]] = [
    {"name": "db-1", "env": "prod", "cpu": 91.5, "seen": "2026-07-20T10:00:00Z"},
    {"name": "db-2", "env": "dev", "cpu": 12.0, "seen": "2026-07-27T10:00:00Z"},
    {"name": "web-1", "env": "prod", "cpu": 55.0, "seen": "2026-07-25T10:00:00Z"},
    {"name": "web-2", "env": "prod", "cpu": 61.0, "seen": "2026-07-26T10:00:00Z"},
]
"""Rows every stubbed data source returns.

Deliberately mixed: two environments, a wide CPU spread, and ISO
timestamps, so filters, aggregates, and chart grouping all have
something real to act on.
"""

TABLE_WIDGET: dict[str, Any] = {
    "widget_key": "hosts",
    "title": "Hosts",
    "widget_type": "table",
    "query": {"source": "inventory", "path": "/inventory/assets"},
    "options": {
        "columns": [
            {"key": "name", "label": "Host"},
            {"key": "cpu", "label": "CPU %"},
        ]
    },
}
"""A minimal but genuinely renderable widget definition."""

METRIC_WIDGET: dict[str, Any] = {
    "widget_key": "host_count",
    "title": "Hosts",
    "widget_type": "metric_card",
    "query": {"source": "inventory", "path": "/inventory/assets"},
    "options": {"metric": {"aggregate": "count"}},
}

CHART_WIDGET: dict[str, Any] = {
    "widget_key": "cpu_by_env",
    "title": "CPU by environment",
    "widget_type": "bar_chart",
    "query": {"source": "monitoring", "path": "/monitoring/metrics"},
    "options": {"series": {"label_key": "env", "value_key": "cpu", "aggregate": "avg"}},
}


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_dashboard",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 21 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=21,
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
    """The test session's fixed RSA keypair."""
    return (
        _TEST_PRIVATE_KEY_PATH.read_text(encoding="ascii"),
        _TEST_PUBLIC_KEY_PATH.read_text(encoding="ascii"),
    )


TokenFn = Callable[..., str]


@pytest.fixture
def token_for(jwt_keypair: tuple[str, str]) -> TokenFn:
    """Mint a valid access token for a given user id, with optional roles."""
    private_key, _public_key = jwt_keypair

    def _mint(user_id: uuid.UUID, *, roles: list[str] | None = None) -> str:
        claims: dict[str, Any] = {"sub": str(user_id)}
        if roles is not None:
            claims["roles"] = roles
        return encode_token(claims, private_key=private_key)

    return _mint


AuthHeadersFn = Callable[..., dict[str, str]]


@pytest.fixture
def auth_headers(token_for: TokenFn) -> AuthHeadersFn:
    """Build ``Authorization`` headers for a given user id."""

    def _headers(user_id: uuid.UUID, *, roles: list[str] | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(user_id, roles=roles)}"}

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


def source_handler(
    rows: list[dict[str, Any]] | None = None, *, status_code: int = HTTP_OK
) -> Callable[[httpx.Request], httpx.Response]:
    """Build a ``MockTransport`` handler serving the platform envelope."""
    payload = SAMPLE_ROWS if rows is None else rows

    def _handle(_request: httpx.Request) -> httpx.Response:
        if status_code != HTTP_OK:
            return httpx.Response(status_code, json={"error": "unavailable"})
        return httpx.Response(HTTP_OK, json={"success": True, "data": payload})

    return _handle


@pytest.fixture
def source_endpoints() -> SourceEndpoints:
    """Every data source pointed at one stub host."""
    return SourceEndpoints(
        inventory=INVENTORY_BASE_URL,
        discovery=INVENTORY_BASE_URL,
        configuration=INVENTORY_BASE_URL,
        automation=INVENTORY_BASE_URL,
        workflow=INVENTORY_BASE_URL,
        validation=INVENTORY_BASE_URL,
        monitoring=MONITORING_BASE_URL,
        alerting=ALERTING_BASE_URL,
        reporting=INVENTORY_BASE_URL,
        ai_assistant=AI_BASE_URL,
        compliance=INVENTORY_BASE_URL,
        incident=INVENTORY_BASE_URL,
        administration=INVENTORY_BASE_URL,
    )


@pytest_asyncio.fixture
async def stub_sources(
    source_endpoints: SourceEndpoints,
) -> AsyncIterator[PlatformSourceClient]:
    """A source client whose transport serves :data:`SAMPLE_ROWS`."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(source_handler())) as client:
        yield PlatformSourceClient(client, source_endpoints, caller_token="test-token")


@pytest_asyncio.fixture
async def resolver(stub_sources: PlatformSourceClient) -> WidgetResolver:
    """A resolver over the stubbed data sources, topology and AI off."""
    return WidgetResolver(stub_sources, None, None, max_parallel=4)


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    The HTTP client is replaced with a stubbed transport *after*
    startup, so the real lifespan (database, cache, events,
    notifications, hub, broadcaster, key loading) is genuinely
    exercised while data sources stay deterministic and offline.
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


async def make_dashboard(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    slug: str = "fleet",
    name: str = "Fleet",
    dashboard_type: DashboardType = DashboardType.INFRASTRUCTURE,
    visibility: DashboardVisibility = DashboardVisibility.PRIVATE,
    default_filters: list[dict[str, Any]] | None = None,
    refresh_seconds: int = 0,
) -> Dashboard:
    """Create a dashboard row directly."""
    dashboard = Dashboard(
        organization_id=organization_id or uuid.uuid4(),
        slug=slug,
        name=name,
        description="A test dashboard.",
        dashboard_type=dashboard_type,
        visibility=visibility,
        owner_id=owner_id,
        default_filters=default_filters or [],
        refresh_seconds=refresh_seconds,
    )
    db_session.add(dashboard)
    await db_session.flush()
    return dashboard


async def make_widget(
    db_session: AsyncSession,
    *,
    dashboard: Dashboard,
    widget_key: str = "hosts",
    title: str = "Hosts",
    widget_type: WidgetType = WidgetType.TABLE,
    data_source: DataSource = DataSource.INVENTORY,
    query: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    filters: list[dict[str, Any]] | None = None,
    refresh_mode: RefreshMode = RefreshMode.POLLING,
    enabled: bool = True,
) -> DashboardWidget:
    """Create a widget row directly."""
    widget = DashboardWidget(
        organization_id=dashboard.organization_id,
        project_id=dashboard.project_id,
        dashboard_id=dashboard.id,
        widget_key=widget_key,
        title=title,
        widget_type=widget_type,
        data_source=data_source,
        query=query or {"source": "inventory", "path": "/inventory/assets"},
        options=options
        or {"columns": [{"key": "name", "label": "Host"}, {"key": "cpu", "label": "CPU %"}]},
        filters=filters or [],
        refresh_mode=refresh_mode,
        enabled=enabled,
    )
    db_session.add(widget)
    await db_session.flush()
    return widget


class FakeResult:
    """An async-iterable stand-in for a Neo4j result cursor."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        async def _iterate() -> AsyncIterator[dict[str, Any]]:
            for record in self._records:
                yield record

        return _iterate()


class FakeSession:
    """A stand-in for a Neo4j async session that records its query."""

    def __init__(self, driver: FakeDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def run(self, cypher: str, **parameters: Any) -> FakeResult:
        self._driver.queries.append((cypher, parameters))
        if self._driver.error is not None:
            raise self._driver.error
        return FakeResult(self._driver.records)


class FakeDriver:
    """A minimal Neo4j async driver, enough to exercise real Cypher.

    Not a mock object: it records the exact query and parameters the
    topology module built, which is what lets a test assert that node
    ids are genuinely parameterised rather than interpolated.
    """

    def __init__(
        self, records: list[dict[str, Any]] | None = None, *, error: Exception | None = None
    ) -> None:
        self.records = records or []
        self.error = error
        self.queries: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def session(self, **_kwargs: Any) -> FakeSession:
        return FakeSession(self)

    async def close(self) -> None:
        self.closed = True

    async def verify_connectivity(self) -> None:
        if self.error is not None:
            raise self.error


def topology_records(count: int = 2) -> list[dict[str, Any]]:
    """Records shaped exactly as this service's own Cypher returns them."""
    return [
        {
            "root_id": "asset-1",
            "other_id": f"asset-{index + 2}",
            "other_labels": ["Host"],
            "other_name": f"host-{index + 2}",
            "other_props": {"env": "prod"},
            "rel_source": "asset-1",
            "rel_target": f"asset-{index + 2}",
            "rel_type": "DEPENDS_ON",
        }
        for index in range(count)
    ]


def utcnow() -> datetime:
    """The current moment, timezone-aware."""
    return datetime.now(UTC)


__all__ = [
    "AI_BASE_URL",
    "ALERTING_BASE_URL",
    "CHART_WIDGET",
    "HTTP_OK",
    "INVENTORY_BASE_URL",
    "METRIC_WIDGET",
    "MONITORING_BASE_URL",
    "SAMPLE_ROWS",
    "TABLE_WIDGET",
    "AuthHeadersFn",
    "FakeDriver",
    "FakeResult",
    "FakeSession",
    "RecordingPublisher",
    "TokenFn",
    "app",
    "auth_headers",
    "client",
    "db_session",
    "db_session_factory",
    "jwt_keypair",
    "make_dashboard",
    "make_widget",
    "pg_engine",
    "postgres_test_settings",
    "publisher",
    "real_redis_client",
    "redis_test_settings",
    "resolver",
    "source_endpoints",
    "source_handler",
    "stub_sources",
    "token_for",
    "topology_records",
    "utcnow",
]
