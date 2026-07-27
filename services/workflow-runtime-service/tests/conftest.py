"""Shared fixtures for the workflow runtime service's test suite.

Everything here runs against real infrastructure (the repository
root's docker-compose Postgres/Redis/RabbitMQ) -- the same discipline
every prior AI-IOS service established. Postgres isolation uses a
per-test SAVEPOINT (``join_transaction_mode="create_savepoint"``), not
a second database: every ``BaseRepository`` write only ``flush()``es,
so an outer, never-committed transaction safely contains everything a
test does.

No Neo4j fixture exists here -- docs/042 names no graph concept for
this service.

**Workflow SDK execution**: ``shared_core.workflow.WorkflowEngine.run()``
is exercised for real (no mocking of the DAG engine itself) --
``TASK``/``CONNECTOR``/``WEBHOOK`` node dispatch (the only handlers that
make outbound HTTP calls) uses ``pytest-httpx`` against
``services/automation-service``'s own real documented response shapes,
never a live account, the same precedent
``services/automation-service``'s own Secrets/Inventory/Configuration
Management cross-service tests established.

This service's own database (``aiios_workflow_runtime``) is physically
separate from every other AI-IOS service's. Redis test db 15 --
distinct from every other AI-IOS service's own test db (3
authentication, 4 user-management, 5 rbac, 6 organization, 7 project, 8
secrets-management, 9 inventory, 10 discovery, 11 asset-management, 12
configuration-management, 13 automation, 14 playbook).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.config.settings import DatabaseSettings, RabbitMQSettings, RedisSettings
from shared_core.database.engine import create_engine
from shared_core.queue.factory import QueueFramework, create_queue_framework
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
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_workflow_runtime")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", "localhost")
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "15")
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
_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_workflow_runtime_test_keys"
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
    "AIIOS_WORKFLOW_RUNTIME_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH)
)
os.environ.setdefault(
    "AIIOS_WORKFLOW_RUNTIME_SERVICE_AUTOMATION_SERVICE_BASE_URL", "http://automation.internal"
)
os.environ.setdefault(
    "AIIOS_WORKFLOW_RUNTIME_SERVICE_PLAYBOOK_SERVICE_BASE_URL", "http://playbook.internal"
)
os.environ.setdefault(
    "AIIOS_WORKFLOW_RUNTIME_SERVICE_INVENTORY_SERVICE_BASE_URL", "http://inventory.internal"
)

from shared_core.workflow import WorkflowTaskQueue  # noqa: E402

from app.api import deps  # noqa: E402  -- see the module-level env var block above
from app.core.factory import create_app  # noqa: E402
from app.events.workflow_events import WorkflowStartedEvent  # noqa: E402, F401
from app.models.enums import WorkflowInstanceStatus, WorkflowTriggerType  # noqa: E402
from app.models.workflow_definition import WorkflowDefinition  # noqa: E402
from app.models.workflow_instance import WorkflowInstance  # noqa: E402
from app.models.workflow_version import WorkflowVersion  # noqa: E402
from app.repositories.workflow_approval import WorkflowApprovalRepository  # noqa: E402
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository  # noqa: E402
from app.repositories.workflow_compensation import WorkflowCompensationRepository  # noqa: E402
from app.repositories.workflow_definition import WorkflowDefinitionRepository  # noqa: E402
from app.repositories.workflow_event import WorkflowEventRecordRepository  # noqa: E402
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository  # noqa: E402
from app.repositories.workflow_instance import WorkflowInstanceRepository  # noqa: E402
from app.repositories.workflow_log import WorkflowLogRepository  # noqa: E402
from app.repositories.workflow_result import WorkflowResultRepository  # noqa: E402
from app.repositories.workflow_state import WorkflowStateTransitionRepository  # noqa: E402
from app.repositories.workflow_version import WorkflowVersionRepository  # noqa: E402
from app.services.approval import WorkflowApprovalService  # noqa: E402
from app.services.checkpoint import WorkflowCheckpointService  # noqa: E402
from app.services.compensation import WorkflowCompensationService  # noqa: E402
from app.services.compiler import compile_version  # noqa: E402
from app.services.definition import WorkflowDefinitionService  # noqa: E402
from app.services.event import WorkflowEventService  # noqa: E402
from app.services.execution import EventPublisher, WorkflowExecutionService  # noqa: E402
from app.services.instance import WorkflowInstanceService  # noqa: E402
from app.services.log import WorkflowLogService  # noqa: E402
from app.services.state import WorkflowStateTransitionService  # noqa: E402
from app.services.version import WorkflowVersionService  # noqa: E402

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

AUTOMATION_SERVICE_BASE_URL = "http://automation.internal"
PLAYBOOK_SERVICE_BASE_URL = "http://playbook.internal"
INVENTORY_SERVICE_BASE_URL = "http://inventory.internal"


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios_workflow_runtime",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 15 -- distinct from every other AI-IOS service's own test db."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=15,
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


def rabbitmq_test_settings() -> RabbitMQSettings:
    return RabbitMQSettings(
        rabbitmq_host="localhost",
        rabbitmq_port=5672,
        rabbitmq_user="aiios",
        rabbitmq_password="change-me",
        rabbitmq_vhost="/aiios",
        _env_file=None,
    )


@pytest_asyncio.fixture
async def real_queue_framework() -> AsyncIterator[QueueFramework]:
    """A real :class:`~shared_core.queue.factory.QueueFramework`, backing
    :class:`~shared_core.workflow.WorkflowTaskQueue` (``QUEUE`` nodes)
    and :func:`~app.workers.execution_worker.build_execution_worker`'s
    own queue-producer-shaped tests -- no in-memory fake.
    """
    try:
        framework = await asyncio.wait_for(
            create_queue_framework(rabbitmq_test_settings()), timeout=5
        )
    except UNREACHABLE_ERRORS as exc:
        pytest.skip(f"RabbitMQ is not reachable: {exc}")
    yield framework
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


async def make_definition(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    workflow_key: str = "test-workflow",
    name: str = "Test Workflow",
) -> WorkflowDefinition:
    """Create a bare :class:`WorkflowDefinition` row directly -- for
    tests exercising code paths that don't need the full
    :class:`WorkflowDefinitionService.create` side-effect chain
    (version compilation).
    """
    definition = WorkflowDefinition(
        organization_id=organization_id or uuid.uuid4(),
        project_id=project_id,
        workflow_key=workflow_key,
        name=name,
    )
    db_session.add(definition)
    await db_session.flush()
    return definition


def linear_nodes_and_edges() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A minimal, real, compilable ``START -> TASK -> END`` DAG shape."""
    nodes: list[dict[str, Any]] = [
        {"node_id": "start", "node_type": "start", "name": "start"},
        {
            "node_id": "task",
            "node_type": "task",
            "name": "task",
            "config": {"job_id": str(uuid.uuid4())},
        },
        {"node_id": "end", "node_type": "end", "name": "end"},
    ]
    edges: list[dict[str, Any]] = [
        {"from_node_id": "start", "to_node_id": "task"},
        {"from_node_id": "task", "to_node_id": "end"},
    ]
    return nodes, edges


