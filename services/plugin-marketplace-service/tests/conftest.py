"""Test fixtures for the plugin marketplace service.

Everything runs against **real** PostgreSQL, Redis, RabbitMQ, and MinIO.
Nothing here mocks infrastructure.

**One thing cannot be pointed at a test double at all.**
``shared_core.monitoring.checks.check_http_reachable`` (used by
``PluginHealthService``) builds its own internal ``httpx.AsyncClient``
-- the same confirmed limitation api-gateway-service's own conftest, and
every service since, already documents. Tests for it point at an
already-running container from the standing docker-compose stack
(RabbitMQ's management UI) for "genuinely reachable" and a real loopback
port nothing listens on for "genuinely unreachable".

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
from minio import Minio
from redis.exceptions import RedisError
from shared_core.storage.wrapper import StorageWrapper
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_LOOPBACK = "127.0.0.1"
"""IPv4, never "localhost".

Docker Desktop's IPv6 loopback does not reach the published ports, so a
name that resolves to ``::1`` first makes every connection hang until it
times out rather than failing fast.
"""

os.environ.setdefault("AIIOS_DATABASE_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_plugin_marketplace")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "32")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")
os.environ.setdefault("AIIOS_MINIO_HOST", "localhost")
os.environ.setdefault("AIIOS_MINIO_PORT", "9000")
os.environ.setdefault("AIIOS_MINIO_ACCESS_KEY", "aiios")
os.environ.setdefault("AIIOS_MINIO_SECRET_KEY", "change-me-min-8-chars")
os.environ.setdefault("AIIOS_MINIO_USE_SSL", "false")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_plugin_marketplace_service_test_keys"
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
    "AIIOS_PLUGIN_MARKETPLACE_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH)
)
os.environ.setdefault("AIIOS_PLUGIN_MARKETPLACE_SERVICE_WORKERS_ENABLED", "false")

from shared_core.cache.factory import create_cache_framework  # noqa: E402
from shared_core.cache.manager import CacheManager  # noqa: E402
from shared_core.cache.settings import CacheSettings  # noqa: E402
from shared_core.config.settings import (  # noqa: E402
    DatabaseSettings,
    MinioSettings,
    RabbitMQSettings,
    RedisSettings,
)
from shared_core.database.engine import create_engine  # noqa: E402
from shared_core.security.jwt import encode_token  # noqa: E402
from shared_core.storage import create_minio_client  # noqa: E402

from app.api import deps  # noqa: E402
from app.config.settings import PluginMarketplaceServiceSettings  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.repositories.dependency import PluginDependencyRepository  # noqa: E402
from app.repositories.governance import (  # noqa: E402
    PluginAuditRepository,
    PluginReportRepository,
    PluginStatisticRepository,
)
from app.repositories.health import PluginHealthRepository  # noqa: E402
from app.repositories.installation import PluginInstallationRepository  # noqa: E402
from app.repositories.manifest import PluginManifestRepository  # noqa: E402
from app.repositories.marketplace import PluginMarketplaceRepository  # noqa: E402
from app.repositories.package import PluginPackageRepository  # noqa: E402
from app.repositories.permission import PluginPermissionRepository  # noqa: E402
from app.repositories.plugin import PluginRepository, PluginVersionRepository  # noqa: E402
from app.repositories.publisher import PluginPublisherRepository  # noqa: E402
from app.repositories.review import PluginRatingRepository, PluginReviewRepository  # noqa: E402
from app.repositories.upgrade import PluginRollbackRepository, PluginUpgradeRepository  # noqa: E402
from app.services.dependency import PluginDependencyService  # noqa: E402
from app.services.health import PluginHealthService  # noqa: E402
from app.services.installation import PluginInstallationService  # noqa: E402
from app.services.marketplace import PluginMarketplaceService  # noqa: E402
from app.services.package import PluginPackageService  # noqa: E402
from app.services.permission import PluginPermissionService  # noqa: E402
from app.services.plugin import PluginService  # noqa: E402
from app.services.publisher import PluginPublisherService  # noqa: E402
from app.services.reporting import AuditService, ReportService, StatisticsService  # noqa: E402
from app.services.review import PluginReviewService  # noqa: E402

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
precedent every AI-IOS service's own conftest has established, since
``check_http_reachable`` cannot be pointed at a test double (see this
module's own docstring)."""

