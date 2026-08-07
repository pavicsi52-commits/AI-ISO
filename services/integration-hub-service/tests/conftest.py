"""Test fixtures for the integration hub service.

Everything runs against **real** PostgreSQL, Redis, and RabbitMQ.
Nothing here mocks infrastructure.

**Two different kinds of "reach a fake backend" exist here, and they
are not interchangeable.** ``app/security/oauth.py`` and
``app/security/credential_resolver.py`` both take an *injectable*
``httpx.AsyncClient``, so tests exercising them point that client at
:func:`fake_backend_app` through ``httpx.ASGITransport`` -- a genuine,
complete HTTP request/response cycle, never mocked. **But
``shared_core.monitoring.checks.check_http_reachable``/
``.check_tcp_reachable`` (used by ``ConnectionService``/``HealthService``)
build their own internal ``httpx.AsyncClient`` and cannot be pointed at
a test double at all** -- the same confirmed limitation
api-gateway-service's own conftest already documents. Tests for those
two services point at an already-running container from the standing
docker-compose stack (e.g. RabbitMQ's management UI) for "genuinely
reachable" and a real loopback port nothing listens on for "genuinely
unreachable".

**The one thing the HTTP tests cannot tell you.** The ``app`` fixture
overrides only the request session, so a test's writes roll back. That
override changes *transaction lifetime*, which means any behaviour whose
correctness depends on transaction lifetime is untestable through it.
``AuditService.record_failure`` commits in its own ``session_scope``
precisely so a refused request's audit entry survives the rollback of
the request that raised -- the same reasoning every prior AI-IOS
service's own conftest documents. That path is therefore exercised at
service level against the real ``db_session_factory``, never through
the ``client`` HTTP fixture.
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
from redis.exceptions import RedisError
from shared_core.security.encryption import generate_encryption_key
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from starlette.routing import Route as StarletteRoute

_LOOPBACK = "127.0.0.1"
"""IPv4, never "localhost".

