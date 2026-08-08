"""Test fixtures for the AI agent platform service.

Everything runs against **real** PostgreSQL, Redis, RabbitMQ, and Neo4j.
Nothing here mocks infrastructure.

**Neo4j has no SAVEPOINT equivalent**, so graph-touching tests must
clean up their own nodes explicitly -- the same limitation
``knowledge-graph-service``'s own conftest documents.

**Outbound model-provider calls are real HTTP, deliberately unmocked.**
No local Ollama/vLLM is guaranteed to be running in every environment
this suite executes in, so ``ModelRegistry.chat`` failing with "every
provider in the chain failed" is treated as a legitimate, expected
outcome by tests that exercise it -- what those tests verify is that
this service's own dispatch, guardrail, memory, and persistence logic
around that call behaved correctly, not that a real LLM answered.

**The one thing the HTTP tests cannot tell you.** The ``app`` fixture
overrides only the request session, so a test's writes roll back. That
override changes *transaction lifetime*, which means any behaviour whose
correctness depends on transaction lifetime is untestable through it --
the same reasoning every prior AI-IOS service's own conftest documents.
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

import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from neo4j import AsyncDriver
from redis.exceptions import RedisError
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_ai_agent_platform")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "33")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")
os.environ.setdefault("AIIOS_NEO4J_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_NEO4J_BOLT_PORT", "7687")
os.environ.setdefault("AIIOS_NEO4J_USER", "neo4j")
os.environ.setdefault("AIIOS_NEO4J_PASSWORD", "change-me-min-8-chars")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_ai_agent_platform_service_test_keys"
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
    "AIIOS_AI_AGENT_PLATFORM_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH)
)
os.environ.setdefault("AIIOS_AI_AGENT_PLATFORM_SERVICE_WORKERS_ENABLED", "false")

from shared_core.cache.factory import create_cache_framework  # noqa: E402
from shared_core.cache.manager import CacheManager  # noqa: E402
from shared_core.cache.settings import CacheSettings  # noqa: E402
from shared_core.config.settings import (  # noqa: E402
    DatabaseSettings,
    Neo4jSettings,
    RabbitMQSettings,
    RedisSettings,
)
from shared_core.database.engine import create_engine  # noqa: E402
from shared_core.security.jwt import encode_token  # noqa: E402

from app.api import deps  # noqa: E402
from app.clients.registry import ModelRegistry, build_model_clients  # noqa: E402
from app.config.settings import AiAgentPlatformServiceSettings  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.graph.client import GraphClient, create_neo4j_driver  # noqa: E402
from app.memory.service import MemoryService  # noqa: E402
from app.models.enums import AgentType, ModelProvider  # noqa: E402
from app.repositories.agent import AgentRepository, AgentVersionRepository  # noqa: E402
from app.repositories.benchmark import AgentBenchmarkRepository  # noqa: E402
from app.repositories.evaluation import AgentEvaluationRepository  # noqa: E402
from app.repositories.execution import AgentExecutionRepository  # noqa: E402
from app.repositories.governance import (  # noqa: E402
    AgentAuditRepository,
    AgentReportRepository,
    AgentStatisticRepository,
)
from app.repositories.guardrail import AgentGuardrailRepository  # noqa: E402
from app.repositories.marketplace import AgentMarketplaceEntryRepository  # noqa: E402
from app.repositories.memory import AgentMemoryRepository  # noqa: E402
from app.repositories.permission import AgentPermissionGrantRepository  # noqa: E402
from app.repositories.profile import AgentProfileRepository  # noqa: E402
from app.repositories.session import AgentSessionRepository  # noqa: E402
from app.repositories.task import AgentTaskRepository  # noqa: E402
from app.repositories.tool import AgentToolRepository  # noqa: E402
from app.repositories.workflow import AgentWorkflowRepository  # noqa: E402
from app.sandbox.policy import AgentSandboxPolicy  # noqa: E402
from app.services.agent import AgentService, ProfileFields  # noqa: E402
from app.services.execution import ExecutionService  # noqa: E402
from app.services.reporting import AuditService, ReportService, StatisticsService  # noqa: E402
from app.services.task import TaskService  # noqa: E402
from app.services.tool import ToolService  # noqa: E402

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


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_ai_agent_platform",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 33 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=33,
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


def neo4j_test_settings() -> Neo4jSettings:
    return Neo4jSettings(
        neo4j_host=_LOOPBACK,
        neo4j_bolt_port=7687,
        neo4j_user="neo4j",
        neo4j_password="change-me-min-8-chars",
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
async def neo4j_driver() -> AsyncIterator[AsyncDriver]:
    """A Neo4j driver bound to this test's event loop, skipped if unreachable."""
    driver = create_neo4j_driver(neo4j_test_settings())
    if driver is None:
        pytest.skip("Neo4j could not be configured.")
    try:
        await asyncio.wait_for(driver.verify_connectivity(), timeout=5)
    except Exception as exc:
        await driver.close()
        pytest.skip(f"Neo4j is not reachable: {exc}")
    yield driver
    await driver.close()


