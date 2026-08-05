"""Test fixtures for the API gateway service.

Everything runs against **real** PostgreSQL, Redis, and RabbitMQ. Nothing
here mocks infrastructure. The one deliberate substitution is the
*backend* a proxied request lands on: :func:`fake_backend_app` is a real
Starlette application served through :class:`httpx.ASGITransport` --
genuine ASGI request/response handling, not a mock -- so
:class:`~app.services.proxy.ProxyService` makes a real HTTP call end to
end without this test suite depending on an actual third-party service
being reachable.

**The one thing the HTTP tests cannot tell you.** The ``app`` fixture
overrides only the request session, so a test's writes roll back. That
override changes *transaction lifetime*, which means any behaviour whose
correctness depends on transaction lifetime is untestable through it.
``AuditService.record_failure`` commits in its own ``session_scope``
precisely so a refused request's audit entry survives the rollback of
the request that raised -- the same reasoning every prior AI-IOS
service's own conftest documents. That path is therefore exercised at
service level against the real session factory, never over HTTP.

Where a test's isolation differs from production's, the test is only
trustworthy about things that isolation does not touch.
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_api_gateway")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "29")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_api_gateway_test_keys"
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

os.environ.setdefault("AIIOS_GATEWAY_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault("AIIOS_GATEWAY_SERVICE_WORKERS_ENABLED", "false")

from shared_core.cache.factory import create_cache_framework  # noqa: E402
from shared_core.cache.manager import CacheManager  # noqa: E402
from shared_core.cache.settings import CacheSettings  # noqa: E402
from shared_core.config.settings import (  # noqa: E402
    DatabaseSettings,
    RabbitMQSettings,
    RedisSettings,
)
from shared_core.connectors.retry import CircuitBreaker  # noqa: E402
from shared_core.database.engine import create_engine  # noqa: E402
from shared_core.security.jwt import encode_token  # noqa: E402

from app.api import deps  # noqa: E402
from app.config.settings import GatewayServiceSettings  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.enums import (  # noqa: E402
    ClientKind,
    LoadBalancingStrategy,
    QuotaPeriod,
    RouteMatchKind,
)
from app.repositories.apikey import ApiKeyPermissionRepository, ApiKeyRepository  # noqa: E402
from app.repositories.client import ApiClientRepository  # noqa: E402
from app.repositories.governance import (  # noqa: E402
    ApiAuditRepository,
    ApiReportRepository,
    ApiStatisticRepository,
)
from app.repositories.health import ApiServiceHealthRepository  # noqa: E402
from app.repositories.quota import ApiQuotaPolicyRepository  # noqa: E402
from app.repositories.ratelimit import ApiRateLimitPolicyRepository  # noqa: E402
from app.repositories.request import ApiRequestLogRepository, ApiResponseLogRepository  # noqa: E402
from app.repositories.route import ApiRouteRepository  # noqa: E402
from app.repositories.service import ApiServiceRepository  # noqa: E402
from app.repositories.transformation import ApiTransformationRuleRepository  # noqa: E402
from app.repositories.version import ApiVersionRepository  # noqa: E402
from app.services.apikey import ApiKeyService  # noqa: E402
from app.services.auth import AuthService  # noqa: E402
from app.services.client import ClientService  # noqa: E402
from app.services.health import HealthMonitorService  # noqa: E402
from app.services.proxy import ProxyService  # noqa: E402
from app.services.quota import QuotaService  # noqa: E402
from app.services.ratelimit import RateLimitService  # noqa: E402
from app.services.reporting import AuditService, ReportService, StatisticsService  # noqa: E402
from app.services.route import RouteService  # noqa: E402
from app.services.service import ServiceRegistryService  # noqa: E402
from app.services.transformation import TransformationService  # noqa: E402
from app.services.version import VersionService  # noqa: E402

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
HTTP_TOO_MANY_REQUESTS = 429

FAKE_BACKEND_URL = "http://backend.test"
"""The instance URL every ``make_service`` fixture points at by default."""


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_api_gateway",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 29 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=29,
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
def service_settings() -> GatewayServiceSettings:
    """Test-tuned settings: small thresholds/timeouts, so a probe/breaker test doesn't sleep for real."""
    return GatewayServiceSettings(
        circuit_breaker_failure_threshold=2,
        circuit_breaker_recovery_seconds=0.05,
        health_probe_timeout_seconds=2.0,
        upstream_connect_timeout_seconds=2.0,
        upstream_read_timeout_seconds=5.0,
        workers_enabled=False,
    )


