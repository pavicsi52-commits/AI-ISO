"""Shared fixtures for integration-style tests against real infrastructure
started by the repository's root ``docker-compose.yml`` (Phase 1).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from aio_pika.abc import AbstractRobustConnection
from aio_pika.exceptions import AMQPConnectionError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared_core.config.settings import (
    DatabaseSettings,
    MinioSettings,
    RabbitMQSettings,
    RedisSettings,
)
from shared_core.database.engine import create_engine
from shared_core.queue import QueueManager, create_connection
from shared_core.storage import StorageWrapper, create_minio_client
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from urllib3.exceptions import MaxRetryError

# Deliberately narrow: only treat genuine unreachability (refused connection,
# DNS failure, timeout) as "skip this test". A protocol-level error (bad
# credentials, missing vhost) is a real bug and should fail loudly instead
# of being silently skipped -- that's exactly how the vhost-encoding bug in
# RabbitMQSettings.url was originally caught.
RABBITMQ_UNREACHABLE_ERRORS = (AMQPConnectionError, ConnectionError, OSError, TimeoutError)


def rabbitmq_test_settings() -> RabbitMQSettings:
    """RabbitMQ connection settings matching the repo's docker-compose.yml."""
    return RabbitMQSettings(
        rabbitmq_host="localhost",
        rabbitmq_port=5672,
        rabbitmq_user="aiios",
        rabbitmq_password="change-me",
        rabbitmq_vhost="/aiios",
        _env_file=None,
    )


@pytest.fixture
async def rabbitmq_connection() -> AsyncIterator[AbstractRobustConnection]:
    try:
        conn = await create_connection(rabbitmq_test_settings())
    except RABBITMQ_UNREACHABLE_ERRORS as exc:
        pytest.skip(f"RabbitMQ is not reachable: {exc}")
    yield conn
    await conn.close()


@pytest.fixture
def queue_manager(rabbitmq_connection: AbstractRobustConnection) -> QueueManager:
    return QueueManager(rabbitmq_connection)


def minio_test_settings() -> MinioSettings:
    """MinIO connection settings matching the repo's docker-compose.yml."""
    return MinioSettings(
        minio_host="localhost",
        minio_port=9000,
        minio_access_key="aiios",
        minio_secret_key="change-me-min-8-chars",
        minio_use_ssl=False,
        _env_file=None,
    )


@pytest.fixture
async def storage() -> StorageWrapper:
    client = create_minio_client(minio_test_settings())
    wrapper = StorageWrapper(client)
    try:
        await asyncio.wait_for(wrapper.ensure_bucket("test-bucket"), timeout=5)
    except (MaxRetryError, OSError, TimeoutError) as exc:
        pytest.skip(f"MinIO is not reachable: {exc}")
    return wrapper


def postgres_test_settings() -> DatabaseSettings:
    """PostgreSQL connection settings matching the repo's docker-compose.yml.

    Host-side port 5433, not the Postgres-standard 5432 -- this machine has
    a native PostgreSQL 16 Windows service already bound to 5432, which was
    silently intercepting host-side connections meant for the
    ``aiios_postgres`` container.
    """
    return DatabaseSettings(
        database_host="localhost",
        database_port=5433,
        database_name="aiios",
        database_user="aiios",
        database_password="change-me",
        _env_file=None,
    )


@pytest.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """A real engine against the docker-compose PostgreSQL instance.

    Skips (rather than fails) the test if Postgres is unreachable -- the
    same "genuine unreachability only" policy as ``rabbitmq_connection``
    above.
    """
    engine = create_engine(postgres_test_settings())
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=5)
    except (OSError, TimeoutError, ConnectionError) as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    yield engine
    await engine.dispose()


def redis_test_settings() -> RedisSettings:
    """Redis connection settings matching the repo's docker-compose.yml."""
    return RedisSettings(
        redis_host="localhost",
        redis_port=6379,
        redis_password="change-me",
        redis_db=0,
        _env_file=None,
    )


@pytest.fixture
async def real_redis_client() -> AsyncIterator[Redis]:
    """A real client against the docker-compose Redis instance.

    Named distinctly from the ``redis_client`` fixture several existing
    test files define locally (backed by ``fakeredis.FakeAsyncRedis``) --
    this one is genuinely networked. Skips (rather than fails) the test if
    Redis is unreachable -- the same "genuine unreachability only" policy
    as ``rabbitmq_connection``/``pg_engine`` above.
    """
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
    except (RedisError, OSError, TimeoutError) as exc:
        await client.aclose()
        pytest.skip(f"Redis is not reachable: {exc}")
    yield client
    await client.flushdb()
    await client.aclose()