@pytest.fixture
def graph_client(neo4j_driver: AsyncDriver) -> GraphClient:
    return GraphClient(neo4j_driver, database="neo4j", max_records=5_000)


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
def service_settings() -> AiAgentPlatformServiceSettings:
    """Test-tuned settings: small timeouts, workers disabled."""
    return AiAgentPlatformServiceSettings(
        http_client_timeout_seconds=5.0,
        default_execution_timeout_seconds=5.0,
        workers_enabled=False,
        neo4j_enabled=True,
    )


@pytest_asyncio.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


@pytest.fixture
def sandbox_policy() -> AgentSandboxPolicy:
    return AgentSandboxPolicy()


@pytest.fixture
def model_registry(
    http_client: httpx.AsyncClient, service_settings: AiAgentPlatformServiceSettings
) -> ModelRegistry:
    """A real registry. No local model backend is guaranteed to be
    running, so ``chat()`` genuinely failing is an accepted, expected
    outcome for tests that exercise it -- see this module's own docstring.
    """
    return ModelRegistry(
        build_model_clients(http_client, service_settings),
        default_provider=ModelProvider(service_settings.default_provider),
        default_model=service_settings.default_model,
    )


# ---- repositories -----------------------------------------------------------


@pytest.fixture
def agents_repo(db_session: AsyncSession) -> AgentRepository:
    return AgentRepository(db_session)


@pytest.fixture
def agent_versions_repo(db_session: AsyncSession) -> AgentVersionRepository:
    return AgentVersionRepository(db_session)


@pytest.fixture
def profiles_repo(db_session: AsyncSession) -> AgentProfileRepository:
    return AgentProfileRepository(db_session)


@pytest.fixture
def sessions_repo(db_session: AsyncSession) -> AgentSessionRepository:
    return AgentSessionRepository(db_session)


@pytest.fixture
def tasks_repo(db_session: AsyncSession) -> AgentTaskRepository:
    return AgentTaskRepository(db_session)


@pytest.fixture
def tools_repo(db_session: AsyncSession) -> AgentToolRepository:
    return AgentToolRepository(db_session)


@pytest.fixture
def permissions_repo(db_session: AsyncSession) -> AgentPermissionGrantRepository:
    return AgentPermissionGrantRepository(db_session)


@pytest.fixture
def guardrails_repo(db_session: AsyncSession) -> AgentGuardrailRepository:
    return AgentGuardrailRepository(db_session)


@pytest.fixture
def executions_repo(db_session: AsyncSession) -> AgentExecutionRepository:
    return AgentExecutionRepository(db_session)


@pytest.fixture
def memory_repo(db_session: AsyncSession) -> AgentMemoryRepository:
    return AgentMemoryRepository(db_session)


@pytest.fixture
def evaluations_repo(db_session: AsyncSession) -> AgentEvaluationRepository:
    return AgentEvaluationRepository(db_session)


@pytest.fixture
def benchmarks_repo(db_session: AsyncSession) -> AgentBenchmarkRepository:
    return AgentBenchmarkRepository(db_session)


