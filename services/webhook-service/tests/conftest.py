"""Test fixtures for the webhook service.

Everything runs against **real** PostgreSQL, Redis, and RabbitMQ.
Nothing here mocks infrastructure. The one deliberate substitution is
the *receiving* backend an outgoing delivery lands on:
:func:`fake_backend_app` is a real Starlette application served through
:class:`httpx.ASGITransport` -- genuine ASGI request/response handling,
not a mock -- so :class:`~app.services.delivery.DeliveryService` makes a
real HTTP call end to end without this suite depending on an actual
third-party endpoint being reachable.

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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_webhook")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "30")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_webhook_service_test_keys"
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

os.environ.setdefault("AIIOS_WEBHOOK_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault("AIIOS_WEBHOOK_SERVICE_WORKERS_ENABLED", "false")
os.environ.setdefault("AIIOS_WEBHOOK_SERVICE_SECRET_ENCRYPTION_KEY", generate_encryption_key())
"""``WebhookServiceSettings.secret_encryption_key`` defaults to ``""`` --
deliberately invalid, as its own field docstring says, for local-dev
convenience only; a real deployment must set it. The ``service_settings``
fixture below builds its own valid key for direct service-layer tests, but
the ``app`` fixture's real ``create_app()`` reads settings from the
environment via ``get_settings()``, bypassing that fixture entirely -- so
without a real key here too, the *first* HTTP request that ever calls
``shared_core.security.encryption.encrypt``/``decrypt`` through the real
app (any ``/webhooks/signatures`` route) fails with ``ValueError: AESGCM
key must be 128, 192, or 256 bits.`` before ever reaching application
code. One key, generated once per test session, is enough: every test's
own writes roll back on its own SAVEPOINT, so no encrypted value ever
needs to outlive the test that created it."""

from shared_core.cache.factory import create_cache_framework  # noqa: E402
from shared_core.cache.manager import CacheManager  # noqa: E402
from shared_core.cache.settings import CacheSettings  # noqa: E402
from shared_core.config.settings import (  # noqa: E402
    DatabaseSettings,
    RabbitMQSettings,
    RedisSettings,
)
from shared_core.database.engine import create_engine  # noqa: E402
from shared_core.security.jwt import encode_token  # noqa: E402

from app.api import deps  # noqa: E402
from app.config.settings import WebhookServiceSettings  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.enums import (  # noqa: E402
    EventSource,
    SignatureAlgorithm,
    SubscriptionScope,
    WebhookAuthMethod,
    WebhookKind,
)
from app.repositories.delivery import (  # noqa: E402
    WebhookDeliveryAttemptRepository,
    WebhookDeliveryRepository,
)
from app.repositories.endpoint import WebhookEndpointRepository  # noqa: E402
from app.repositories.event import WebhookEventRepository  # noqa: E402
from app.repositories.filter import WebhookFilterRepository  # noqa: E402
from app.repositories.governance import (  # noqa: E402
    WebhookAuditRepository,
    WebhookReportRepository,
    WebhookStatisticRepository,
)
from app.repositories.idempotency import WebhookIdempotencyKeyRepository  # noqa: E402
from app.repositories.replay import WebhookReplayJobRepository  # noqa: E402
from app.repositories.retry import (  # noqa: E402
    WebhookDeadLetterRepository,
    WebhookRetryQueueRepository,
)
from app.repositories.signature import WebhookSignatureRepository  # noqa: E402
from app.repositories.subscription import WebhookSubscriptionRepository  # noqa: E402
from app.repositories.transformation import WebhookTransformationRepository  # noqa: E402
from app.services.delivery import DeliveryService  # noqa: E402
from app.services.endpoint import EndpointService  # noqa: E402
from app.services.event import EventService  # noqa: E402
from app.services.filter import FilterService  # noqa: E402
from app.services.idempotency import IdempotencyService  # noqa: E402
from app.services.replay import ReplayService  # noqa: E402
from app.services.reporting import AuditService, ReportService, StatisticsService  # noqa: E402
from app.services.signature import SignatureService  # noqa: E402
from app.services.subscription import SubscriptionService  # noqa: E402
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

FAKE_BACKEND_URL = "http://example.com"
"""The endpoint URL every ``make_endpoint`` fixture points at by default.

