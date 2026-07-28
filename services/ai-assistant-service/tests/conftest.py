"""Shared fixtures for the AI assistant service's test suite.

Everything runs against real infrastructure (the repository root's
docker-compose Postgres/Redis/RabbitMQ) with per-test SAVEPOINT
isolation -- the discipline every prior AI-IOS service established.

**Model providers are the one thing not called for real.** Every test
that needs a completion injects a :class:`StubModelClient`, which is a
genuine :class:`~app.clients.base.ModelClient` implementation returning
scripted completions. That is deliberate and honest: calling a real
LLM would make the suite non-deterministic, slow, network-dependent,
and billable. The provider *clients* themselves are separately tested
against each vendor's own documented response shape via
``pytest-httpx``, so the wire format is genuinely verified -- only the
model's own creativity is stubbed.

Redis test db 19 -- distinct from every other AI-IOS service's own
(... 17 monitoring, 18 alerting).
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
from shared_core.config.settings import DatabaseSettings, RedisSettings
from shared_core.database.engine import create_engine
from shared_core.security.jwt import encode_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_LOOPBACK = "127.0.0.1"
"""The IPv4 literal, never the name ``localhost``.

On Windows ``localhost`` resolves to ``::1`` first, and Docker
Desktop's IPv6 forwarding hangs rather than refusing, so every
connection burns its full timeout instead of falling back. Diagnosed
and fixed during Prompt 045; see that service's own README.
"""

os.environ.setdefault("AIIOS_DATABASE_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_DATABASE_PORT", "5433")
os.environ.setdefault("AIIOS_DATABASE_NAME", "aiios_ai_assistant")
os.environ.setdefault("AIIOS_DATABASE_USER", "aiios")
os.environ.setdefault("AIIOS_DATABASE_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_REDIS_PORT", "6379")
os.environ.setdefault("AIIOS_REDIS_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_REDIS_DB", "19")
os.environ.setdefault("AIIOS_RABBITMQ_HOST", _LOOPBACK)
os.environ.setdefault("AIIOS_RABBITMQ_PORT", "5672")
os.environ.setdefault("AIIOS_RABBITMQ_USER", "aiios")
os.environ.setdefault("AIIOS_RABBITMQ_PASSWORD", "change-me")
os.environ.setdefault("AIIOS_RABBITMQ_VHOST", "/aiios")

_TEST_KEY_DIR = Path(tempfile.gettempdir()) / "aiios_ai_assistant_test_keys"
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

os.environ.setdefault("AIIOS_AI_ASSISTANT_SERVICE_JWT_PUBLIC_KEY_PATH", str(_TEST_PUBLIC_KEY_PATH))
os.environ.setdefault(
    "AIIOS_AI_ASSISTANT_SERVICE_INVENTORY_SERVICE_BASE_URL", "http://inventory.internal"
)
os.environ.setdefault(
    "AIIOS_AI_ASSISTANT_SERVICE_MONITORING_SERVICE_BASE_URL", "http://monitoring.internal"
)
os.environ.setdefault(
    "AIIOS_AI_ASSISTANT_SERVICE_ALERTING_SERVICE_BASE_URL", "http://alerting.internal"
)

from app.api import deps  # noqa: E402  -- see the env var block above
from app.clients.base import ChatCompletion, ChatMessage, ToolSpecification  # noqa: E402
from app.clients.registry import ModelRegistry  # noqa: E402
from app.core.factory import create_app  # noqa: E402
from app.models.ai_agent import AiAgent  # noqa: E402
from app.models.ai_conversation import AiConversation  # noqa: E402
from app.models.ai_tool import AiTool  # noqa: E402
from app.models.enums import (  # noqa: E402
    AgentType,
    ConversationStatus,
    ModelProvider,
    ToolKind,
)

UNREACHABLE_ERRORS = (OSError, TimeoutError, ConnectionError, RedisError)

INVENTORY_BASE_URL = "http://inventory.internal"
MONITORING_BASE_URL = "http://monitoring.internal"
ALERTING_BASE_URL = "http://alerting.internal"


def postgres_test_settings() -> DatabaseSettings:
    return DatabaseSettings(
        database_host=_LOOPBACK,
        database_port=5433,
        database_name="aiios_ai_assistant",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


def redis_test_settings() -> RedisSettings:
    """Test db 19 -- distinct from every other AI-IOS service's own."""
    return RedisSettings(
        redis_host=_LOOPBACK,
        redis_port=6379,
        redis_password="change-me",
        redis_db=19,
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
    """The test session's fixed RSA keypair."""
    return (
        _TEST_PRIVATE_KEY_PATH.read_text(encoding="ascii"),
        _TEST_PUBLIC_KEY_PATH.read_text(encoding="ascii"),
    )


@pytest.fixture
def token_for(jwt_keypair: tuple[str, str]) -> Callable[[uuid.UUID], str]:
    """Mint a valid access token for a given user id."""
    private_key, _public_key = jwt_keypair

    def _mint(user_id: uuid.UUID) -> str:
        return encode_token({"sub": str(user_id)}, private_key=private_key)

    return _mint


AuthHeadersFn = Callable[[uuid.UUID], dict[str, str]]


@pytest.fixture
def auth_headers(token_for: Callable[[uuid.UUID], str]) -> AuthHeadersFn:
    """Build ``Authorization`` headers for a given user id."""

    def _headers(user_id: uuid.UUID) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(user_id)}"}

    return _headers