Docker Desktop's IPv6 loopback does not reach the published ports, so a
name that resolves to ``::1`` first makes every connection hang until it
times out rather than failing fast.
"""

os.environ.setdefault("AIIOS_DATABASE_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_integration_hub")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "31")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_integration_hub_service_test_keys"
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
    "AIIOS_INTEGRATION_HUB_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH)
)
os.environ.setdefault("AIIOS_INTEGRATION_HUB_SERVICE_WORKERS_ENABLED", "false")
os.environ.setdefault(
    "AIIOS_INTEGRATION_HUB_SERVICE_SECRET_ENCRYPTION_KEY", generate_encryption_key()
)
"""``IntegrationHubServiceSettings.secret_encryption_key`` defaults to ``""``
-- deliberately invalid, as its own field docstring says, for local-dev
convenience only. The ``service_settings`` fixture below builds its own
valid key for direct service-layer tests, but the ``app`` fixture's real
``create_app()`` reads settings from the environment via
``get_settings()``, bypassing that fixture entirely -- so without a real
key here too, the *first* HTTP request that ever calls
``shared_core.security.encryption.encrypt``/``decrypt`` through the real
app (any ``/integrations/credentials`` route with a self-managed value)
fails with ``ValueError: AESGCM key must be 128, 192, or 256 bits.``
before ever reaching application code."""

from shared_core.cache.factory import create_cache_framework  # noqa: E402
from shared_core.cache.manager import CacheManager  # noqa: E402
from shared_core.cache.settings import CacheSettings  # noqa: E402
from shared_core.config.settings import (  # noqa: E402
    DatabaseSettings,
    RabbitMQSettings,
    RedisSettings,
)
from shared_core.connectors.credentials import CredentialType  # noqa: E402
from shared_core.database.engine import create_engine  # noqa: E402
from shared_core.security.jwt import encode_token  # noqa: E402

from app.api import deps  # noqa: E402
from app.config.settings import IntegrationHubServiceSettings  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.enums import ConnectorAuthMethod, ConnectorCategory  # noqa: E402
from app.repositories.connector import (  # noqa: E402
    ConnectorCategoryRepository,
    ConnectorRepository,
    ConnectorVersionRepository,
)
from app.repositories.credential import (  # noqa: E402
    ConnectorConnectionRepository,
    ConnectorCredentialRepository,
)
from app.repositories.event import ConnectorEventRepository  # noqa: E402
from app.repositories.flow import ConnectorFlowRepository  # noqa: E402
from app.repositories.governance import (  # noqa: E402
    ConnectorAuditRepository,
    ConnectorReportRepository,
    ConnectorStatisticRepository,
)
from app.repositories.health import ConnectorHealthRepository  # noqa: E402
from app.repositories.marketplace import ConnectorMarketplaceRepository  # noqa: E402
from app.repositories.sync import ConnectorSyncJobRepository  # noqa: E402
from app.repositories.transformation import ConnectorTransformationRepository  # noqa: E402
from app.security.credential_resolver import SecretCredentialResolver  # noqa: E402
from app.services.connection import ConnectionService  # noqa: E402
from app.services.connector import ConnectorService  # noqa: E402
from app.services.credential import CredentialService  # noqa: E402
from app.services.event import EventService  # noqa: E402
from app.services.flow import FlowService  # noqa: E402
from app.services.health import HealthService  # noqa: E402
from app.services.marketplace import MarketplaceService  # noqa: E402
from app.services.reporting import AuditService, ReportService, StatisticsService  # noqa: E402
from app.services.sync import SyncService  # noqa: E402
from app.services.transformation import TransformationService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NO_CONTENT = 204
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422

REACHABLE_HTTP_URL = f"http://{_LOOPBACK}:15672"
"""RabbitMQ's own management UI, from the standing docker-compose stack
-- always up in this environment, genuinely reachable, and the same
"point a HTTP-reachability check at a real already-running container"
precedent api-gateway-service's own conftest already established, since
``check_http_reachable`` cannot be pointed at a test double (see this
module's own docstring)."""

UNREACHABLE_HTTP_URL = f"http://{_LOOPBACK}:1"
"""A real loopback port nothing listens on -- genuinely unreachable,
fails fast rather than timing out against a firewalled remote host."""

REACHABLE_TCP_HOST, REACHABLE_TCP_PORT = _LOOPBACK, 5433
"""PostgreSQL's own published port -- always up, accepts a raw TCP connect."""

UNREACHABLE_TCP_HOST, UNREACHABLE_TCP_PORT = _LOOPBACK, 1


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_integration_hub",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 31 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=31,
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
async def cache_framework() -> AsyncIterator[Any]:
    framework = await create_cache_framework(
        CacheSettings(redis=redis_test_settings()), wait_for_ready=False
    )
    try:
        await asyncio.wait_for(framework.client.ping(), timeout=5)
    except UNREACHABLE_ERRORS as exc:
        await framework.shutdown()
        pytest.skip(f"Redis is not reachable: {exc}")
    yield framework
    await framework.shutdown()


@pytest.fixture
def cache_manager(cache_framework: Any) -> CacheManager:
    return cache_framework.manager  # type: ignore[no-any-return]


@pytest.fixture
def organization_id() -> uuid.UUID:
    """A fresh organization id per test.

    Every test works inside its own tenant, which means every test is
    also, incidentally, a tenant-isolation test: a query that forgot its
    ``organization_id`` filter would see the other tests' rows.
    """
    return uuid.uuid4()


@pytest.fixture(scope="session")
def jwt_keypair() -> tuple[str, str]:
    """The test session's fixed RSA keypair."""
    return (
        _TEST_PRIVATE_KEY_PATH.read_text(encoding="ascii"),
        _TEST_PUBLIC_KEY_PATH.read_text(encoding="ascii"),
    )


AuthHeadersFn = Callable[..., dict[str, str]]


@pytest.fixture
def auth_headers(jwt_keypair: tuple[str, str]) -> AuthHeadersFn:
    """Build ``Authorization`` headers for a given user, role, and organization."""
    private_key, _public_key = jwt_keypair

    def _headers(
        user_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
        role: str = "super_admin",
        scopes: list[str] | None = None,
    ) -> dict[str, str]:
        claims: dict[str, Any] = {"sub": str(user_id), "role": role, "scopes": scopes or []}
        if organization_id is not None:
            claims["organization_id"] = str(organization_id)
        token = encode_token(claims, private_key=private_key)
        return {"Authorization": f"Bearer {token}"}

    return _headers


class RecordingPublisher:
    """A real :data:`~app.types.EventPublisher` that records.

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
    return RecordingPublisher()


@pytest.fixture
def service_settings() -> IntegrationHubServiceSettings:
    """Test-tuned settings: a real encryption key, small timeouts, workers disabled."""
    return IntegrationHubServiceSettings(
        secret_encryption_key=generate_encryption_key(),
        secrets_service_base_url="http://secrets.example.com",
        health_check_timeout_seconds=2.0,
        sync_connect_timeout_seconds=2.0,
        sync_read_timeout_seconds=5.0,
        workers_enabled=False,
    )


KNOWN_SECRET_ID = "known-secret"
KNOWN_SECRET_VALUE = "resolved-secret-value"
MISSING_SECRET_ID = "missing-secret"

GOOD_AUTH_CODE = "good-authorization-code"
GOOD_REFRESH_TOKEN = "good-refresh-token"


async def _fake_oauth_token(request: StarletteRequest) -> JSONResponse:
    form = await request.form()
    grant_type = form.get("grant_type")
    if grant_type == "authorization_code" and form.get("code") == GOOD_AUTH_CODE:
        return JSONResponse(
            {
                "access_token": "fake-access-token",
                "refresh_token": GOOD_REFRESH_TOKEN,
                "expires_in": 3600,
                "token_type": "bearer",
            }
        )
    if grant_type == "refresh_token" and form.get("refresh_token") == GOOD_REFRESH_TOKEN:
        return JSONResponse(
            {"access_token": "refreshed-access-token", "expires_in": 3600, "token_type": "bearer"}
        )
    return JSONResponse({"error": "invalid_grant"}, status_code=400)


async def _fake_get_secret(request: StarletteRequest) -> JSONResponse:
    secret_id = request.path_params["secret_id"]
    if "authorization" not in request.headers:
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    if secret_id == MISSING_SECRET_ID:
        return JSONResponse({"detail": "not found"}, status_code=404)
    return JSONResponse({"data": {"value": KNOWN_SECRET_VALUE}})


def fake_backend_app() -> Starlette:
    """A real ASGI application standing in for both an OAuth2 provider's own
    token endpoint and the Secrets Management Service's own ``/secrets/{id}``
    route.

    Not a mock -- genuine Starlette routing and JSON responses, served
    through :class:`httpx.ASGITransport` so ``app/security/oauth.py`` and
    ``app/security/credential_resolver.py`` make a real, complete HTTP
    request/response cycle without this suite depending on any actual
    third-party endpoint.
    """
    return Starlette(
        routes=[
            StarletteRoute("/oauth/token", _fake_oauth_token, methods=["POST"]),
            StarletteRoute("/secrets/{secret_id}", _fake_get_secret, methods=["GET"]),
        ]
    )


@pytest.fixture
def http_client() -> AsyncClient:
    """An HTTP client whose every outbound request lands on :func:`fake_backend_app`."""
    return AsyncClient(
        transport=ASGITransport(app=fake_backend_app()), base_url="http://backend.example.com"
    )


# ---- repositories -----------------------------------------------------------


@pytest.fixture
def connectors_repo(db_session: AsyncSession) -> ConnectorRepository:
    return ConnectorRepository(db_session)


@pytest.fixture
def categories_repo(db_session: AsyncSession) -> ConnectorCategoryRepository:
    return ConnectorCategoryRepository(db_session)


@pytest.fixture
def versions_repo(db_session: AsyncSession) -> ConnectorVersionRepository:
    return ConnectorVersionRepository(db_session)


@pytest.fixture
def credentials_repo(db_session: AsyncSession) -> ConnectorCredentialRepository:
    return ConnectorCredentialRepository(db_session)


@pytest.fixture
def connections_repo(db_session: AsyncSession) -> ConnectorConnectionRepository:
    return ConnectorConnectionRepository(db_session)


@pytest.fixture
def sync_jobs_repo(db_session: AsyncSession) -> ConnectorSyncJobRepository:
    return ConnectorSyncJobRepository(db_session)


@pytest.fixture
def transformations_repo(db_session: AsyncSession) -> ConnectorTransformationRepository:
    return ConnectorTransformationRepository(db_session)


@pytest.fixture
def flows_repo(db_session: AsyncSession) -> ConnectorFlowRepository:
    return ConnectorFlowRepository(db_session)


@pytest.fixture
def events_repo(db_session: AsyncSession) -> ConnectorEventRepository:
    return ConnectorEventRepository(db_session)


@pytest.fixture
def health_repo(db_session: AsyncSession) -> ConnectorHealthRepository:
    return ConnectorHealthRepository(db_session)


@pytest.fixture
def marketplace_repo(db_session: AsyncSession) -> ConnectorMarketplaceRepository:
    return ConnectorMarketplaceRepository(db_session)


@pytest.fixture
def statistics_repo(db_session: AsyncSession) -> ConnectorStatisticRepository:
    return ConnectorStatisticRepository(db_session)


@pytest.fixture
def reports_repo(db_session: AsyncSession) -> ConnectorReportRepository:
    return ConnectorReportRepository(db_session)


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> ConnectorAuditRepository:
    return ConnectorAuditRepository(db_session)


# ---- services -----------------------------------------------------------


@pytest.fixture
def connector_service(
    connectors_repo: ConnectorRepository,
    versions_repo: ConnectorVersionRepository,
    categories_repo: ConnectorCategoryRepository,
) -> ConnectorService:
    return ConnectorService(connectors_repo, versions_repo, categories_repo)


@pytest.fixture
def credential_resolver(
    http_client: AsyncClient, service_settings: IntegrationHubServiceSettings
) -> SecretCredentialResolver:
    return SecretCredentialResolver(http_client, base_url=service_settings.secrets_service_base_url)


@pytest.fixture
def credential_service(
    credentials_repo: ConnectorCredentialRepository,
    service_settings: IntegrationHubServiceSettings,
    credential_resolver: SecretCredentialResolver,
) -> CredentialService:
    return CredentialService(
        credentials_repo,
        encryption_key=service_settings.secret_encryption_key,
        resolver=credential_resolver,
    )


@pytest.fixture
def connection_service(
    connections_repo: ConnectorConnectionRepository, service_settings: IntegrationHubServiceSettings
) -> ConnectionService:
    return ConnectionService(
        connections_repo, timeout_seconds=service_settings.health_check_timeout_seconds
    )


@pytest.fixture
def health_service(
    health_repo: ConnectorHealthRepository, service_settings: IntegrationHubServiceSettings
) -> HealthService:
    return HealthService(
        health_repo,
        timeout_seconds=service_settings.health_check_timeout_seconds,
        failure_threshold=service_settings.health_failure_threshold,
    )


@pytest.fixture
def transformation_service(
    transformations_repo: ConnectorTransformationRepository,
) -> TransformationService:
    return TransformationService(transformations_repo)


@pytest.fixture
def sync_service(
    sync_jobs_repo: ConnectorSyncJobRepository,
    transformation_service: TransformationService,
    publisher: RecordingPublisher,
) -> SyncService:
    return SyncService(sync_jobs_repo, transformation_service, publish_event=publisher)


@pytest.fixture
def event_service(events_repo: ConnectorEventRepository) -> EventService:
    return EventService(events_repo)


@pytest.fixture
def flow_service(
    flows_repo: ConnectorFlowRepository,
    sync_service: SyncService,
    transformation_service: TransformationService,
    event_service: EventService,
    publisher: RecordingPublisher,
) -> FlowService:
    return FlowService(
        flows_repo, sync_service, transformation_service, event_service, publish_event=publisher
    )


@pytest.fixture
def marketplace_service(
    marketplace_repo: ConnectorMarketplaceRepository, publisher: RecordingPublisher
) -> MarketplaceService:
    return MarketplaceService(marketplace_repo, publish_event=publisher)


@pytest.fixture
def statistics_service(
    statistics_repo: ConnectorStatisticRepository, sync_jobs_repo: ConnectorSyncJobRepository
) -> StatisticsService:
    return StatisticsService(statistics_repo, sync_jobs_repo)


@pytest.fixture
def report_service(
    reports_repo: ConnectorReportRepository,
    connectors_repo: ConnectorRepository,
    sync_jobs_repo: ConnectorSyncJobRepository,
    health_repo: ConnectorHealthRepository,
    audit_repo: ConnectorAuditRepository,
) -> ReportService:
    return ReportService(reports_repo, connectors_repo, sync_jobs_repo, health_repo, audit_repo)


@pytest.fixture
def audit_service(audit_repo: ConnectorAuditRepository) -> AuditService:
    return AuditService(audit_repo)


# ---- composite fixtures --------------------------------------------------


MakeConnectorFn = Callable[..., Any]


@pytest.fixture
def make_connector(
    connector_service: ConnectorService, organization_id: uuid.UUID
) -> MakeConnectorFn:
    """Register one connector."""

    async def _make(
        name: str = "test-connector",
        *,
        category: ConnectorCategory = ConnectorCategory.CUSTOM,
        connector_type: str = "rest_api",
        auth_method: ConnectorAuthMethod = ConnectorAuthMethod.API_KEY,
        **kwargs: Any,
    ) -> Any:
        return await connector_service.register(
            organization_id,
            name=name,
            category=category,
            connector_type=connector_type,
            auth_method=auth_method,
            **kwargs,
        )

    return _make


MakeCredentialFn = Callable[..., Any]


@pytest.fixture
def make_credential(
    credential_service: CredentialService, organization_id: uuid.UUID
) -> MakeCredentialFn:
    """Assign one self-managed credential to a connector."""

    async def _make(
        connector_id: uuid.UUID, *, raw_value: str = "test-secret-value", **kwargs: Any
    ) -> Any:
        return await credential_service.assign(
            organization_id,
            connector_id=connector_id,
            credential_type=CredentialType.API_KEY,
            raw_value=raw_value,
            **kwargs,
        )

    return _make


@pytest_asyncio.fixture
async def app(db_session: AsyncSession, http_client: AsyncClient) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    PostgreSQL, Redis, RabbitMQ, and key loading all run for real. The
    request session and the outbound HTTP client (so an OAuth exchange
    or a secret resolution lands on :func:`fake_backend_app` rather than
    the network) are the only two overrides -- see this module's
    docstring for the one thing the session override makes untestable
    here, and for why ``check_http_reachable``-backed routes cannot be
    exercised this way at all.
    """
    application = create_app()
    async with application.router.lifespan_context(application):

        async def _override_db_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        def _override_http_client() -> AsyncClient:
            return http_client

        application.dependency_overrides[deps.get_db_session] = _override_db_session
        application.dependency_overrides[deps.get_http_client] = _override_http_client
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def utcnow() -> datetime:
    """The current moment, timezone-aware."""
    return datetime.now(UTC)


def soon(seconds: int = 3600) -> datetime:
    """A moment *seconds* in the future."""
    return datetime.now(UTC) + timedelta(seconds=seconds)


def ago(seconds: int = 3600) -> datetime:
    """A moment *seconds* in the past."""
    return datetime.now(UTC) - timedelta(seconds=seconds)


__all__ = [
    "GOOD_AUTH_CODE",
    "GOOD_REFRESH_TOKEN",
    "HTTP_BAD_REQUEST",
    "HTTP_CONFLICT",
    "HTTP_CREATED",
    "HTTP_FORBIDDEN",
    "HTTP_NOT_FOUND",
    "HTTP_NO_CONTENT",
    "HTTP_OK",
    "HTTP_UNAUTHORIZED",
    "HTTP_UNPROCESSABLE",
    "KNOWN_SECRET_ID",
    "KNOWN_SECRET_VALUE",
    "MISSING_SECRET_ID",
    "REACHABLE_HTTP_URL",
    "REACHABLE_TCP_HOST",
    "REACHABLE_TCP_PORT",
    "UNREACHABLE_HTTP_URL",
    "UNREACHABLE_TCP_HOST",
    "UNREACHABLE_TCP_PORT",
    "ago",
    "fake_backend_app",
    "soon",
    "utcnow",
]
