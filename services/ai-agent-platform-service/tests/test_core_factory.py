"""Tests for :mod:`app.core.factory`.

Everything here runs against the **real** application factory and the
**real** lifespan -- real PostgreSQL, Redis, RabbitMQ, Neo4j, key
loading, and (in the one test that enables them) a real
``SchedulerManager`` wired to a real RabbitMQ queue. Nothing is mocked.

The ``app`` fixture from ``tests/conftest.py`` already boots the whole
lifespan once, which is what exercises ``_build_model_registry``,
``_build_graph_client``, ``_build_cors_config`` and the
workers-disabled branch of ``_build_workers``; those tests assert on
``app.state``. The workers-*enabled* branch needs its own app, because
``get_settings()`` is ``lru_cache``d and the setting is read once per
process -- see :func:`test_build_workers_registers_all_four_jobs`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from redis.asyncio import Redis
from shared_core.config.environment import Environment
from shared_core.config.settings import ApplicationSettings
from shared_core.exceptions.base import AIIOSException
from shared_core.scheduler import SchedulerManager
from shared_core.security.cors import CorsConfig
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from app.clients.registry import ModelRegistry
from app.config.settings import (
    AiAgentPlatformServiceSettings,
    Settings,
    build_settings,
    get_settings,
)
from app.core.factory import (
    _build_cors_config,
    _build_graph_client,
    _build_model_registry,
    _build_workers,
    create_app,
)
from app.graph.client import GraphClient
from app.models.enums import ModelProvider
from app.sandbox.policy import AgentSandboxPolicy
from app.workers.registrar import (
    BENCHMARK_SWEEP_JOB_ID,
    CHECKPOINT_RECOVERY_SWEEP_JOB_ID,
    STATISTICS_ROLLUP_JOB_ID,
    TASK_DISPATCH_SWEEP_JOB_ID,
)
from tests.conftest import RecordingPublisher

WORKERS_ENABLED_ENV = "AIIOS_AI_AGENT_PLATFORM_SERVICE_WORKERS_ENABLED"


def _settings(**service_overrides: object) -> Settings:
    """A real :class:`Settings`, with this service's own section overridden."""
    return build_settings(service=AiAgentPlatformServiceSettings(**service_overrides))


# ---- _build_model_registry -----------------------------------------------------


async def test_build_model_registry_uses_the_configured_default_provider(
    http_client: httpx.AsyncClient,
) -> None:
    registry = _build_model_registry(
        http_client, _settings(default_provider="vllm", default_model="mistral")
    )

    assert isinstance(registry, ModelRegistry)
    assert registry.get(ModelProvider.VLLM) is not None
    # Self-hosted providers need no credential, so they are always built.
    assert set(registry.available_providers) >= {
        ModelProvider.OLLAMA,
        ModelProvider.VLLM,
        ModelProvider.LOCAL,
    }


async def test_build_model_registry_includes_credentialed_providers_only(
    http_client: httpx.AsyncClient,
) -> None:
    without_keys = _build_model_registry(http_client, _settings(openai_api_key=""))
    with_key = _build_model_registry(http_client, _settings(openai_api_key="sk-test"))

    assert ModelProvider.OPENAI not in without_keys.available_providers
    assert ModelProvider.OPENAI in with_key.available_providers


# ---- _build_graph_client -------------------------------------------------------


async def test_build_graph_client_when_neo4j_is_enabled() -> None:
    driver, graph_client = _build_graph_client(
        _settings(neo4j_enabled=True, neo4j_database="neo4j", neo4j_max_records=42)
    )

    assert driver is not None
    assert isinstance(graph_client, GraphClient)
    assert graph_client.enabled is True
    assert graph_client.database == "neo4j"
    await driver.close()


def test_build_graph_client_when_neo4j_is_disabled() -> None:
    driver, graph_client = _build_graph_client(_settings(neo4j_enabled=False))

    assert driver is None
    assert graph_client.enabled is False


# ---- _build_cors_config --------------------------------------------------------