@pytest.fixture
def breakers() -> dict[str, CircuitBreaker]:
    """One process-wide-equivalent breaker dict, shared by every `HealthMonitorService` a test builds."""
    return {}


async def _fake_echo(request: StarletteRequest) -> JSONResponse:
    body = await request.body()
    return JSONResponse(
        {
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "headers": dict(request.headers),
            "body": body.decode("utf-8", errors="replace"),
        }
    )


async def _fake_health(_request: StarletteRequest) -> JSONResponse:
    return JSONResponse({"status": "healthy"})


async def _fake_error(_request: StarletteRequest) -> JSONResponse:
    return JSONResponse({"detail": "backend failure"}, status_code=500)


def fake_backend_app() -> Starlette:
    """A real ASGI application standing in for an external backend.

    Not a mock -- genuine Starlette routing and JSON responses, served
    through :class:`httpx.ASGITransport` so :class:`~app.services.proxy
    .ProxyService` makes a real, complete HTTP request/response cycle
    without this suite depending on any actual third-party service.
    """
    return Starlette(
        routes=[
            StarletteRoute("/echo", _fake_echo, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
            StarletteRoute("/echo/{rest:path}", _fake_echo, methods=["GET", "POST"]),
            StarletteRoute("/health", _fake_health, methods=["GET"]),
            StarletteRoute("/error", _fake_error, methods=["GET"]),
        ]
    )


@pytest.fixture
def http_client() -> AsyncClient:
    """An HTTP client whose every outbound request lands on :func:`fake_backend_app`."""
    return AsyncClient(transport=ASGITransport(app=fake_backend_app()))


# ---- repositories -----------------------------------------------------------


@pytest.fixture
def services_repo(db_session: AsyncSession) -> ApiServiceRepository:
    return ApiServiceRepository(db_session)


@pytest.fixture
def versions_repo(db_session: AsyncSession) -> ApiVersionRepository:
    return ApiVersionRepository(db_session)


@pytest.fixture
def routes_repo(db_session: AsyncSession) -> ApiRouteRepository:
    return ApiRouteRepository(db_session)


@pytest.fixture
def clients_repo(db_session: AsyncSession) -> ApiClientRepository:
    return ApiClientRepository(db_session)


@pytest.fixture
def api_keys_repo(db_session: AsyncSession) -> ApiKeyRepository:
    return ApiKeyRepository(db_session)


@pytest.fixture
def api_key_permissions_repo(db_session: AsyncSession) -> ApiKeyPermissionRepository:
    return ApiKeyPermissionRepository(db_session)


@pytest.fixture
def rate_limits_repo(db_session: AsyncSession) -> ApiRateLimitPolicyRepository:
    return ApiRateLimitPolicyRepository(db_session)


@pytest.fixture
def quotas_repo(db_session: AsyncSession) -> ApiQuotaPolicyRepository:
    return ApiQuotaPolicyRepository(db_session)


@pytest.fixture
def transformations_repo(db_session: AsyncSession) -> ApiTransformationRuleRepository:
    return ApiTransformationRuleRepository(db_session)


@pytest.fixture
def health_repo(db_session: AsyncSession) -> ApiServiceHealthRepository:
    return ApiServiceHealthRepository(db_session)


@pytest.fixture
def request_logs_repo(db_session: AsyncSession) -> ApiRequestLogRepository:
    return ApiRequestLogRepository(db_session)


@pytest.fixture
def response_logs_repo(db_session: AsyncSession) -> ApiResponseLogRepository:
    return ApiResponseLogRepository(db_session)


@pytest.fixture
def statistics_repo(db_session: AsyncSession) -> ApiStatisticRepository:
    return ApiStatisticRepository(db_session)


@pytest.fixture
def reports_repo(db_session: AsyncSession) -> ApiReportRepository:
    return ApiReportRepository(db_session)


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> ApiAuditRepository:
    return ApiAuditRepository(db_session)


# ---- services -----------------------------------------------------------


@pytest.fixture
def service_registry_service(services_repo: ApiServiceRepository) -> ServiceRegistryService:
    return ServiceRegistryService(services_repo)


@pytest.fixture
def version_service(versions_repo: ApiVersionRepository) -> VersionService:
    return VersionService(versions_repo)


@pytest.fixture
def route_service(routes_repo: ApiRouteRepository) -> RouteService:
    return RouteService(routes_repo)


@pytest.fixture
def client_service(clients_repo: ApiClientRepository) -> ClientService:
    return ClientService(clients_repo)


@pytest.fixture
def api_key_service(api_keys_repo: ApiKeyRepository) -> ApiKeyService:
    return ApiKeyService(api_keys_repo)


@pytest.fixture
def rate_limit_service(
    rate_limits_repo: ApiRateLimitPolicyRepository, cache_manager: CacheManager
) -> RateLimitService:
    return RateLimitService(rate_limits_repo, cache_manager)


@pytest.fixture
def quota_service(quotas_repo: ApiQuotaPolicyRepository) -> QuotaService:
    return QuotaService(quotas_repo)


@pytest.fixture
def transformation_service(
    transformations_repo: ApiTransformationRuleRepository,
) -> TransformationService:
    return TransformationService(transformations_repo)


@pytest.fixture
def health_monitor_service(
    health_repo: ApiServiceHealthRepository,
    service_settings: GatewayServiceSettings,
    breakers: dict[str, CircuitBreaker],
) -> HealthMonitorService:
    return HealthMonitorService(
        health_repo,
        failure_threshold=service_settings.circuit_breaker_failure_threshold,
        recovery_seconds=service_settings.circuit_breaker_recovery_seconds,
        probe_timeout_seconds=service_settings.health_probe_timeout_seconds,
        breakers=breakers,
    )


@pytest.fixture
def auth_service(api_key_service: ApiKeyService, jwt_keypair: tuple[str, str]) -> AuthService:
    _private_key, public_key = jwt_keypair
    return AuthService(api_keys=api_key_service, jwt_public_key=public_key)


@pytest.fixture
def statistics_service(
    statistics_repo: ApiStatisticRepository,
    request_logs_repo: ApiRequestLogRepository,
    response_logs_repo: ApiResponseLogRepository,
) -> StatisticsService:
    return StatisticsService(statistics_repo, request_logs_repo, response_logs_repo)


@pytest.fixture
def report_service(
    reports_repo: ApiReportRepository,
    request_logs_repo: ApiRequestLogRepository,
    response_logs_repo: ApiResponseLogRepository,
    audit_repo: ApiAuditRepository,
) -> ReportService:
    return ReportService(reports_repo, request_logs_repo, response_logs_repo, audit_repo)


@pytest.fixture
def audit_service(audit_repo: ApiAuditRepository) -> AuditService:
    return AuditService(audit_repo)


@pytest.fixture
def proxy_service(
    http_client: AsyncClient,
    route_service: RouteService,
    service_registry_service: ServiceRegistryService,
    rate_limit_service: RateLimitService,
    quota_service: QuotaService,
    health_monitor_service: HealthMonitorService,
    transformation_service: TransformationService,
    request_logs_repo: ApiRequestLogRepository,
    response_logs_repo: ApiResponseLogRepository,
    publisher: RecordingPublisher,
) -> ProxyService:
    return ProxyService(
        http_client=http_client,
        routes=route_service,
        services=service_registry_service,
        rate_limits=rate_limit_service,
        quotas=quota_service,
        health=health_monitor_service,
        transformations=transformation_service,
        request_logs=request_logs_repo,
        response_logs=response_logs_repo,
        round_robin_counters={},
        sticky_maps={},
        publish_event=publisher,
    )


# ---- composite fixtures --------------------------------------------------


MakeServiceFn = Callable[..., Any]


@pytest.fixture
def make_service(
    service_registry_service: ServiceRegistryService, organization_id: uuid.UUID
) -> MakeServiceFn:
    """Register one backend service, its own single instance pointed at the fake backend."""

    async def _make(
        name: str = "orders-service",
        *,
        instance_url: str = FAKE_BACKEND_URL,
        load_balancing_strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN,
        **kwargs: Any,
    ) -> Any:
        return await service_registry_service.register(
            organization_id,
            name=name,
            instances=[{"url": instance_url, "weight": 100}],
            load_balancing_strategy=load_balancing_strategy,
            **kwargs,
        )

    return _make


MakeRouteFn = Callable[..., Any]


@pytest.fixture
def make_route(route_service: RouteService, organization_id: uuid.UUID) -> MakeRouteFn:
    """Register one route for a given service."""

    async def _make(
        service_id: uuid.UUID,
        *,
        name: str = "test-route",
        path_pattern: str = "/echo",
        match_kind: RouteMatchKind = RouteMatchKind.PATH,
        methods: list[str] | None = None,
        requires_auth: bool = False,
        **kwargs: Any,
    ) -> Any:
        return await route_service.create(
            organization_id,
            service_id=service_id,
            name=name,
            path_pattern=path_pattern,
            match_kind=match_kind,
            methods=methods or ["get", "post"],
            requires_auth=requires_auth,
            **kwargs,
        )

    return _make


MakeClientFn = Callable[..., Any]


@pytest.fixture
def make_client(client_service: ClientService, organization_id: uuid.UUID) -> MakeClientFn:
    """Register one API client."""

    async def _make(
        name: str = "test-client", *, client_kind: ClientKind = ClientKind.THIRD_PARTY, **kwargs: Any
    ) -> Any:
        return await client_service.register(organization_id, name=name, client_kind=client_kind, **kwargs)

    return _make


MakeApiKeyFn = Callable[..., Any]


@pytest.fixture
def make_api_key(
    api_key_service: ApiKeyService, make_client: MakeClientFn, organization_id: uuid.UUID
) -> MakeApiKeyFn:
    """Register one client and issue it an API key; returns ``(raw_key, ApiKey)``."""

    async def _make(*, name: str = "test-key", scopes: list[str] | None = None, **kwargs: Any) -> Any:
        client = await make_client()
        return await api_key_service.create(
            organization_id, client_id=client.id, name=name, scopes=scopes or [], **kwargs
        )

    return _make


MakeRateLimitPolicyFn = Callable[..., Any]


@pytest.fixture
def make_rate_limit_policy(
    rate_limit_service: RateLimitService, organization_id: uuid.UUID
) -> MakeRateLimitPolicyFn:
    async def _make(
        *, scope: Any, scope_reference: str | None = None, max_requests: int = 5, window_seconds: int = 60, **kwargs: Any
    ) -> Any:
        return await rate_limit_service.set_policy(
            organization_id,
            scope=scope,
            scope_reference=scope_reference,
            max_requests=max_requests,
            window_seconds=window_seconds,
            **kwargs,
        )

    return _make


MakeQuotaPolicyFn = Callable[..., Any]


@pytest.fixture
def make_quota_policy(quota_service: QuotaService, organization_id: uuid.UUID) -> MakeQuotaPolicyFn:
    async def _make(
        *,
        scope: Any,
        kind: Any,
        scope_reference: str | None = None,
        period: QuotaPeriod = QuotaPeriod.DAILY,
        limit_value: float = 10,
        **kwargs: Any,
    ) -> Any:
        return await quota_service.set_policy(
            organization_id,
            scope=scope,
            scope_reference=scope_reference,
            kind=kind,
            period=period,
            limit_value=limit_value,
            **kwargs,
        )

    return _make


@pytest_asyncio.fixture
async def app(db_session: AsyncSession, http_client: AsyncClient) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    PostgreSQL, Redis, RabbitMQ, and key loading all run for real. The
    request session and the outbound HTTP client (so a proxied call
    lands on :func:`fake_backend_app` rather than the network) are the
    only two overrides -- see this module's docstring for the one thing
    the session override makes untestable here.
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
    "FAKE_BACKEND_URL",
    "HTTP_BAD_REQUEST",
    "HTTP_CONFLICT",
    "HTTP_CREATED",
    "HTTP_FORBIDDEN",
    "HTTP_NOT_FOUND",
    "HTTP_NO_CONTENT",
    "HTTP_OK",
    "HTTP_TOO_MANY_REQUESTS",
    "HTTP_UNAUTHORIZED",
    "HTTP_UNPROCESSABLE",
    "ago",
    "fake_backend_app",
    "soon",
    "utcnow",
]