UNREACHABLE_HTTP_URL = f"http://{_LOOPBACK}:1"
"""A real loopback port nothing listens on -- genuinely unreachable,
fails fast rather than timing out against a firewalled remote host."""


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_plugin_marketplace",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 32 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=32,
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


def minio_test_settings() -> MinioSettings:
    return MinioSettings(
        minio_host="localhost",
        minio_port=9000,
        minio_access_key="aiios",
        minio_secret_key="change-me-min-8-chars",
        minio_use_ssl=False,
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


@pytest_asyncio.fixture
async def minio_client() -> AsyncIterator[Minio]:
    client = create_minio_client(minio_test_settings())
    try:
        await asyncio.to_thread(client.list_buckets)
    except Exception as exc:
        pytest.skip(f"MinIO is not reachable: {exc}")
    yield client


@pytest.fixture
def storage_wrapper(minio_client: Minio) -> StorageWrapper:
    return StorageWrapper(minio_client)


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
def service_settings() -> PluginMarketplaceServiceSettings:
    """Test-tuned settings: small timeouts, workers disabled."""
    return PluginMarketplaceServiceSettings(
        health_check_timeout_seconds=2.0,
        package_storage_bucket="plugin-packages-test",
        workers_enabled=False,
    )


# ---- repositories -----------------------------------------------------------


@pytest.fixture
def plugins_repo(db_session: AsyncSession) -> PluginRepository:
    return PluginRepository(db_session)


@pytest.fixture
def versions_repo(db_session: AsyncSession) -> PluginVersionRepository:
    return PluginVersionRepository(db_session)


@pytest.fixture
def manifests_repo(db_session: AsyncSession) -> PluginManifestRepository:
    return PluginManifestRepository(db_session)


@pytest.fixture
def packages_repo(db_session: AsyncSession) -> PluginPackageRepository:
    return PluginPackageRepository(db_session)


@pytest.fixture
def dependencies_repo(db_session: AsyncSession) -> PluginDependencyRepository:
    return PluginDependencyRepository(db_session)


@pytest.fixture
def permissions_repo(db_session: AsyncSession) -> PluginPermissionRepository:
    return PluginPermissionRepository(db_session)


@pytest.fixture
def installations_repo(db_session: AsyncSession) -> PluginInstallationRepository:
    return PluginInstallationRepository(db_session)


@pytest.fixture
def upgrades_repo(db_session: AsyncSession) -> PluginUpgradeRepository:
    return PluginUpgradeRepository(db_session)


@pytest.fixture
def rollbacks_repo(db_session: AsyncSession) -> PluginRollbackRepository:
    return PluginRollbackRepository(db_session)


@pytest.fixture
def health_repo(db_session: AsyncSession) -> PluginHealthRepository:
    return PluginHealthRepository(db_session)


@pytest.fixture
def reviews_repo(db_session: AsyncSession) -> PluginReviewRepository:
    return PluginReviewRepository(db_session)


@pytest.fixture
def ratings_repo(db_session: AsyncSession) -> PluginRatingRepository:
    return PluginRatingRepository(db_session)


@pytest.fixture
def publishers_repo(db_session: AsyncSession) -> PluginPublisherRepository:
    return PluginPublisherRepository(db_session)


@pytest.fixture
def marketplace_repo(db_session: AsyncSession) -> PluginMarketplaceRepository:
    return PluginMarketplaceRepository(db_session)


@pytest.fixture
def statistics_repo(db_session: AsyncSession) -> PluginStatisticRepository:
    return PluginStatisticRepository(db_session)


@pytest.fixture
def reports_repo(db_session: AsyncSession) -> PluginReportRepository:
    return PluginReportRepository(db_session)


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> PluginAuditRepository:
    return PluginAuditRepository(db_session)


# ---- services -----------------------------------------------------------


@pytest.fixture
def plugin_service(
    plugins_repo: PluginRepository,
    versions_repo: PluginVersionRepository,
    manifests_repo: PluginManifestRepository,
    publisher: RecordingPublisher,
) -> PluginService:
    return PluginService(plugins_repo, versions_repo, manifests_repo, publish_event=publisher)


@pytest.fixture
def package_service(
    packages_repo: PluginPackageRepository,
    storage_wrapper: StorageWrapper,
    service_settings: PluginMarketplaceServiceSettings,
) -> PluginPackageService:
    return PluginPackageService(
        packages_repo, storage_wrapper, bucket=service_settings.package_storage_bucket
    )


@pytest.fixture
def dependency_service(dependencies_repo: PluginDependencyRepository) -> PluginDependencyService:
    return PluginDependencyService(dependencies_repo)


@pytest.fixture
def permission_service(permissions_repo: PluginPermissionRepository) -> PluginPermissionService:
    return PluginPermissionService(permissions_repo)


@pytest.fixture
def installation_service(
    installations_repo: PluginInstallationRepository,
    plugins_repo: PluginRepository,
    versions_repo: PluginVersionRepository,
    dependencies_repo: PluginDependencyRepository,
    upgrades_repo: PluginUpgradeRepository,
    rollbacks_repo: PluginRollbackRepository,
    publisher: RecordingPublisher,
) -> PluginInstallationService:
    return PluginInstallationService(
        installations_repo,
        plugins_repo,
        versions_repo,
        dependencies_repo,
        upgrades_repo,
        rollbacks_repo,
        publish_event=publisher,
    )


@pytest.fixture
def health_service(
    health_repo: PluginHealthRepository, service_settings: PluginMarketplaceServiceSettings
) -> PluginHealthService:
    return PluginHealthService(
        health_repo,
        timeout_seconds=service_settings.health_check_timeout_seconds,
        failure_threshold=service_settings.health_failure_threshold,
    )


@pytest.fixture
def review_service(
    reviews_repo: PluginReviewRepository, ratings_repo: PluginRatingRepository
) -> PluginReviewService:
    return PluginReviewService(reviews_repo, ratings_repo)


@pytest.fixture
def publisher_service(publishers_repo: PluginPublisherRepository) -> PluginPublisherService:
    return PluginPublisherService(publishers_repo)


@pytest.fixture
def marketplace_service(
    marketplace_repo: PluginMarketplaceRepository, publisher: RecordingPublisher
) -> PluginMarketplaceService:
    return PluginMarketplaceService(marketplace_repo, publish_event=publisher)


@pytest.fixture
def statistics_service(
    statistics_repo: PluginStatisticRepository,
    plugins_repo: PluginRepository,
    installations_repo: PluginInstallationRepository,
    reviews_repo: PluginReviewRepository,
) -> StatisticsService:
    return StatisticsService(statistics_repo, plugins_repo, installations_repo, reviews_repo)


@pytest.fixture
def report_service(
    reports_repo: PluginReportRepository,
    plugins_repo: PluginRepository,
    installations_repo: PluginInstallationRepository,
    publishers_repo: PluginPublisherRepository,
    audit_repo: PluginAuditRepository,
) -> ReportService:
    return ReportService(
        reports_repo, plugins_repo, installations_repo, publishers_repo, audit_repo
    )


@pytest.fixture
def audit_service(audit_repo: PluginAuditRepository) -> AuditService:
    return AuditService(audit_repo)


# ---- composite fixtures --------------------------------------------------


MakePluginFn = Callable[..., Any]


@pytest.fixture
def make_plugin(plugin_service: PluginService, organization_id: uuid.UUID) -> MakePluginFn:
    """Register one plugin."""

    async def _make(slug: str = "test-plugin", **kwargs: Any) -> Any:
        defaults: dict[str, Any] = {
            "name": "Test Plugin",
            "category": "utilities",
            "plugin_type": "custom_plugin",
        }
        defaults.update(kwargs)
        return await plugin_service.register(organization_id, slug=slug, **defaults)

    return _make


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    PostgreSQL, Redis, RabbitMQ, MinIO, and key loading all run for
    real. The request session is the only override -- see this module's
    docstring for the one thing that makes untestable, and for why
    ``check_http_reachable``-backed routes cannot be exercised this way
    at all.
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
    "HTTP_BAD_REQUEST",
    "HTTP_CONFLICT",
    "HTTP_CREATED",
    "HTTP_FORBIDDEN",
    "HTTP_NOT_FOUND",
    "HTTP_NO_CONTENT",
    "HTTP_OK",
    "HTTP_UNAUTHORIZED",
    "HTTP_UNPROCESSABLE",
    "REACHABLE_HTTP_URL",
    "UNREACHABLE_HTTP_URL",
    "ago",
    "soon",
    "utcnow",
]
