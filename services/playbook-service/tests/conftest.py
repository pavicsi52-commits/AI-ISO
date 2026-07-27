"""Shared fixtures for the playbook service's test suite.

Everything here runs against real infrastructure (the repository
root's docker-compose Postgres/Redis/RabbitMQ) -- the same discipline
every prior AI-IOS service established. Postgres isolation uses a
per-test SAVEPOINT (``join_transaction_mode="create_savepoint"``), not
a second database: every ``BaseRepository`` write only ``flush()``es,
so an outer, never-committed transaction safely contains everything a
test does.

No Neo4j fixture exists here -- docs/041 names no graph concept for
this service.

**Structural content validation**: YAML/Python syntax checks need no
external tooling; Bash/Shell syntax checks use the real ``sh``/``bash``
already on this repository's own dev machine and CI image (matching
``services/automation-service``'s own runner tests); PowerShell syntax
checks self-skip cleanly when neither ``pwsh`` nor ``powershell.exe``
is on ``PATH``.

**Digital signatures**: genuinely real Ed25519 sign/verify via
``cryptography`` -- no live external dependency, so no skip condition
is needed the way the SSH/Git-provider tests in prior services needed
one.

This service's own database (``aiios_playbook``) is physically
separate from every other AI-IOS service's. Redis test db 14 --
distinct from every other AI-IOS service's own test db (3
authentication, 4 user-management, 5 rbac, 6 organization, 7 project, 8
secrets-management, 9 inventory, 10 discovery, 11 asset-management, 12
configuration-management, 13 automation).
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
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.config.settings import DatabaseSettings, RedisSettings
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_playbook")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "14")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", "localhost")
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

# app.config.settings.get_settings() is a process-wide lru_cache singleton,
# so the JWT public key path (like every other env var above) must be fixed
# *before* anything calls it for the first time -- generating a session
# keypair inside a fixture and pointing a per-test tmp_path at it doesn't
# work, since only the first test's path would ever actually be read.
_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_playbook_test_keys"
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

os.environ.setdefault("AIIOS_PLAYBOOK_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault(
    "AIIOS_PLAYBOOK_SERVICE_SIGNING_PRIVATE_KEY_PATH", str(Path("keys/signing_private_key.pem"))
)
os.environ.setdefault(
    "AIIOS_PLAYBOOK_SERVICE_SIGNING_PUBLIC_KEY_PATH", str(Path("keys/signing_public_key.pem"))
)

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.core.factory import create_app  # noqa: E402
from app.events.playbook_events import PlaybookCreatedEvent  # noqa: E402, F401
from app.models.enums import ContentType, PlaybookStatus  # noqa: E402
from app.models.playbook import Playbook  # noqa: E402
from app.repositories.playbook import PlaybookRepository  # noqa: E402
from app.repositories.playbook_audit import PlaybookAuditRepository  # noqa: E402
from app.repositories.playbook_version import PlaybookVersionRepository  # noqa: E402
from app.services.audit import PlaybookAuditService  # noqa: E402
from app.services.playbook import EventPublisher, PlaybookService  # noqa: E402
from app.services.version import PlaybookVersionService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios_playbook",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 14 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=14,
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
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    ``get_db_session`` is overridden to hand out this test's SAVEPOINT
    session, so every request made through ``client`` in a given test
    shares one transaction, rolled back at teardown.
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


async def make_playbook(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    name: str = "test-playbook",
    status: PlaybookStatus = PlaybookStatus.DRAFT,
    content_type: ContentType = ContentType.SHELL_SCRIPT,
) -> Playbook:
    """Create a bare :class:`Playbook` row directly -- for tests
    exercising code paths that don't need the full
    :class:`PlaybookService.create` side-effect chain (version snapshot/
    audit/events).
    """
    playbook = Playbook(
        organization_id=organization_id or uuid.uuid4(),
        project_id=project_id,
        name=name,
        status=status,
        content_type=content_type,
    )
    db_session.add(playbook)
    await db_session.flush()
    return playbook


def build_audit_service(db_session: AsyncSession) -> PlaybookAuditService:
    return PlaybookAuditService(PlaybookAuditRepository(db_session))


def build_version_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> PlaybookVersionService:
    return PlaybookVersionService(
        PlaybookVersionRepository(db_session),
        PlaybookRepository(db_session),
        publish_event=publish_event,
    )


def build_playbook_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> PlaybookService:
    """Assemble a real, fully-wired :class:`PlaybookService` bound to
    *db_session* -- the shared wiring nearly every playbook-touching
    service test needs, matching ``app/core/factory.py``'s own
    dependency-graph shape.
    """
    return PlaybookService(
        PlaybookRepository(db_session),
        build_version_service(db_session, publish_event=publish_event),
        build_audit_service(db_session),
        publish_event=publish_event,
    )


def utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "AuthHeadersFn",
    "app",
    "auth_headers",
    "build_audit_service",
    "build_playbook_service",
    "build_version_service",
    "client",
    "db_session",
    "jwt_keypair",
    "make_playbook",
    "pg_engine",
    "postgres_test_settings",
    "real_redis_client",
    "redis_test_settings",
    "token_for",
    "utcnow",
]