@pytest.fixture
def marketplace_repo(db_session: AsyncSession) -> AgentMarketplaceEntryRepository:
    return AgentMarketplaceEntryRepository(db_session)


@pytest.fixture
def workflows_repo(db_session: AsyncSession) -> AgentWorkflowRepository:
    return AgentWorkflowRepository(db_session)


@pytest.fixture
def statistics_repo(db_session: AsyncSession) -> AgentStatisticRepository:
    return AgentStatisticRepository(db_session)


@pytest.fixture
def reports_repo(db_session: AsyncSession) -> AgentReportRepository:
    return AgentReportRepository(db_session)


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> AgentAuditRepository:
    return AgentAuditRepository(db_session)


# ---- services -----------------------------------------------------------


@pytest.fixture
def agent_service(
    agents_repo: AgentRepository,
    agent_versions_repo: AgentVersionRepository,
    profiles_repo: AgentProfileRepository,
    audit_repo: AgentAuditRepository,
    publisher: RecordingPublisher,
) -> AgentService:
    return AgentService(
        agents_repo, profiles_repo, agent_versions_repo, audit_repo, publish_event=publisher
    )


@pytest.fixture
def task_service(tasks_repo: AgentTaskRepository, publisher: RecordingPublisher) -> TaskService:
    return TaskService(tasks_repo, publish_event=publisher)


@pytest.fixture
def tool_service(tools_repo: AgentToolRepository) -> ToolService:
    return ToolService(tools_repo)


@pytest.fixture
def memory_service(memory_repo: AgentMemoryRepository) -> MemoryService:
    return MemoryService(memory_repo)


@pytest.fixture
def execution_service(
    db_session: AsyncSession,
    agents_repo: AgentRepository,
    profiles_repo: AgentProfileRepository,
    tools_repo: AgentToolRepository,
    permissions_repo: AgentPermissionGrantRepository,
    executions_repo: AgentExecutionRepository,
    memory_service: MemoryService,
    model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    service_settings: AiAgentPlatformServiceSettings,
    publisher: RecordingPublisher,
) -> ExecutionService:
    return ExecutionService(
        agents_repo,
        profiles_repo,
        tools_repo,
        permissions_repo,
        executions_repo,
        memory_service,
        model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        graph_client=None,
        automation_service_base_url=service_settings.automation_service_base_url,
        session=db_session,
        publish_event=publisher,
    )


@pytest.fixture
def statistics_service(
    statistics_repo: AgentStatisticRepository,
    agents_repo: AgentRepository,
    tasks_repo: AgentTaskRepository,
    executions_repo: AgentExecutionRepository,
    memory_repo: AgentMemoryRepository,
) -> StatisticsService:
    return StatisticsService(statistics_repo, agents_repo, tasks_repo, executions_repo, memory_repo)


@pytest.fixture
def report_service(
    reports_repo: AgentReportRepository,
    agents_repo: AgentRepository,
    executions_repo: AgentExecutionRepository,
    audit_repo: AgentAuditRepository,
) -> ReportService:
    return ReportService(reports_repo, agents_repo, executions_repo, audit_repo)


@pytest.fixture
def audit_service(audit_repo: AgentAuditRepository) -> AuditService:
    return AuditService(audit_repo)


# ---- composite fixtures --------------------------------------------------


MakeAgentFn = Callable[..., Any]


@pytest.fixture
def make_agent(agent_service: AgentService, organization_id: uuid.UUID) -> MakeAgentFn:
    """Register one active agent with its own profile."""

    async def _make(slug: str = "test-agent", **kwargs: Any) -> Any:
        profile_kwargs = kwargs.pop("profile", {})
        defaults: dict[str, Any] = {"name": "Test Agent", "agent_type": AgentType.EXECUTOR}
        defaults.update(kwargs)
        return await agent_service.register(
            organization_id=organization_id,
            slug=slug,
            profile=ProfileFields(**profile_kwargs),
            **defaults,
        )

    return _make


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    PostgreSQL, Redis, RabbitMQ, Neo4j, and key loading all run for
    real. The request session is the only override -- see this module's
    docstring for the one thing that makes untestable.
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
    "ago",
    "soon",
    "utcnow",
]