Must be a *real*, publicly-resolvable hostname -- ``assert_safe_url``
does its own independent DNS resolution (see ``app/security/url_safety
.py``) before any request is ever made, and rejects an unresolvable
host the same way it would reject a private one. ``example.com`` is
IANA-reserved for exactly this kind of documentation/testing use and
always resolves to a genuine public IP. The actual HTTP traffic never
touches the real network regardless: ``http_client`` below uses
``ASGITransport`` as its *sole* transport, which routes every request
through :func:`fake_backend_app` purely by construction, independent
of whatever hostname the request URL names.
"""


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_webhook",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 30 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=30,
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
def service_settings() -> WebhookServiceSettings:
    """Test-tuned settings: a real encryption key, small timeouts, workers disabled."""
    return WebhookServiceSettings(
        secret_encryption_key=generate_encryption_key(),
        signature_timestamp_tolerance_seconds=300,
        delivery_connect_timeout_seconds=2.0,
        delivery_read_timeout_seconds=5.0,
        idempotency_key_ttl_seconds=3_600,
        workers_enabled=False,
    )


async def _fake_echo(request: StarletteRequest) -> JSONResponse:
    body = await request.body()
    return JSONResponse(
        {
            "method": request.method,
            "path": request.url.path,
            "headers": dict(request.headers),
            "body": body.decode("utf-8", errors="replace"),
        }
    )


async def _fake_error(_request: StarletteRequest) -> JSONResponse:
    return JSONResponse({"detail": "backend failure"}, status_code=500)


def fake_backend_app() -> Starlette:
    """A real ASGI application standing in for an external delivery target.

    Not a mock -- genuine Starlette routing and JSON responses, served
    through :class:`httpx.ASGITransport` so :class:`~app.services.delivery
    .DeliveryService` makes a real, complete HTTP request/response cycle
    without this suite depending on any actual third-party endpoint.
    """
    return Starlette(
        routes=[
            StarletteRoute("/echo", _fake_echo, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
            StarletteRoute("/error", _fake_error, methods=["POST"]),
        ]
    )


@pytest.fixture
def http_client() -> AsyncClient:
    """An HTTP client whose every outbound request lands on :func:`fake_backend_app`."""
    return AsyncClient(transport=ASGITransport(app=fake_backend_app()))


# ---- repositories -----------------------------------------------------------


@pytest.fixture
def endpoints_repo(db_session: AsyncSession) -> WebhookEndpointRepository:
    return WebhookEndpointRepository(db_session)


@pytest.fixture
def subscriptions_repo(db_session: AsyncSession) -> WebhookSubscriptionRepository:
    return WebhookSubscriptionRepository(db_session)


@pytest.fixture
def events_repo(db_session: AsyncSession) -> WebhookEventRepository:
    return WebhookEventRepository(db_session)


@pytest.fixture
def deliveries_repo(db_session: AsyncSession) -> WebhookDeliveryRepository:
    return WebhookDeliveryRepository(db_session)


@pytest.fixture
def attempts_repo(db_session: AsyncSession) -> WebhookDeliveryAttemptRepository:
    return WebhookDeliveryAttemptRepository(db_session)


@pytest.fixture
def filters_repo(db_session: AsyncSession) -> WebhookFilterRepository:
    return WebhookFilterRepository(db_session)


@pytest.fixture
def transformations_repo(db_session: AsyncSession) -> WebhookTransformationRepository:
    return WebhookTransformationRepository(db_session)


@pytest.fixture
def signatures_repo(db_session: AsyncSession) -> WebhookSignatureRepository:
    return WebhookSignatureRepository(db_session)


@pytest.fixture
def idempotency_repo(db_session: AsyncSession) -> WebhookIdempotencyKeyRepository:
    return WebhookIdempotencyKeyRepository(db_session)


@pytest.fixture
def replay_jobs_repo(db_session: AsyncSession) -> WebhookReplayJobRepository:
    return WebhookReplayJobRepository(db_session)


@pytest.fixture
def retry_queue_repo(db_session: AsyncSession) -> WebhookRetryQueueRepository:
    return WebhookRetryQueueRepository(db_session)


@pytest.fixture
def dead_letters_repo(db_session: AsyncSession) -> WebhookDeadLetterRepository:
    return WebhookDeadLetterRepository(db_session)


@pytest.fixture
def statistics_repo(db_session: AsyncSession) -> WebhookStatisticRepository:
    return WebhookStatisticRepository(db_session)


@pytest.fixture
def reports_repo(db_session: AsyncSession) -> WebhookReportRepository:
    return WebhookReportRepository(db_session)


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> WebhookAuditRepository:
    return WebhookAuditRepository(db_session)


# ---- services -----------------------------------------------------------


@pytest.fixture
def endpoint_service(endpoints_repo: WebhookEndpointRepository) -> EndpointService:
    return EndpointService(endpoints_repo)


@pytest.fixture
def subscription_service(subscriptions_repo: WebhookSubscriptionRepository) -> SubscriptionService:
    return SubscriptionService(subscriptions_repo)


@pytest.fixture
def filter_service(filters_repo: WebhookFilterRepository) -> FilterService:
    return FilterService(filters_repo)


@pytest.fixture
def transformation_service(
    transformations_repo: WebhookTransformationRepository,
) -> TransformationService:
    return TransformationService(transformations_repo)


@pytest.fixture
def signature_service(
    signatures_repo: WebhookSignatureRepository, service_settings: WebhookServiceSettings
) -> SignatureService:
    return SignatureService(signatures_repo, encryption_key=service_settings.secret_encryption_key)


@pytest.fixture
def idempotency_service(
    idempotency_repo: WebhookIdempotencyKeyRepository, service_settings: WebhookServiceSettings
) -> IdempotencyService:
    return IdempotencyService(
        idempotency_repo, ttl_seconds=service_settings.idempotency_key_ttl_seconds
    )


@pytest.fixture
def event_service(
    events_repo: WebhookEventRepository, publisher: RecordingPublisher
) -> EventService:
    return EventService(events_repo, publish_event=publisher)


@pytest.fixture
def delivery_service(
    http_client: AsyncClient,
    deliveries_repo: WebhookDeliveryRepository,
    attempts_repo: WebhookDeliveryAttemptRepository,
    endpoints_repo: WebhookEndpointRepository,
    retry_queue_repo: WebhookRetryQueueRepository,
    dead_letters_repo: WebhookDeadLetterRepository,
    subscription_service: SubscriptionService,
    filter_service: FilterService,
    transformation_service: TransformationService,
    signature_service: SignatureService,
    publisher: RecordingPublisher,
) -> DeliveryService:
    return DeliveryService(
        http_client=http_client,
        deliveries=deliveries_repo,
        attempts=attempts_repo,
        endpoints=endpoints_repo,
        retry_queue=retry_queue_repo,
        dead_letters=dead_letters_repo,
        subscriptions=subscription_service,
        filters=filter_service,
        transformations=transformation_service,
        signatures=signature_service,
        publish_event=publisher,
    )


@pytest.fixture
def replay_service(
    replay_jobs_repo: WebhookReplayJobRepository,
    events_repo: WebhookEventRepository,
    delivery_service: DeliveryService,
) -> ReplayService:
    return ReplayService(replay_jobs_repo, events_repo, delivery_service)


@pytest.fixture
def statistics_service(
    statistics_repo: WebhookStatisticRepository, attempts_repo: WebhookDeliveryAttemptRepository
) -> StatisticsService:
    return StatisticsService(statistics_repo, attempts_repo)


@pytest.fixture
def report_service(
    reports_repo: WebhookReportRepository,
    attempts_repo: WebhookDeliveryAttemptRepository,
    events_repo: WebhookEventRepository,
    dead_letters_repo: WebhookDeadLetterRepository,
    audit_repo: WebhookAuditRepository,
) -> ReportService:
    return ReportService(reports_repo, attempts_repo, events_repo, dead_letters_repo, audit_repo)


@pytest.fixture
def audit_service(audit_repo: WebhookAuditRepository) -> AuditService:
    return AuditService(audit_repo)


# ---- composite fixtures --------------------------------------------------


MakeEndpointFn = Callable[..., Any]


@pytest.fixture
def make_endpoint(endpoint_service: EndpointService, organization_id: uuid.UUID) -> MakeEndpointFn:
    """Register one endpoint pointed at the fake backend."""

    async def _make(
        name: str = "test-endpoint",
        *,
        url: str = f"{FAKE_BACKEND_URL}/echo",
        kind: WebhookKind = WebhookKind.OUTGOING,
        auth_method: WebhookAuthMethod = WebhookAuthMethod.HMAC_SHA256,
        **kwargs: Any,
    ) -> Any:
        return await endpoint_service.register(
            organization_id, name=name, url=url, kind=kind, auth_method=auth_method, **kwargs
        )

    return _make


MakeSubscriptionFn = Callable[..., Any]


@pytest.fixture
def make_subscription(
    subscription_service: SubscriptionService, organization_id: uuid.UUID
) -> MakeSubscriptionFn:
    """Register one subscription for a given endpoint."""

    async def _make(
        endpoint_id: uuid.UUID,
        *,
        scope: SubscriptionScope = SubscriptionScope.WILDCARD,
        scope_reference: str | None = None,
        event_types: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        return await subscription_service.create(
            organization_id,
            endpoint_id=endpoint_id,
            scope=scope,
            scope_reference=scope_reference,
            event_types=event_types or [],
            **kwargs,
        )

    return _make


MakeEventFn = Callable[..., Any]


@pytest.fixture
def make_event(event_service: EventService, organization_id: uuid.UUID) -> MakeEventFn:
    """Raise one internal event."""

    async def _make(event_type: str = "test.event", **kwargs: Any) -> Any:
        kwargs.setdefault("source", EventSource.CUSTOM)
        kwargs.setdefault("payload", {"hello": "world"})
        return await event_service.ingest_internal(organization_id, event_type=event_type, **kwargs)

    return _make


MakeSignatureFn = Callable[..., Any]


@pytest.fixture
def make_signature(
    signature_service: SignatureService, organization_id: uuid.UUID
) -> MakeSignatureFn:
    """Create one signing secret for a given endpoint."""

    async def _make(
        endpoint_id: uuid.UUID,
        *,
        secret: str = "test-secret-value",
        algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
    ) -> Any:
        return await signature_service.create(
            organization_id, endpoint_id=endpoint_id, secret=secret, algorithm=algorithm
        )

    return _make


@pytest_asyncio.fixture
async def app(db_session: AsyncSession, http_client: AsyncClient) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    PostgreSQL, Redis, RabbitMQ, and key loading all run for real. The
    request session and the outbound HTTP client (so a delivery lands on
    :func:`fake_backend_app` rather than the network) are the only two
    overrides -- see this module's docstring for the one thing the
    session override makes untestable here.
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
    "HTTP_UNAUTHORIZED",
    "HTTP_UNPROCESSABLE",
    "ago",
    "fake_backend_app",
    "soon",
    "utcnow",
]
