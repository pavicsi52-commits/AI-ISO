"""Shared fixtures for the project service's test suite.

Everything here runs against real infrastructure (the repository
root's docker-compose Postgres/Redis/RabbitMQ/MinIO) -- the same
discipline every prior AI-IOS service established. Postgres isolation
uses a per-test SAVEPOINT (``join_transaction_mode="create_savepoint"``),
not a second database: every ``BaseRepository`` write only ``flush()``es,
so an outer, never-committed transaction safely contains everything a
test does -- *including* the seed migration's 8 system project roles,
which every test therefore sees for free without re-seeding.

**A deliberate exception**: :class:`~app.services.import_service
.ProjectImportService`/:class:`~app.services.export_service
.ProjectExportService` explicitly ``commit()`` their own job row (see
that module's own docstring for why -- a queue-consumer worker on a
separate connection must see it). Tests exercising those two services
directly therefore use the real, committing ``pg_engine``-backed
session fixtures (mirroring
``services/organization-service/tests/test_worker_regression.py``'s
precedent for testing commit behavior), not the rolled-back
``db_session`` fixture every other test uses.

This service's own database (``aiios_project``) is physically separate
from every other AI-IOS service's, the same "database per service"
isolation every prior AI-IOS service's own conftest documents.
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
from minio import Minio
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.cache.factory import CacheFramework, create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.config.settings import DatabaseSettings, MinioSettings, RedisSettings
from shared_core.database.engine import create_engine
from shared_core.security.jwt import encode_token
from shared_core.storage import StorageWrapper, create_minio_client
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Must be set before shared_core.config.cache.get_settings() is first called
# (a process-wide lru_cache singleton), so this whole block runs at import
# time -- ahead of app.api.deps/app.core.factory being imported below, and
# ahead of any fixture or test -- exactly like every other AIIOS_* default
# already set the same way in every prior AI-IOS service's own conftest.
os.environ.setdefault("AIIOS_DATABASE_HOST", "localhost")
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_project")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "7")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", "localhost")
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_MINIO_HOST", "localhost")
os.environ.setdefault("AIIOS_MINIO_PORT", "9000")
os.environ.setdefault("AIIOS_MINIO_ACCESS_KEY", "aiios")
os.environ.setdefault("AIIOS_MINIO_SECRET_KEY", "change-me-min-8-chars")
os.environ.setdefault("AIIOS_MINIO_USE_SSL", "false")
os.environ.setdefault("AIIOS_PROJECT_SERVICE_IMPORT_EXPORT_BUCKET", "project-import-export-test")

# app.config.settings.get_settings() is a process-wide lru_cache singleton,
# so the JWT public key path (like every other env var above) must be fixed
# *before* anything calls it for the first time -- generating a session
# keypair inside a fixture and pointing a per-test tmp_path at it doesn't
# work, since only the first test's path would ever actually be read.
_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_project_test_keys"
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

os.environ.setdefault("AIIOS_PROJECT_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.core.factory import create_app  # noqa: E402
from app.models.enums import ProjectMemberStatus, ProjectStatus, ProjectVisibility  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.project_member import ProjectMember  # noqa: E402
from app.models.project_role import OWNER_ROLE_ID  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios_project",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 7 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=7,
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
    visible to independent connections -- see this module's own
    docstring for why :class:`ProjectImportService`/:class:`ProjectExportService`
    need this instead of the rolled-back ``db_session`` fixture.
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


@pytest_asyncio.fixture
async def minio_client() -> AsyncIterator[Minio]:
    client = create_minio_client(minio_test_settings())
    try:
        await asyncio.wait_for(asyncio.to_thread(client.list_buckets), timeout=5)
    except UNREACHABLE_ERRORS as exc:
        pytest.skip(f"MinIO is not reachable: {exc}")
    yield client


@pytest.fixture
def storage_wrapper(minio_client: Minio) -> StorageWrapper:
    return StorageWrapper(minio_client)


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


async def make_project(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    name: str = "Test Project",
    code: str | None = None,
    owner_id: uuid.UUID | None = None,
    status: ProjectStatus = ProjectStatus.ACTIVE,
    visibility: ProjectVisibility = ProjectVisibility.PRIVATE,
) -> Project:
    """Create a bare project row, its own ``project_id`` equal to its
    ``id`` -- the same self-referential pattern
    ``app/services/project.py::ProjectService.create()`` uses.
    """
    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        project_id=project_id,
        organization_id=organization_id or uuid.uuid4(),
        name=name,
        code=code or f"test-{project_id.hex[:8]}",
        owner_id=owner_id or uuid.uuid4(),
        status=status,
        visibility=visibility,
    )
    db_session.add(project)
    await db_session.flush()
    return project


async def add_member(
    db_session: AsyncSession,
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    role_id: uuid.UUID,
    status: ProjectMemberStatus = ProjectMemberStatus.ACTIVE,
) -> ProjectMember:
    """Add *user_id* to *project_id* directly with *role_id*."""
    member = ProjectMember(
        project_id=project_id,
        organization_id=organization_id,
        user_id=user_id,
        role_id=role_id,
        status=status,
    )
    db_session.add(member)
    await db_session.flush()
    return member


async def make_project_with_owner(
    db_session: AsyncSession, owner_id: uuid.UUID, **project_kwargs: object
) -> Project:
    """Create a project and add *owner_id* as its Owner member -- the
    common case nearly every admin-gated test needs.
    """
    project = await make_project(db_session, owner_id=owner_id, **project_kwargs)  # type: ignore[arg-type]
    await add_member(
        db_session, project.id, project.organization_id, owner_id, role_id=OWNER_ROLE_ID
    )
    return project


__all__ = [
    "add_member",
    "app",
    "auth_headers",
    "cache_framework",
    "client",
    "committing_session_factory",
    "db_session",
    "jwt_keypair",
    "make_project",
    "make_project_with_owner",
    "minio_client",
    "minio_test_settings",
    "pg_engine",
    "postgres_test_settings",
    "real_redis_client",
    "redis_test_settings",
    "storage_wrapper",
    "token_for",
]
