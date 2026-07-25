"""Shared fixtures for the secrets management service's test suite.

Everything here runs against real infrastructure (the repository
root's docker-compose Postgres/Redis/RabbitMQ) -- the same discipline
every prior AI-IOS service established. Postgres isolation uses a
per-test SAVEPOINT (``join_transaction_mode="create_savepoint"``), not
a second database: every ``BaseRepository`` write only ``flush()``es,
so an outer, never-committed transaction safely contains everything a
test does.

This service's own database (``aiios_secrets``) is physically separate
from every other AI-IOS service's, the same "database per service"
isolation every prior AI-IOS service's own conftest documents. No
MinIO fixtures -- this service has no bulk file import/export need.
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
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.cache.factory import CacheFramework, create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.config.settings import DatabaseSettings, RedisSettings
from shared_core.database.engine import create_engine
from shared_core.security.encryption import generate_encryption_key
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_secrets")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "8")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", "localhost")
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")

# app.config.settings.get_settings() is a process-wide lru_cache singleton,
# so the JWT public key path and master key path (like every other env var
# above) must be fixed *before* anything calls it for the first time --
# generating them inside a fixture and pointing a per-test tmp_path at them
# doesn't work, since only the first test's path would ever actually be read.
_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_secrets_test_keys"
_TEST_KEY_DIR.mkdir(parents=True, exist_ok=True)
_TEST_PRIVATE_KEY_PATH = _TEST_KEY_DIR / "private.pem"
_TEST_PUBLIC_KEY_PATH = _TEST_KEY_DIR / "public.pem"
_TEST_MASTER_KEY_PATH = _TEST_KEY_DIR / "master.key"

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

if not _TEST_MASTER_KEY_PATH.is_file():
    _TEST_MASTER_KEY_PATH.write_text(generate_encryption_key(), encoding="ascii")

os.environ.setdefault("AIIOS_SECRETS_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault("AIIOS_SECRETS_SERVICE_MASTER_KEY_PATH", str(_TEST_MASTER_KEY_PATH))
os.environ.setdefault("AIIOS_SECRETS_SERVICE_ROTATION_CHECK_INTERVAL_SECONDS", "3600")
os.environ.setdefault("AIIOS_SECRETS_SERVICE_LEASE_SWEEP_INTERVAL_SECONDS", "3600")

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.core.factory import create_app  # noqa: E402
from app.encryption.envelope import EnvelopeEncryption  # noqa: E402
from app.models.enums import SecretStatus, SecretType  # noqa: E402
from app.models.secret import Secret  # noqa: E402
from app.repositories.encryption_key import EncryptionKeyRepository  # noqa: E402
from app.repositories.key_rotation_history import KeyRotationHistoryRepository  # noqa: E402
from app.repositories.secret import SecretRepository  # noqa: E402
from app.repositories.secret_audit import SecretAuditRepository  # noqa: E402
from app.repositories.secret_rotation import SecretRotationRepository  # noqa: E402
from app.repositories.secret_tag import SecretTagRepository  # noqa: E402
from app.repositories.secret_version import SecretVersionRepository  # noqa: E402
from app.services.audit import SecretAuditService  # noqa: E402
from app.services.encryption_key import EncryptionKeyService  # noqa: E402
from app.services.key_rotation_history import KeyRotationHistoryService  # noqa: E402
from app.services.rotation_history import SecretRotationHistoryService  # noqa: E402
from app.services.secret import EventPublisher, SecretService  # noqa: E402
from app.services.secret_version import SecretVersionService  # noqa: E402
from app.services.tag import SecretTagService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios_secrets",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 8 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=8,
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
    visible to independent connections -- used by the background-worker
    regression tests, which construct their own session per unit of work
    the same way ``app/core/factory.py::_build_worker_services`` does.
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
async def cache_framework() -> AsyncIterator[CacheFramework]:
    try:
        framework = await create_cache_framework(CacheSettings(redis=redis_test_settings()))
    except UNREACHABLE_ERRORS as exc:
        pytest.skip(f"Redis is not reachable: {exc}")
    await framework.client.flushdb()
    yield framework
    await framework.client.flushdb()
    await framework.shutdown()


@pytest.fixture(scope="session")
def jwt_keypair() -> tuple[str, str]:
    """The test session's fixed RSA keypair -- see the module-level key
    generation above for why this can't be regenerated per-test.
    """
    return (
        _TEST_PRIVATE_KEY_PATH.read_text(encoding="ascii"),
        _TEST_PUBLIC_KEY_PATH.read_text(encoding="ascii"),
    )


@pytest.fixture(scope="session")
def master_key() -> str:
    """The test session's fixed envelope-encryption master key."""
    return _TEST_MASTER_KEY_PATH.read_text(encoding="ascii").strip()


