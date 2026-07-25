"""Shared fixtures for the organization service's test suite.

Everything here runs against real infrastructure (the repository
root's docker-compose Postgres/Redis/RabbitMQ) -- the same discipline
``services/rbac-service``/``services/user-management-service``
established. Postgres isolation uses a per-test SAVEPOINT
(``join_transaction_mode="create_savepoint"``), not a second database:
every ``BaseRepository`` write only ``flush()``es, so an outer,
never-committed transaction safely contains everything a test does --
*including* the default organization the seed migration already
applied to the real ``aiios_organization`` database, which every test
therefore sees for free without re-seeding.

This service's own database (``aiios_organization``) is physically
separate from every other AI-IOS service's, the same "database per
service" isolation every prior AI-IOS service's own conftest documents.
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_organization")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "6")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", "localhost")
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")

# app.config.settings.get_settings() is a process-wide lru_cache singleton,
# so the JWT public key path (like every other env var above) must be fixed
# *before* anything calls it for the first time -- generating a session
# keypair inside a fixture and pointing a per-test tmp_path at it doesn't
# work, since only the first test's path would ever actually be read.
_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_organization_test_keys"
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

os.environ.setdefault("AIIOS_ORG_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.core.factory import create_app  # noqa: E402
from app.models.enums import MemberRole, MemberStatus, OrganizationStatus  # noqa: E402
from app.models.member import OrganizationMember  # noqa: E402
from app.models.organization import Organization  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios_organization",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 6 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=6,
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


async def make_org(
    db_session: AsyncSession,
    *,
    name: str = "Test Org",
    slug: str | None = None,
    status: OrganizationStatus = OrganizationStatus.ACTIVE,
) -> Organization:
    """Create a bare organization row, its own ``organization_id`` equal to
    its ``id`` -- the same self-referential pattern
    ``app/services/organization.py::OrganizationService.create()`` uses,
    without the default child rows a full API-driven creation provisions
    (tests that need those call the API/service directly instead).
    """
    org_id = uuid.uuid4()
    organization = Organization(
        id=org_id,
        organization_id=org_id,
        name=name,
        slug=slug or f"test-org-{org_id.hex[:8]}",
        status=status,
    )
    db_session.add(organization)
    await db_session.flush()
    return organization


async def add_member(
    db_session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    role: MemberRole = MemberRole.MEMBER,
    status: MemberStatus = MemberStatus.ACTIVE,
) -> OrganizationMember:
    """Add *user_id* to *organization_id* directly with *role* -- the test
    equivalent of ``app/services/member.py::OrganizationMemberService.add()``.
    """
    member = OrganizationMember(
        organization_id=organization_id, user_id=user_id, role=role, status=status
    )
    db_session.add(member)
    await db_session.flush()
    return member


async def make_org_with_owner(
    db_session: AsyncSession, owner_id: uuid.UUID, **org_kwargs: object
) -> Organization:
    """Create an organization and add *owner_id* as its ``owner`` member --
    the common case nearly every admin-gated test needs.
    """
    organization = await make_org(db_session, **org_kwargs)  # type: ignore[arg-type]
    await add_member(db_session, organization.id, owner_id, role=MemberRole.OWNER)
    return organization


__all__ = [
    "add_member",
    "app",
    "auth_headers",
    "cache_framework",
    "client",
    "db_session",
    "jwt_keypair",
    "make_org",
    "make_org_with_owner",
    "pg_engine",
    "postgres_test_settings",
    "real_redis_client",
    "redis_test_settings",
    "token_for",
]