async def make_version(
    db_session: AsyncSession,
    definition: WorkflowDefinition,
    *,
    version_number: str = "1.0.0",
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
) -> WorkflowVersion:
    """Create a bare, already-compiled :class:`WorkflowVersion` row
    directly, using :func:`linear_nodes_and_edges` by default.
    """
    default_nodes, default_edges = linear_nodes_and_edges()
    version = WorkflowVersion(
        organization_id=definition.organization_id,
        definition_id=definition.id,
        version_number=version_number,
        nodes=nodes if nodes is not None else default_nodes,
        edges=edges if edges is not None else default_edges,
        compiled_execution_plan=[],
    )
    compiled = compile_version(definition, version)
    version.compiled_execution_plan = compiled.execution_plan
    db_session.add(version)
    await db_session.flush()
    definition.current_version_number = version_number
    await db_session.flush()
    return version


async def make_instance(
    db_session: AsyncSession,
    definition: WorkflowDefinition,
    version: WorkflowVersion,
    *,
    status: WorkflowInstanceStatus = WorkflowInstanceStatus.QUEUED,
    trigger_type: WorkflowTriggerType = WorkflowTriggerType.MANUAL,
    triggered_by: uuid.UUID | None = None,
) -> WorkflowInstance:
    """Create a bare :class:`WorkflowInstance` row directly."""
    instance = WorkflowInstance(
        organization_id=definition.organization_id,
        project_id=definition.project_id,
        definition_id=definition.id,
        version_id=version.id,
        status=status,
        trigger_type=trigger_type,
        triggered_by=triggered_by,
    )
    db_session.add(instance)
    await db_session.flush()
    return instance


