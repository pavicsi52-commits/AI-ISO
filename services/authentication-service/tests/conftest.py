"""Shared fixtures for the authentication service's test suite.

Everything here runs against the real infrastructure started by the
repository's root ``docker-compose.yml`` (Postgres, Redis, RabbitMQ) --
the same "real infrastructure integration testing wherever feasible"
discipline the rest of this repository's test suites follow (see
``packages/shared-core/tests/unit/conftest.py``). Postgres isolation
between tests uses a per-test SAVEPOINT
(``join_transaction_mode="create_savepoint"``) rather than a second
database: the service's own Alembic migration already owns the schema
in the real ``aiios`` database, every ``BaseRepository`` write only
``flush()``es (never commits) so an outer, never-committed transaction
safely contains everything a test does -- including a *real*
``session.commit()`` reached through the app's own HTTP layer.
"""

from __future__ import annotations

import os

# Must be set before shared_core.config.cache.get_settings() is first
# called (triggered lazily, the first time anything builds a Settings
# instance) -- that cache is a process-wide singleton, so these need to
# be in place before any fixture or test imports app.core.factory.
os.environ.setdefault("AIIOS_DATABASE_HOST", "localhost")
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "3")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", "localhost")
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.cache.factory import CacheFramework, create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.config.settings import DatabaseSettings, RedisSettings
from shared_core.constants.authentication import AuthConstants
from shared_core.database.engine import create_engine
from shared_core.security.mfa import generate_totp_code
from shared_core.security.sessions import SessionManager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api import deps
from app.config.keys import generate_keypair
from app.core.factory import create_app

# Deliberately narrow: only genuine unreachability skips a test. A
# protocol-level error (bad credentials, missing vhost) is a real bug
# and should fail loudly -- matching packages/shared-core/tests's policy.
UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)


def postgres_test_settings() -> DatabaseSettings:
    """PostgreSQL connection settings matching the repo's docker-compose.yml."""
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Redis connection settings matching the repo's docker-compose.yml.

    Uses db 3, distinct from the development default (db 0), so the
    test suite's session keys never collide with a developer's own
    manually-run instance of this service.
    """
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=3,
        _env_file=None,
    )


@pytest_asyncio.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """A real engine against the docker-compose PostgreSQL instance.

    Skips (rather than fails) the test if Postgres is unreachable.
    """
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
    """One SAVEPOINT-isolated session per test, always rolled back.

    Bound to a connection with its own outer transaction; the session
    factory uses ``join_transaction_mode="create_savepoint"`` so an
    internal ``session.commit()`` only releases a SAVEPOINT rather than
    truly committing -- verified empirically against the real database
    before this fixture was written.
    """
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
    """A real client against the docker-compose Redis instance (test db 3)."""
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
async def app(db_session: AsyncSession):
    """The real FastAPI app, started through its actual lifespan.

    ``get_db_session`` is overridden to hand out this test's SAVEPOINT
    session instead of a real per-request one, so every request made
    through ``client`` in a given test shares one transaction that is
    rolled back at teardown. Everything else (Redis-backed sessions,
    RabbitMQ event publishing, JWT keys) is the real thing, per this
    suite's "real infrastructure wherever feasible" discipline.
    """
    application = create_app()
    async with application.router.lifespan_context(application):

        async def _override_db_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        application.dependency_overrides[deps.get_db_session] = _override_db_session
        yield application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired directly to the real app via ASGI, no network socket."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def real_app():
    """The real app with NO database dependency override.

    Reserved for the small number of tests that specifically verify
    cross-request persistence (a write made in one request is durably
    visible to a later, independent request) -- the exact regression
    this package's development caught: repositories only ``flush()``,
    so ``get_db_session`` must itself commit. Every test using this
    fixture is responsible for cleaning up whatever rows it creates.
    """
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def real_client(real_app) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired to :func:`real_app` -- see its docstring."""
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def cache_framework() -> AsyncIterator[CacheFramework]:
    """A real :class:`CacheFramework` against the docker-compose Redis instance (test db 3)."""
    try:
        framework = await create_cache_framework(CacheSettings(redis=redis_test_settings()))
    except UNREACHABLE_ERRORS as exc:
        pytest.skip(f"Redis is not reachable: {exc}")
    await framework.client.flushdb()
    yield framework
    await framework.client.flushdb()
    await framework.shutdown()


@pytest.fixture
def session_manager(cache_framework: CacheFramework) -> SessionManager:
    """A real, Redis-backed :class:`SessionManager` for service-layer tests."""
    return SessionManager(
        cache_framework.manager,
        idle_timeout_seconds=AuthConstants.SESSION_IDLE_TIMEOUT_SECONDS,
        absolute_timeout_seconds=AuthConstants.SESSION_ABSOLUTE_TIMEOUT_SECONDS,
        max_concurrent_sessions=AuthConstants.MAX_CONCURRENT_SESSIONS,
    )


def unique_email() -> str:
    """A collision-free email for tests that commit for real."""
    return f"test-{uuid.uuid4().hex}@example.com"


DEFAULT_TEST_PASSWORD = "Sup3rSecret!23"


async def register_via_api(
    client: AsyncClient, *, email: str | None = None, password: str = DEFAULT_TEST_PASSWORD
) -> dict[str, Any]:
    """Register a user through the real HTTP surface, returning the response body's ``data``."""
    response = await client.post(
        "/auth/register",
        json={"email": email or unique_email(), "password": password, "display_name": None},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def login_via_api(
    client: AsyncClient,
    *,
    email: str,
    password: str = DEFAULT_TEST_PASSWORD,
    mfa_code: str | None = None,
) -> dict[str, Any]:
    """Log in through the real HTTP surface, returning the response body's ``data``."""
    payload: dict[str, Any] = {"email": email, "password": password}
    if mfa_code is not None:
        payload["mfa_code"] = mfa_code
    response = await client.post("/auth/login", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def register_and_login(
    client: AsyncClient, *, password: str = DEFAULT_TEST_PASSWORD
) -> tuple[str, dict[str, Any]]:
    """Register a fresh user and log in, returning ``(email, token_response_data)``."""
    email = unique_email()
    await register_via_api(client, email=email, password=password)
    tokens = await login_via_api(client, email=email, password=password)
    return email, tokens


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def totp_code() -> Callable[[str], str]:
    """Return a function computing the current valid TOTP code for a given secret."""
    return generate_totp_code


@pytest.fixture(scope="session")
def jwt_keypair() -> tuple[str, str]:
    """A real RSA keypair, generated once per test session (RSA-4096 keygen is not free)."""
    return generate_keypair()


__all__ = [
    "DEFAULT_TEST_PASSWORD",
    "app",
    "auth_headers",
    "cache_framework",
    "client",
    "db_session",
    "jwt_keypair",
    "login_via_api",
    "pg_engine",
    "postgres_test_settings",
    "real_app",
    "real_client",
    "real_redis_client",
    "redis_test_settings",
    "register_and_login",
    "register_via_api",
    "session_manager",
    "totp_code",
    "unique_email",
]