class RecordingPublisher:
    """A real :data:`~app.types.EventPublisher` that records events.

    Not a mock: it is an awaitable callable with the right signature,
    so the publish path executes for real and tests can assert exactly
    which domain events a flow announced.
    """

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def __call__(self, event: Any) -> None:
        self.events.append(event)

    @property
    def names(self) -> list[str]:
        """The ``event_name`` of every event published, in order."""
        return [event.event_name for event in self.events]


class StubModelClient:
    """A real :class:`~app.clients.base.ModelClient` returning scripted replies.

    Not a mock object: it implements the protocol properly, records what
    it was asked, and can be scripted to request tool calls. That lets
    the orchestration logic be tested deterministically while the wire
    format is verified separately against each provider's own documented
    shape.
    """

    def __init__(
        self,
        replies: list[ChatCompletion] | None = None,
        *,
        provider: str = "stub",
        fail_with: Exception | None = None,
    ) -> None:
        self.provider = provider
        self._replies = list(replies or [])
        self._fail_with = fail_with
        self.calls: list[list[ChatMessage]] = []
        self.offered_tools: list[list[ToolSpecification] | None] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        tools: list[ToolSpecification] | None = None,
    ) -> ChatCompletion:
        self.calls.append(list(messages))
        self.offered_tools.append(tools)
        if self._fail_with is not None:
            raise self._fail_with
        if self._replies:
            return self._replies.pop(0)
        return ChatCompletion(
            content="stub answer",
            model=model,
            provider=self.provider,
            prompt_tokens=10,
            completion_tokens=5,
        )


def stub_registry(
    client: StubModelClient | None = None,
    *,
    provider: ModelProvider = ModelProvider.OLLAMA,
) -> tuple[ModelRegistry, StubModelClient]:
    """A :class:`ModelRegistry` backed by one stub client."""
    stub = client or StubModelClient()
    registry = ModelRegistry(
        {provider: stub}, default_provider=provider, default_model="stub-model"
    )
    return registry, stub


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """The real FastAPI app, started through its actual lifespan.

    The model registry is replaced with a stub *after* startup so the
    real lifespan (database, cache, events, notifications, key loading)
    is genuinely exercised, while chat turns stay deterministic.
    """
    application = create_app()
    async with application.router.lifespan_context(application):

        async def _override_db_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        application.dependency_overrides[deps.get_db_session] = _override_db_session
        registry, _stub = stub_registry()
        application.state.model_registry = registry
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def make_agent(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    agent_type: AgentType = AgentType.REASONING,
    provider: ModelProvider = ModelProvider.OLLAMA,
    tool_keys: list[str] | None = None,
    system_prompt: str | None = "You are a helpful infrastructure assistant.",
    enabled: bool = True,
) -> AiAgent:
    """Create a bare :class:`AiAgent` row directly."""
    agent = AiAgent(
        organization_id=organization_id or uuid.uuid4(),
        name=f"agent-{uuid.uuid4().hex[:8]}",
        agent_type=agent_type,
        provider=provider,
        model="stub-model",
        system_prompt=system_prompt,
        tool_keys=tool_keys if tool_keys is not None else [],
        enabled=enabled,
    )
    db_session.add(agent)
    await db_session.flush()
    return agent


async def make_tool(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    tool_key: str = "inventory_list_assets",
    tool_kind: ToolKind = ToolKind.INVENTORY_QUERY,
    parameters_schema: dict[str, Any] | None = None,
    required_permission: str | None = None,
    is_mutating: bool = False,
    enabled: bool = True,
) -> AiTool:
    """Create a bare :class:`AiTool` row directly."""
    tool = AiTool(
        organization_id=organization_id or uuid.uuid4(),
        tool_key=tool_key,
        name=tool_key.replace("_", " ").title(),
        description=f"Test tool {tool_key}.",
        tool_kind=tool_kind,
        parameters_schema=(
            parameters_schema
            if parameters_schema is not None
            else {
                "type": "object",
                "properties": {"organization_id": {"type": "string"}},
                "required": ["organization_id"],
                "additionalProperties": False,
            }
        ),
        required_permission=required_permission,
        is_mutating=is_mutating,
        enabled=enabled,
    )
    db_session.add(tool)
    await db_session.flush()
    return tool


async def make_conversation(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    status: ConversationStatus = ConversationStatus.ACTIVE,
) -> AiConversation:
    """Create a bare :class:`AiConversation` row directly."""
    conversation = AiConversation(
        organization_id=organization_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        title="Test conversation",
        status=status,
        started_at=datetime.now(UTC),
    )
    db_session.add(conversation)
    await db_session.flush()
    return conversation


__all__ = [
    "ALERTING_BASE_URL",
    "INVENTORY_BASE_URL",
    "MONITORING_BASE_URL",
    "AuthHeadersFn",
    "RecordingPublisher",
    "StubModelClient",
    "app",
    "auth_headers",
    "client",
    "db_session",
    "db_session_factory",
    "jwt_keypair",
    "make_agent",
    "make_conversation",
    "make_tool",
    "pg_engine",
    "postgres_test_settings",
    "real_redis_client",
    "redis_test_settings",
    "stub_registry",
    "token_for",
]
