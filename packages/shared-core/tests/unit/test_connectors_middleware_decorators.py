"""Tests for middleware.py and decorators.py."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.connectors import metrics as connector_metrics
from shared_core.connectors.base import BaseConnector
from shared_core.connectors.connection import ConnectionConfig
from shared_core.connectors.credentials import Credential, username_password
from shared_core.connectors.decorators import connector, get_provider_name, retryable, timed
from shared_core.connectors.exceptions import (
    AuthenticationFailedError,
    CircuitBreakerOpenError,
    ConnectorValidationError,
)
from shared_core.connectors.middleware import (
    Handler,
    Middleware,
    OperationContext,
    apply_middleware,
    audit_middleware,
    build_authentication_middleware,
    build_retry_middleware,
    build_security_middleware,
    build_telemetry_middleware,
    logging_middleware,
    metrics_collection_middleware,
    validation_middleware,
)
from shared_core.connectors.retry import CircuitBreaker
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.queue.retry import RetryPolicy


def _provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _context(**overrides: object) -> OperationContext:
    defaults: dict[str, object] = {"provider": "ssh", "target": "10.0.0.1", "operation": "connect"}
    defaults.update(overrides)
    return OperationContext(**defaults)  # type: ignore[arg-type]


async def _ok_handler(_context: OperationContext) -> str:
    return "ok"


# --- middleware.py ---


async def test_apply_middleware_runs_outermost_first() -> None:
    calls: list[str] = []

    async def outer(context: OperationContext, next_handler: Handler[str]) -> str:
        calls.append("outer-before")
        result = await next_handler(context)
        calls.append("outer-after")
        return result

    async def inner(context: OperationContext, next_handler: Handler[str]) -> str:
        calls.append("inner-before")
        result = await next_handler(context)
        calls.append("inner-after")
        return result

    handler = apply_middleware(_ok_handler, [outer, inner])
    await handler(_context())

    assert calls == ["outer-before", "inner-before", "inner-after", "outer-after"]


async def test_logging_middleware_calls_through() -> None:
    result = await logging_middleware(_context(), _ok_handler)

    assert result == "ok"


async def test_logging_middleware_logs_and_reraises_on_failure() -> None:
    async def failing(_context: OperationContext) -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await logging_middleware(_context(), failing)


async def test_validation_middleware_passes_through_without_a_config() -> None:
    result = await validation_middleware(_context(), _ok_handler)

    assert result == "ok"


async def test_validation_middleware_rejects_an_invalid_config() -> None:
    context = _context(config=ConnectionConfig(host="   "))

    with pytest.raises(ConnectorValidationError):
        await validation_middleware(context, _ok_handler)


async def test_metrics_collection_middleware_records_success() -> None:
    before = connector_metrics.connector_success_total.labels(provider="ssh")._value.get()

    await metrics_collection_middleware(_context(), _ok_handler)

    after = connector_metrics.connector_success_total.labels(provider="ssh")._value.get()
    assert after == before + 1


async def test_metrics_collection_middleware_records_failure() -> None:
    async def failing(_context: OperationContext) -> str:
        raise RuntimeError("boom")

    before = connector_metrics.connector_failure_total.labels(provider="ssh")._value.get()

    with pytest.raises(RuntimeError):
        await metrics_collection_middleware(_context(), failing)

    after = connector_metrics.connector_failure_total.labels(provider="ssh")._value.get()
    assert after == before + 1


@pytest.mark.parametrize(
    "operation", ["connect", "disconnect", "discover", "collect_inventory", "execute"]
)
async def test_audit_middleware_handles_every_known_operation(operation: str) -> None:
    result = await audit_middleware(_context(operation=operation, detail="uptime"), _ok_handler)

    assert result == "ok"


async def test_audit_middleware_audits_failure() -> None:
    async def failing(_context: OperationContext) -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await audit_middleware(_context(), failing)


async def test_build_authentication_middleware_authenticates_when_credential_given() -> None:
    called_with: list[Credential] = []

    async def authenticator(credential: Credential) -> None:
        called_with.append(credential)

    middleware: Middleware[str] = build_authentication_middleware(authenticator)
    context = _context(credential=username_password("admin", "hunter2"))

    result = await middleware(context, _ok_handler)

    assert result == "ok"
    assert len(called_with) == 1


async def test_build_authentication_middleware_skips_without_a_credential() -> None:
    async def authenticator(_credential: Credential) -> None:
        raise AssertionError("should not be called")

    middleware: Middleware[str] = build_authentication_middleware(authenticator)

    result = await middleware(_context(), _ok_handler)

    assert result == "ok"


async def test_build_authentication_middleware_propagates_failure() -> None:
    async def authenticator(_credential: Credential) -> None:
        raise RuntimeError("bad creds")

    middleware: Middleware[str] = build_authentication_middleware(authenticator)
    context = _context(credential=username_password("admin", "wrong"))

    with pytest.raises(AuthenticationFailedError):
        await middleware(context, _ok_handler)


async def test_build_telemetry_middleware_creates_a_span() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)
    middleware: Middleware[str] = build_telemetry_middleware(tracer)

    result = await middleware(_context(), _ok_handler)

    assert result == "ok"
    assert len(exporter.get_finished_spans()) == 1


async def test_build_retry_middleware_retries_then_succeeds() -> None:
    calls = 0

    async def flaky(_context: OperationContext) -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RuntimeError("transient")
        return "ok"

    middleware: Middleware[str] = build_retry_middleware(
        policy=RetryPolicy(max_attempts=3, backoff_base_seconds=0.001, backoff_max_seconds=0.01)
    )

    result = await middleware(_context(), flaky)

    assert result == "ok"
    assert calls == 2


async def test_build_retry_middleware_exhausts_and_raises() -> None:
    async def always_fails(_context: OperationContext) -> str:
        raise RuntimeError("permanent")

    middleware: Middleware[str] = build_retry_middleware(
        policy=RetryPolicy(max_attempts=2, backoff_base_seconds=0.001, backoff_max_seconds=0.01)
    )

    with pytest.raises(RuntimeError, match="permanent"):
        await middleware(_context(), always_fails)


async def test_build_retry_middleware_integrates_with_a_circuit_breaker() -> None:
    breaker = CircuitBreaker(failure_threshold=1)
    middleware: Middleware[str] = build_retry_middleware(
        policy=RetryPolicy(max_attempts=1), circuit_breaker=breaker
    )

    async def always_fails(_context: OperationContext) -> str:
        raise RuntimeError("permanent")

    with pytest.raises(RuntimeError):
        await middleware(_context(), always_fails)

    with pytest.raises(CircuitBreakerOpenError):
        await middleware(_context(), _ok_handler)


async def test_build_security_middleware_denies_when_checker_rejects() -> None:
    async def checker(_context: OperationContext) -> bool:
        return False

    middleware: Middleware[str] = build_security_middleware(checker)

    with pytest.raises(AuthorizationError):
        await middleware(_context(), _ok_handler)


async def test_build_security_middleware_allows_when_checker_approves() -> None:
    async def checker(_context: OperationContext) -> bool:
        return True

    middleware: Middleware[str] = build_security_middleware(checker)

    result = await middleware(_context(), _ok_handler)

    assert result == "ok"


# --- decorators.py ---


def test_connector_decorator_sets_the_provider_name() -> None:
    @connector("fake-provider")
    class _Fake(BaseConnector):
        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def validate(self) -> bool:
            return True

        async def execute(self, command: str, **kwargs: object) -> object:  # type: ignore[override]
            raise NotImplementedError

        async def health(self) -> object:  # type: ignore[override]
            raise NotImplementedError

        async def collect_inventory(self) -> object:  # type: ignore[override]
            raise NotImplementedError

        async def discover(self) -> object:  # type: ignore[override]
            raise NotImplementedError

    assert get_provider_name(_Fake) == "fake-provider"
    assert _Fake.provider_name == "fake-provider"


def test_get_provider_name_returns_none_when_undecorated() -> None:
    class _Bare(BaseConnector):
        async def connect(self) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def validate(self) -> bool:
            return True

        async def execute(self, command: str, **kwargs: object) -> object:  # type: ignore[override]
            raise NotImplementedError

        async def health(self) -> object:  # type: ignore[override]
            raise NotImplementedError

        async def collect_inventory(self) -> object:  # type: ignore[override]
            raise NotImplementedError

        async def discover(self) -> object:  # type: ignore[override]
            raise NotImplementedError

    assert get_provider_name(_Bare) is None


async def test_retryable_retries_then_succeeds() -> None:
    calls = 0

    @retryable(max_attempts=3)
    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RuntimeError("transient")
        return "ok"

    result = await flaky()

    assert result == "ok"
    assert calls == 2


async def test_retryable_exhausts_and_raises() -> None:
    @retryable(max_attempts=2)
    async def always_fails() -> str:
        raise RuntimeError("permanent")

    with pytest.raises(RuntimeError, match="permanent"):
        await always_fails()


async def test_timed_records_success() -> None:
    before = connector_metrics.connector_success_total.labels(provider="ssh")._value.get()

    @timed("ssh")
    async def op() -> str:
        return "ok"

    result = await op()

    after = connector_metrics.connector_success_total.labels(provider="ssh")._value.get()
    assert result == "ok"
    assert after == before + 1


async def test_timed_records_failure() -> None:
    before = connector_metrics.connector_failure_total.labels(provider="ssh")._value.get()

    @timed("ssh")
    async def op() -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await op()

    after = connector_metrics.connector_failure_total.labels(provider="ssh")._value.get()
    assert after == before + 1