def test_build_cors_config_is_permissive_outside_production() -> None:
    settings = _settings()
    config = _build_cors_config(settings)

    assert isinstance(config, CorsConfig)
    assert config.allow_origins == ("*",)
    assert config.allow_credentials is False


def test_build_cors_config_is_strict_in_production() -> None:
    base = _settings(cors_allowed_origins=["https://app.example.com"])
    production = Settings(
        application=ApplicationSettings(environment=Environment.PRODUCTION),
        database=base.database,
        redis=base.redis,
        rabbitmq=base.rabbitmq,
        email=base.email,
        neo4j=base.neo4j,
        service=base.service,
    )

    config = _build_cors_config(production)

    assert config.allow_origins == ("https://app.example.com",)
    assert config.allow_credentials is True


def test_build_cors_config_treats_staging_as_non_production() -> None:
    base = _settings(cors_allowed_origins=["https://staging.example.com"])
    staging = Settings(
        application=ApplicationSettings(environment=Environment.STAGING),
        database=base.database,
        redis=base.redis,
        rabbitmq=base.rabbitmq,
        email=base.email,
        neo4j=base.neo4j,
        service=base.service,
    )

    assert _build_cors_config(staging).allow_origins == ("*",)


# ---- _build_workers ------------------------------------------------------------