def build_version_service(db_session: AsyncSession) -> WorkflowVersionService:
    return WorkflowVersionService(WorkflowVersionRepository(db_session))


def build_definition_service(db_session: AsyncSession) -> WorkflowDefinitionService:
    return WorkflowDefinitionService(
        WorkflowDefinitionRepository(db_session), build_version_service(db_session)
    )


def build_instance_service(db_session: AsyncSession) -> WorkflowInstanceService:
    return WorkflowInstanceService(
        WorkflowInstanceRepository(db_session),
        WorkflowStateTransitionService(WorkflowStateTransitionRepository(db_session)),
    )


def build_execution_service(
    db_session: AsyncSession,
    *,
    http_client: AsyncClient,
    task_queue: WorkflowTaskQueue,
    publish_event: EventPublisher | None = None,
    approval_poll_interval_seconds: float = 0.05,
) -> WorkflowExecutionService:
    """Assemble a real, fully-wired :class:`WorkflowExecutionService`
    bound to *db_session* -- the shared wiring nearly every
    execution-touching service test needs, matching ``app/core
    /factory.py``'s own dependency-graph shape.
    """

    async def _noop_publish(_event: object) -> None:
        return None

    return WorkflowExecutionService(
        WorkflowInstanceRepository(db_session),
        WorkflowExecutionStepRepository(db_session),
        WorkflowResultRepository(db_session),
        build_definition_service(db_session),
        build_version_service(db_session),
        WorkflowStateTransitionService(WorkflowStateTransitionRepository(db_session)),
        WorkflowLogService(WorkflowLogRepository(db_session)),
        WorkflowEventService(WorkflowEventRecordRepository(db_session)),
        WorkflowApprovalService(WorkflowApprovalRepository(db_session)),
        WorkflowCheckpointService(WorkflowCheckpointRepository(db_session)),
        WorkflowCompensationService(WorkflowCompensationRepository(db_session)),
        http_client,
        task_queue,
        automation_service_base_url=AUTOMATION_SERVICE_BASE_URL,
        publish_event=publish_event or _noop_publish,
        approval_poll_interval_seconds=approval_poll_interval_seconds,
        max_loop_iterations=1000,
    )


def utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "AUTOMATION_SERVICE_BASE_URL",
    "INVENTORY_SERVICE_BASE_URL",
    "PLAYBOOK_SERVICE_BASE_URL",
    "AuthHeadersFn",
    "app",
    "auth_headers",
    "build_definition_service",
    "build_execution_service",
    "build_instance_service",
    "build_version_service",
    "client",
    "db_session",
    "jwt_keypair",
    "linear_nodes_and_edges",
    "make_definition",
    "make_instance",
    "make_version",
    "pg_engine",
    "postgres_test_settings",
    "rabbitmq_test_settings",
    "real_queue_framework",
    "real_redis_client",
    "redis_test_settings",
    "token_for",
    "utcnow",
]
