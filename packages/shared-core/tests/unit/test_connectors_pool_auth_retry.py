"""Tests for pool.py, authentication.py, retry.py, ratelimit.py, and timeout.py."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from shared_core.cache.manager import CacheManager
from shared_core.connectors.authentication import authenticate
from shared_core.connectors.base import (
    BaseConnector,
    CommandResult,
    ConnectorCapability,
)
from shared_core.connectors.connection import ConnectionConfig, ConnectionState
from shared_core.connectors.credentials import Credential, CredentialType, username_password
from shared_core.connectors.discovery import DiscoveryResult
from shared_core.connectors.exceptions import (
    AuthenticationFailedError,
    CircuitBreakerOpenError,
    ConnectorTimeoutError,
    ConnectorValidationError,
)
from shared_core.connectors.health import ConnectorHealthReport, build_health_report
from shared_core.connectors.inventory import InventoryReport
from shared_core.connectors.pool import ConnectorPool
from shared_core.connectors.ratelimit import build_connector_rate_limiters
from shared_core.connectors.retry import CircuitBreaker, CircuitState, connector_retry_policy
from shared_core.connectors.timeout import with_timeout


class _FakeConnector(BaseConnector):
    capabilities = frozenset({ConnectorCapability.EXECUTE})

    def __init__(self) -> None:
        super().__init__(ConnectionConfig(host="10.0.0.1"), username_password("admin", "hunter2"))
        self.disconnected = False

    async def connect(self) -> None:
        self.state = ConnectionState.CONNECTED

    async def disconnect(self) -> None:
        self.disconnected = True
        self.state = ConnectionState.DISCONNECTED

    async def validate(self) -> bool:
        return True

    async def execute(self, command: str, **kwargs: object) -> CommandResult:
        return CommandResult(command=command, exit_code=0)

    async def health(self) -> ConnectorHealthReport:
        return build_health_report(
            connection_state=self.state, authenticated=True, protocol_ok=True
        )

    async def collect_inventory(self) -> InventoryReport:
        return InventoryReport(host=self.config.host)

    async def discover(self) -> DiscoveryResult:
        return DiscoveryResult(host=self.config.host, reachable=True)


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


# --- pool.py ---


async def test_acquire_creates_a_new_connector() -> None:
    async def factory() -> BaseConnector:
        return _FakeConnector()

    pool = ConnectorPool(factory, max_size=2)

    connector = await pool.acquire()

    assert isinstance(connector, _FakeConnector)
    assert pool.size == 1


async def test_release_then_acquire_reuses_the_same_instance() -> None:
    created = []

    async def factory() -> BaseConnector:
        instance = _FakeConnector()
        created.append(instance)
        return instance

    pool = ConnectorPool(factory, max_size=2)
    first = await pool.acquire()
    await pool.release(first)

    second = await pool.acquire()

    assert second is first
    assert len(created) == 1


async def test_acquire_blocks_until_max_size_then_reuses_on_release() -> None:
    async def factory() -> BaseConnector:
        return _FakeConnector()

    pool = ConnectorPool(factory, max_size=1, acquire_timeout_seconds=5)
    first = await pool.acquire()

    async def release_soon() -> None:
        await asyncio.sleep(0.05)
        await pool.release(first)

    releaser = asyncio.create_task(release_soon())
    second = await pool.acquire()
    await releaser

    assert second is first


async def test_acquire_times_out_when_pool_is_exhausted() -> None:
    async def factory() -> BaseConnector:
        return _FakeConnector()

    pool = ConnectorPool(factory, max_size=1, acquire_timeout_seconds=0.05)
    await pool.acquire()

    with pytest.raises(ConnectorTimeoutError):
        await pool.acquire()


async def test_discard_disconnects_and_frees_a_slot() -> None:
    async def factory() -> BaseConnector:
        return _FakeConnector()

    pool = ConnectorPool(factory, max_size=1, acquire_timeout_seconds=1)
    connector = await pool.acquire()

    await pool.discard(connector)

    assert pool.size == 0
    assert connector.disconnected is True  # type: ignore[attr-defined]
    await pool.acquire()  # doesn't time out now that a slot is free


async def test_close_disconnects_every_idle_connector() -> None:
    async def factory() -> BaseConnector:
        return _FakeConnector()

    pool = ConnectorPool(factory, max_size=2)
    connector = await pool.acquire()
    await pool.release(connector)

    await pool.close()

    assert connector.disconnected is True  # type: ignore[attr-defined]
    assert pool.size == 0


async def test_connector_context_manager_acquires_and_releases() -> None:
    async def factory() -> BaseConnector:
        return _FakeConnector()

    pool = ConnectorPool(factory, max_size=1)

    async with pool.connector() as connector:
        assert isinstance(connector, _FakeConnector)

    assert pool.size == 1  # released back to idle, not discarded


async def test_acquire_frees_the_slot_when_the_factory_raises() -> None:
    calls = 0

    async def failing_factory() -> BaseConnector:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        return _FakeConnector()

    pool = ConnectorPool(failing_factory, max_size=1, acquire_timeout_seconds=1)

    with pytest.raises(RuntimeError):
        await pool.acquire()

    assert pool.size == 0
    connector = await pool.acquire()
    assert isinstance(connector, _FakeConnector)


# --- authentication.py ---


async def test_authenticate_succeeds() -> None:
    async def authenticator(_credential: Credential) -> None:
        return None

    result = await authenticate(username_password("admin", "hunter2"), authenticator)

    assert result.succeeded is True
    assert result.identity == "admin"


async def test_authenticate_rejects_an_incomplete_credential_before_calling_the_authenticator() -> (
    None
):
    called = False

    async def authenticator(_credential: Credential) -> None:
        nonlocal called
        called = True

    credential = Credential(credential_type=CredentialType.USERNAME_PASSWORD)

    with pytest.raises(ConnectorValidationError):
        await authenticate(credential, authenticator)
    assert called is False


async def test_authenticate_wraps_an_authenticator_failure() -> None:
    async def authenticator(_credential: Credential) -> None:
        raise RuntimeError("bad password")

    with pytest.raises(AuthenticationFailedError):
        await authenticate(username_password("admin", "wrong"), authenticator)


# --- retry.py ---


def test_connector_retry_policy_default_max_attempts() -> None:
    policy = connector_retry_policy()

    assert policy.max_attempts == 3


def test_circuit_breaker_starts_closed() -> None:
    breaker = CircuitBreaker()

    breaker.before_call()  # doesn't raise
    assert breaker.state == CircuitState.CLOSED


def test_circuit_breaker_opens_after_the_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2)

    breaker.record_failure()
    state_after_one_failure = breaker.state
    assert state_after_one_failure == CircuitState.CLOSED
    breaker.record_failure()

    state_after_two_failures = breaker.state
    assert state_after_two_failures == CircuitState.OPEN
    with pytest.raises(CircuitBreakerOpenError):
        breaker.before_call()


def test_circuit_breaker_half_opens_after_recovery_elapses() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=0.01)
    breaker.record_failure()
    state_before_recovery = breaker.state
    assert state_before_recovery == CircuitState.OPEN

    breaker._opened_at = breaker._opened_at - 1  # type: ignore[operator]

    state_after_recovery = breaker.state
    assert state_after_recovery == CircuitState.HALF_OPEN
    breaker.before_call()  # a trial call is allowed through


def test_circuit_breaker_half_open_success_closes_it() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=0.01)
    breaker.record_failure()
    breaker._opened_at = breaker._opened_at - 1  # type: ignore[operator]
    state_half_open = breaker.state
    assert state_half_open == CircuitState.HALF_OPEN

    breaker.record_success()

    state_after_success = breaker.state
    assert state_after_success == CircuitState.CLOSED


def test_circuit_breaker_half_open_failure_reopens_immediately() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=0.01)
    breaker.record_failure()
    breaker._opened_at = breaker._opened_at - 1  # type: ignore[operator]
    state_half_open = breaker.state
    assert state_half_open == CircuitState.HALF_OPEN
    # A high threshold and a reset failure count prove the reopen below comes
    # from being in HALF_OPEN specifically, not from re-hitting the threshold.
    breaker.failure_threshold = 10
    breaker._consecutive_failures = 0

    breaker.record_failure()

    state_after_second_failure = breaker.state
    assert state_after_second_failure == CircuitState.OPEN


# --- ratelimit.py, against real fakeredis ---


async def test_rate_limiter_scopes_are_isolated_by_the_same_literal_identifier(
    redis_client: FakeAsyncRedis,
) -> None:
    cache = CacheManager(redis_client)
    limiter = build_connector_rate_limiters(cache, max_requests=1, burst=0)

    connector_status = await limiter.check_connector("shared-name")
    target_status = await limiter.check_target("shared-name")

    assert connector_status.allowed is True
    assert target_status.allowed is True


async def test_rate_limiter_blocks_after_the_limit(redis_client: FakeAsyncRedis) -> None:
    cache = CacheManager(redis_client)
    limiter = build_connector_rate_limiters(cache, max_requests=1, burst=0)

    await limiter.check_organization("org-1")
    second = await limiter.check_organization("org-1")

    assert second.allowed is False


# --- timeout.py ---


async def test_with_timeout_returns_the_result_when_fast_enough() -> None:
    async def fast() -> str:
        return "done"

    result = await with_timeout(fast(), timeout_seconds=1, operation="fast op")

    assert result == "done"


async def test_with_timeout_raises_when_too_slow() -> None:
    async def slow() -> str:
        await asyncio.sleep(10)
        return "done"

    with pytest.raises(ConnectorTimeoutError):
        await with_timeout(slow(), timeout_seconds=0.01, operation="slow op")