async def test_build_workers_returns_none_when_disabled(
    db_session_factory: async_sessionmaker[AsyncSession],
    cache_framework: object,
    model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    """The early return: no RabbitMQ connection, no scheduler, nothing started."""
    _driver, graph_client = _build_graph_client(_settings(neo4j_enabled=False))

    manager = await _build_workers(
        db_session_factory,
        cache_framework.client,  # type: ignore[attr-defined]
        model_registry,
        http_client,
        sandbox_policy,
        graph_client,
        publisher,
        _settings(workers_enabled=False),
    )

    assert manager is None


@pytest_asyncio.fixture
async def workers_enabled_app() -> AsyncIterator[FastAPI]:
    """A second real app, booted with the workers genuinely switched on.

    ``get_settings()`` is ``lru_cache``d, so both the environment
    variable and the cache have to be restored afterwards or every later
    test in this session would inherit a scheduler-running app.
    """
    previous = os.environ.get(WORKERS_ENABLED_ENV)
    os.environ[WORKERS_ENABLED_ENV] = "true"
    get_settings.cache_clear()
    application = create_app()
    try:
        async with application.router.lifespan_context(application):
            yield application
    finally:
        if previous is None:
            os.environ.pop(WORKERS_ENABLED_ENV, None)
        else:
            os.environ[WORKERS_ENABLED_ENV] = previous
        get_settings.cache_clear()


async def test_build_workers_registers_all_four_leader_elected_jobs(
    workers_enabled_app: FastAPI,
) -> None:
    manager = workers_enabled_app.state.scheduler_manager

    assert isinstance(manager, SchedulerManager)
    jobs = {job.job_id: job for job in manager.registry.list_jobs()}
    assert set(jobs) == {
        TASK_DISPATCH_SWEEP_JOB_ID,
        CHECKPOINT_RECOVERY_SWEEP_JOB_ID,
        STATISTICS_ROLLUP_JOB_ID,
        BENCHMARK_SWEEP_JOB_ID,
    }
    # Registration is what computes the first due time.
    assert all(job.next_run is not None for job in jobs.values())
    assert manager.leader is not None, "all four jobs are leader-elected"

    settings = get_settings()
    assert jobs[TASK_DISPATCH_SWEEP_JOB_ID].schedule.interval is not None
    assert (
        jobs[TASK_DISPATCH_SWEEP_JOB_ID].schedule.interval.total_seconds()
        == settings.service.task_dispatch_sweep_seconds
    )
    assert (
        jobs[BENCHMARK_SWEEP_JOB_ID].schedule.interval.total_seconds()  # type: ignore[union-attr]
        == settings.service.benchmark_sweep_seconds
    )

    # Close the broker connection the scheduler framework opened; the
    # lifespan stops the manager but never owns that connection.
    await manager.queue._queue_manager._connection.close()


# ---- _lifespan / app.state -----------------------------------------------------


async def test_lifespan_populates_every_piece_of_app_state(app: FastAPI) -> None:
    state = app.state

    assert isinstance(state.db_engine, AsyncEngine)
    assert isinstance(state.db_session_factory, async_sessionmaker)
    assert state.cache_manager is not None
    assert isinstance(state.redis_client, Redis)
    assert callable(state.publish_event)
    assert state.jwt_public_key.startswith("-----BEGIN PUBLIC KEY-----")
    assert isinstance(state.service_settings, AiAgentPlatformServiceSettings)
    assert isinstance(state.http_client, httpx.AsyncClient)
    assert isinstance(state.model_registry, ModelRegistry)
    assert isinstance(state.graph_client, GraphClient)
    assert isinstance(state.sandbox_policy, AgentSandboxPolicy)


async def test_lifespan_leaves_the_scheduler_off_when_workers_are_disabled(app: FastAPI) -> None:
    """conftest sets ``WORKERS_ENABLED=false``, so the whole scheduler --
    and the RabbitMQ connection it would open -- is skipped."""
    assert app.state.service_settings.workers_enabled is False
    assert app.state.scheduler_manager is None


async def test_lifespan_builds_the_sandbox_policy_from_settings(app: FastAPI) -> None:
    settings = app.state.service_settings
    policy = app.state.sandbox_policy

    assert policy.execution_timeout_seconds == settings.default_execution_timeout_seconds
    assert policy.memory_limit_mb == settings.default_memory_limit_mb


async def test_lifespan_model_registry_matches_configured_defaults(app: FastAPI) -> None:
    settings = app.state.service_settings
    registry: ModelRegistry = app.state.model_registry

    assert registry.get(ModelProvider(settings.default_provider)) is not None


async def test_lifespan_http_client_is_open_and_usable(app: FastAPI) -> None:
    client: httpx.AsyncClient = app.state.http_client

    assert client.is_closed is False
    assert client.timeout.connect == app.state.service_settings.http_client_timeout_seconds


# ---- create_app ----------------------------------------------------------------


@pytest.fixture
def built_app() -> Iterator[FastAPI]:
    """A freshly built app, never started -- ``create_app`` only."""
    yield create_app()


def test_create_app_metadata(built_app: FastAPI) -> None:
    settings = get_settings()

    assert built_app.title == "AI-IOS Enterprise AI Agent Platform Service"
    assert built_app.version == settings.application.app_version
    assert built_app.docs_url == "/docs"
    assert built_app.openapi_url == "/openapi.json"


def test_create_app_installs_the_cors_middleware_from_the_cors_config(
    built_app: FastAPI,
) -> None:
    cors = [entry for entry in built_app.user_middleware if entry.cls is CORSMiddleware]

    assert len(cors) == 1
    expected = _build_cors_config(get_settings())
    assert cors[0].kwargs["allow_origins"] == list(expected.allow_origins)
    assert cors[0].kwargs["allow_credentials"] == expected.allow_credentials
    assert cors[0].kwargs["max_age"] == expected.max_age_seconds


def test_create_app_installs_every_shared_middleware(built_app: FastAPI) -> None:
    installed = {entry.cls.__name__ for entry in built_app.user_middleware}

    assert {
        "CORSMiddleware",
        "RequestContextMiddleware",
        "LocalizationMiddleware",
        "RequestValidationMiddleware",
        "SecurityHeadersMiddleware",
    } <= installed


def test_create_app_includes_the_domain_routers_and_metrics(built_app: FastAPI) -> None:
    paths = set(built_app.openapi()["paths"])

    assert "/metrics" in paths
    assert "/health" in paths
    assert "/agents" in paths
    assert "/agents/tasks" in paths
    assert "/agents/{agent_id}/execute" in paths


def test_create_app_registers_the_shared_exception_handlers(built_app: FastAPI) -> None:
    handled = set(built_app.exception_handlers)

    assert AIIOSException in handled
    assert RequestValidationError in handled
    assert StarletteHTTPException in handled