@pytest.fixture
def envelope(master_key: str) -> EnvelopeEncryption:
    """A fresh :class:`EnvelopeEncryption` bound to the test master key."""
    return EnvelopeEncryption(master_key)


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


async def make_secret(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    name: str = "test-secret",
    secret_type: SecretType = SecretType.PASSWORD,
    owner_id: uuid.UUID | None = None,
    status: SecretStatus = SecretStatus.ACTIVE,
    current_version: int = 0,
) -> Secret:
    """Create a bare :class:`Secret` row, with no version -- for tests
    exercising code paths that don't need a real encrypted value (most
    do; see ``make_secret_with_value`` in test files that construct the
    full service stack instead).
    """
    secret = Secret(
        organization_id=organization_id or uuid.uuid4(),
        project_id=project_id,
        name=name,
        secret_type=secret_type,
        owner_id=owner_id or uuid.uuid4(),
        status=status,
        current_version=current_version,
    )
    db_session.add(secret)
    await db_session.flush()
    return secret


def build_encryption_key_service(
    db_session: AsyncSession,
    envelope: EnvelopeEncryption,
    *,
    publish_event: EventPublisher | None = None,
) -> EncryptionKeyService:
    """Assemble a real :class:`EncryptionKeyService` bound to *db_session*
    -- the shared wiring nearly every crypto-touching service test needs,
    matching ``app/core/factory.py::_build_worker_services``'s own shape.
    """
    history = KeyRotationHistoryService(KeyRotationHistoryRepository(db_session))
    return EncryptionKeyService(
        EncryptionKeyRepository(db_session), envelope, history, publish_event=publish_event
    )


def build_secret_version_service(
    db_session: AsyncSession,
    envelope: EnvelopeEncryption,
    *,
    publish_event: EventPublisher | None = None,
) -> SecretVersionService:
    """Assemble a real :class:`SecretVersionService` bound to *db_session*."""
    keys = build_encryption_key_service(db_session, envelope, publish_event=publish_event)
    return SecretVersionService(SecretVersionRepository(db_session), keys)


def build_secret_service(
    db_session: AsyncSession,
    envelope: EnvelopeEncryption,
    *,
    publish_event: EventPublisher | None = None,
) -> SecretService:
    """Assemble a real, fully-wired :class:`SecretService` bound to
    *db_session* -- the shared wiring nearly every service test needs,
    since most other resources (certificates, SSH keys, API keys) store
    their sensitive material as a :class:`~app.models.secret.Secret`.
    """
    versions = build_secret_version_service(db_session, envelope, publish_event=publish_event)
    tags = SecretTagService(SecretTagRepository(db_session))
    rotation_history = SecretRotationHistoryService(SecretRotationRepository(db_session))
    audit = SecretAuditService(SecretAuditRepository(db_session))
    return SecretService(
        SecretRepository(db_session),
        versions,
        tags,
        rotation_history,
        audit,
        publish_event=publish_event,
    )


__all__ = [
    "app",
    "auth_headers",
    "build_encryption_key_service",
    "build_secret_service",
    "build_secret_version_service",
    "cache_framework",
    "client",
    "committing_session_factory",
    "db_session",
    "envelope",
    "jwt_keypair",
    "make_secret",
    "master_key",
    "pg_engine",
    "postgres_test_settings",
    "real_redis_client",
    "redis_test_settings",
    "token_for",
]
