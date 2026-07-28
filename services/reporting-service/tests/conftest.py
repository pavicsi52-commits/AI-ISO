"""Shared fixtures for the reporting service's test suite.

Everything runs against real infrastructure (the repository root's
docker-compose Postgres/Redis/RabbitMQ) with per-test SAVEPOINT
isolation -- the discipline every prior AI-IOS service established.

**Data sources are the one thing not called for real.** Every platform
service this reads lives behind an ``httpx.MockTransport`` serving the
platform's own response envelope. That is deliberate: a report test
suite cannot stand up twelve other services, and what actually needs
verifying here is this service's own rendering, filtering, export, and
delivery -- all of which run for real against real Postgres. The source
*client* is separately tested against the exact envelope those services
return.

Redis test db 20 -- distinct from every other AI-IOS service's own
(... 17 monitoring, 18 alerting, 19 ai-assistant).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_reporting")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "20")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_reporting_test_keys"
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

os.environ.setdefault("AIIOS_REPORTING_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault(
    "AIIOS_REPORTING_SERVICE_INVENTORY_SERVICE_BASE_URL", "http://inventory.internal"
)
os.environ.setdefault(
    "AIIOS_REPORTING_SERVICE_MONITORING_SERVICE_BASE_URL", "http://monitoring.internal"
)
os.environ.setdefault(
    "AIIOS_REPORTING_SERVICE_ALERTING_SERVICE_BASE_URL", "http://alerting.internal"
)
os.environ.setdefault("AIIOS_REPORTING_SERVICE_AI_ASSISTANT_SERVICE_BASE_URL", "http://ai.internal")
# The scheduler polls RabbitMQ and elects a leader; a suite that started
# it would race every test against a background tick.
os.environ.setdefault("AIIOS_REPORTING_SERVICE_SCHEDULER_ENABLED", "false")

from app.api import deps  # noqa: E402  -- see the env var block above
from app.clients.platform import PlatformSourceClient, SourceEndpoints  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.enums import (  # noqa: E402
    ExportFormat,
    ReportCategory,
    ReportType,
    TemplateStatus,
)
from app.models.report_export import ReportExport  # noqa: E402
from app.models.report_job import ReportJob  # noqa: E402
from app.models.report_template import ReportTemplate  # noqa: E402
from app.renderer.engine import ReportRenderer  # noqa: E402

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

SIMPLE_DEFINITION: dict[str, Any] = {
    "title": "Fleet Report",
    "sections": [
        {"key": "intro", "kind": "text", "text": "Fleet overview."},
        {
            "key": "hosts",
            "kind": "table",
            "title": "Hosts",
            "query": {"source": "inventory", "path": "/inventory/assets"},
            "columns": [
                {"key": "name", "label": "Host"},
                {"key": "cpu", "label": "CPU %"},
            ],
        },
    ],
}
"""A minimal but genuinely renderable designer document."""


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_reporting",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 20 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=20,
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


@pytest.fixture
def token_for(jwt_keypair: tuple[str, str]) -> Callable[[uuid.UUID], str]:
    """Mint a valid access token for a given user id."""
    private_key, _public_key = jwt_keypair

    def _mint(user_id: uuid.UUID) -> str:
        return encode_token({"sub": str(user_id)}, private_key=private_key)

    return _mint


AuthHeadersFn = Callable[[uuid.UUID], dict[str, str]]


@pytest.fixture
def auth_headers(token_for: Callable[[uuid.UUID], str]) -> AuthHeadersFn:
    """Build ``Authorization`` headers for a given user id."""

    def _headers(user_id: uuid.UUID) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(user_id)}"}

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
async def renderer(stub_sources: PlatformSourceClient) -> ReportRenderer:
    """A renderer over the stubbed data sources, with AI disabled."""
    return ReportRenderer(stub_sources, None, max_parallel_sections=4)


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    The HTTP client is replaced with a stubbed transport *after*
    startup, so the real lifespan (database, cache, events,
    notifications, key loading) is genuinely exercised while data
    sources stay deterministic and offline.
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


async def make_template(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    name: str = "Fleet Report",
    definition: dict[str, Any] | None = None,
    status: TemplateStatus = TemplateStatus.APPROVED,
    version_number: str = "1.0.0",
) -> ReportTemplate:
    """Create a template row directly, approved by default."""
    template = ReportTemplate(
        organization_id=organization_id or uuid.uuid4(),
        name=name,
        description="A test template.",
        category=ReportCategory.INFRASTRUCTURE,
        report_type=ReportType.SUMMARY,
        version_number=version_number,
        status=status,
        definition=definition if definition is not None else SIMPLE_DEFINITION,
        branding={},
    )
    db_session.add(template)
    await db_session.flush()
    return template


async def make_job(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    template_id: uuid.UUID | None = None,
    name: str = "Nightly Fleet",
    default_format: ExportFormat = ExportFormat.CSV,
    parameter_values: dict[str, Any] | None = None,
    filters: list[dict[str, Any]] | None = None,
    owner_id: uuid.UUID | None = None,
) -> ReportJob:
    """Create a saved report row directly."""
    job = ReportJob(
        organization_id=organization_id or uuid.uuid4(),
        template_id=template_id,
        name=name,
        description=None,
        category=ReportCategory.INFRASTRUCTURE,
        report_type=ReportType.SUMMARY,
        default_format=default_format,
        parameter_values=parameter_values or {},
        filters=filters or [],
        owner_id=owner_id,
    )
    db_session.add(job)
    await db_session.flush()
    return job


async def make_export(
    db_session: AsyncSession,
    *,
    execution_id: uuid.UUID,
    organization_id: uuid.UUID,
    content: bytes = b"name,cpu\ndb-1,91.5\n",
    export_format: ExportFormat = ExportFormat.CSV,
) -> ReportExport:
    """Create a rendered-artifact row directly, checksum included."""
    export_record = ReportExport(
        organization_id=organization_id,
        execution_id=execution_id,
        export_format=export_format,
        filename=f"report.{export_format}",
        content_type="text/csv; charset=utf-8",
        size_bytes=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        content=content,
    )
    db_session.add(export_record)
    await db_session.flush()
    return export_record


__all__ = [
    "AI_BASE_URL",
    "ALERTING_BASE_URL",
    "INVENTORY_BASE_URL",
    "MONITORING_BASE_URL",
    "SAMPLE_ROWS",
    "SIMPLE_DEFINITION",
    "AuthHeadersFn",
    "RecordingPublisher",
    "app",
    "auth_headers",
    "client",
    "db_session",
    "db_session_factory",
    "jwt_keypair",
    "make_export",
    "make_job",
    "make_template",
    "pg_engine",
    "postgres_test_settings",
    "real_redis_client",
    "redis_test_settings",
    "renderer",
    "source_endpoints",
    "source_handler",
    "stub_sources",
    "token_for",
]
