"""ProxyService: the reverse-proxy orchestrator -- the gateway's core feature.

Against real PostgreSQL and a real, ASGI-backed fake upstream
(``tests/conftest.py``'s ``fake_backend_app``, served through
``httpx.ASGITransport``) -- every proxied call in this file makes a
genuine HTTP request/response round trip. Nothing here mocks
``ProxyService`` itself or its own collaborators (routing, load
balancing, health/circuit state, rate limiting, quotas, transformation);
only the network hop past the gateway's own outbound HTTP client is
substituted, exactly as ``tests/conftest.py``'s own module docstring
describes.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.models.enums import (
    CircuitBreakerState,
    HealthState,
    QuotaKind,
    QuotaScope,
    RateLimitScope,
    TransformationDirection,
    TransformationKind,
)
from app.models.health import ApiServiceHealth
from app.services.proxy import ProxyError, ProxyResult, ProxyService
from tests.conftest import FAKE_BACKEND_URL, HTTP_OK


async def _proxy(
    proxy_service: ProxyService, organization_id: uuid.UUID, **overrides: object
) -> ProxyResult:
    """Call ``proxy_service.proxy`` with sensible defaults for every required kwarg."""
    kwargs: dict[str, object] = {
        "method": "GET",
        "path": "/echo",
        "query_string": None,
        "headers": {},
        "body": b"",
        "source_ip": "127.0.0.1",
        "client_id": None,
        "api_key_id": None,
        "authenticated_user_id": None,
        "auth_method": None,
    }
    kwargs.update(overrides)
    return await proxy_service.proxy(organization_id, **kwargs)  # type: ignore[arg-type]


class TestProxySuccess:
    async def test_get_round_trip_returns_the_echoed_body(
        self, proxy_service, make_service, make_route, organization_id
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])

        result = await _proxy(proxy_service, organization_id)

        assert result.status_code == HTTP_OK
        echoed = json.loads(result.body)
        assert echoed["method"] == "GET"
        assert echoed["path"] == "/echo"

    async def test_post_round_trip_forwards_the_body_unchanged(
        self, proxy_service, make_service, make_route, organization_id
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["post"])

        result = await _proxy(proxy_service, organization_id, method="POST", body=b'{"a": 1}')

        echoed = json.loads(result.body)
        assert echoed["method"] == "POST"
        assert echoed["body"] == '{"a": 1}'

    async def test_query_string_is_forwarded_to_the_upstream(
        self, proxy_service, make_service, make_route, organization_id
    ) -> None:
        """Regression test.

        ``_forward`` used to build ``target_url`` from the resolved
        target *path* alone and never looked at the caller's own query
        string at all -- every proxied call silently dropped
        ``?page=2``, ``?id=...``, and so on. Fixed in
        ``app/services/proxy.py`` by threading ``query_string`` through
        ``_forward`` and appending it to ``target_url``.
        """
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])

        result = await _proxy(proxy_service, organization_id, query_string="foo=bar&baz=qux")

        echoed = json.loads(result.body)
        assert echoed["query"] == "foo=bar&baz=qux"

    async def test_no_query_string_forwards_none(
        self, proxy_service, make_service, make_route, organization_id
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])

        result = await _proxy(proxy_service, organization_id, query_string=None)

        echoed = json.loads(result.body)
        assert echoed["query"] == ""

    async def test_request_and_response_logs_are_persisted(
        self,
        proxy_service,
        make_service,
        make_route,
        organization_id,
        request_logs_repo,
        response_logs_repo,
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])

        result = await _proxy(proxy_service, organization_id)

        stored_request = await request_logs_repo.require_by_id(result.request_log.id)
        assert stored_request.method == "GET"
        assert stored_request.path == "/echo"
        assert stored_request.organization_id == organization_id

        stored_response = await response_logs_repo.require_by_id(result.response_log.id)
        assert stored_response.status_code == HTTP_OK
        assert stored_response.upstream_instance == FAKE_BACKEND_URL

    async def test_publishes_received_and_completed_events_in_order(
        self, proxy_service, make_service, make_route, organization_id, publisher
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])

        await _proxy(proxy_service, organization_id)

        assert publisher.names == ["ApiRequestReceived", "ApiRequestCompleted"]

    async def test_host_header_is_stripped_and_replaced_with_the_upstreams_own(
        self, proxy_service, make_service, make_route, organization_id
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])

        result = await _proxy(
            proxy_service, organization_id, headers={"Host": "should-be-stripped.example"}
        )

        echoed = json.loads(result.body)
        forwarded_headers = {k.lower(): v for k, v in echoed["headers"].items()}
        assert forwarded_headers.get("host") == "backend.test"
        assert "x-correlation-id" in forwarded_headers

    async def test_rewrite_path_changes_the_forwarded_path(
        self, proxy_service, make_service, make_route, organization_id
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/legacy", methods=["get"], rewrite_path="/echo")

        result = await _proxy(proxy_service, organization_id, path="/legacy")

        echoed = json.loads(result.body)
        assert echoed["path"] == "/echo"

    async def test_strip_prefix_changes_the_forwarded_path(
        self, proxy_service, make_service, make_route, organization_id
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/api/**", methods=["get"], strip_prefix=True)

        result = await _proxy(proxy_service, organization_id, path="/api/echo")

        echoed = json.loads(result.body)
        assert echoed["path"] == "/echo"

    async def test_request_direction_header_transformation_is_applied(
        self, proxy_service, make_service, make_route, transformation_service, organization_id
    ) -> None:
        service = await make_service()
        route = await make_route(service.id, path_pattern="/echo", methods=["get"])
        await transformation_service.create(
            organization_id,
            name="inject-request-header",
            kind=TransformationKind.HEADER,
            direction=TransformationDirection.REQUEST,
            route_id=route.id,
            config={"add": {"X-Injected": "yes"}},
        )

        result = await _proxy(proxy_service, organization_id)

        echoed = json.loads(result.body)
        forwarded_headers = {k.lower(): v for k, v in echoed["headers"].items()}
        assert forwarded_headers.get("x-injected") == "yes"

    async def test_response_direction_header_transformation_is_applied(
        self, proxy_service, make_service, make_route, transformation_service, organization_id
    ) -> None:
        service = await make_service()
        route = await make_route(service.id, path_pattern="/echo", methods=["get"])
        await transformation_service.create(
            organization_id,
            name="inject-response-header",
            kind=TransformationKind.HEADER,
            direction=TransformationDirection.RESPONSE,
            route_id=route.id,
            config={"add": {"X-Resp-Injected": "yes"}},
        )

        result = await _proxy(proxy_service, organization_id)

        assert result.headers.get("X-Resp-Injected") == "yes"

    async def test_body_transformation_rules_never_touch_the_proxied_body(
        self, proxy_service, make_service, make_route, transformation_service, organization_id
    ) -> None:
        """Documented scope boundary (``proxy.py``'s own module docstring):
        the proxy path never parses the body, so a configured ``BODY``
        rule -- real, tested code at the ``TransformationService`` level
        -- must have zero effect on what actually crosses the wire.
        """
        service = await make_service()
        route = await make_route(service.id, path_pattern="/echo", methods=["post"])
        await transformation_service.create(
            organization_id,
            name="body-rule-must-be-inert-on-the-proxy-path",
            kind=TransformationKind.BODY,
            direction=TransformationDirection.REQUEST,
            route_id=route.id,
            config={"add": {"injected": "should-not-appear"}},
        )

        result = await _proxy(proxy_service, organization_id, method="POST", body=b'{"a": 1}')

        echoed = json.loads(result.body)
        assert echoed["body"] == '{"a": 1}'

    async def test_successful_call_records_a_circuit_breaker_success(
        self, proxy_service, make_service, make_route, health_monitor_service, organization_id
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])
        health_monitor_service.breaker_for(FAKE_BACKEND_URL).record_failure()

        await _proxy(proxy_service, organization_id)

        assert health_monitor_service.circuit_state(FAKE_BACKEND_URL) == CircuitBreakerState.CLOSED

    async def test_client_id_is_recorded_on_the_persisted_request_log(
        self,
        proxy_service,
        make_service,
        make_route,
        make_client,
        organization_id,
        request_logs_repo,
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])
        client = await make_client()

        result = await _proxy(proxy_service, organization_id, client_id=client.id)

        stored_request = await request_logs_repo.require_by_id(result.request_log.id)
        assert stored_request.client_id == client.id


class TestProxyBackendErrorPassthrough:
    async def test_a_genuine_backend_500_is_passed_through_unchanged(
        self, proxy_service, make_service, make_route, organization_id
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/error", methods=["get"])

        result = await _proxy(proxy_service, organization_id, path="/error")

        assert result.status_code == 500
        assert json.loads(result.body) == {"detail": "backend failure"}
        # A genuine backend error response is not a proxy-level refusal:
        # no `_log_refusal` flags are set on the persisted response log.
        assert result.response_log.error is None
        assert result.response_log.rate_limited is False
        assert result.response_log.circuit_breaker_tripped is False


class TestProxyNoRouteMatched:
    async def test_raises_404_and_never_writes_a_request_log(
        self, proxy_service, organization_id, request_logs_repo, publisher
    ) -> None:
        with pytest.raises(ProxyError) as exc_info:
            await _proxy(proxy_service, organization_id)

        assert exc_info.value.status_code == 404
        assert await request_logs_repo.list_recent(organization_id) == []
        assert publisher.events == []


class TestProxyRateLimiting:
    async def test_endpoint_rate_limit_refusal_returns_429_with_a_json_body(
        self,
        proxy_service,
        make_service,
        make_route,
        make_rate_limit_policy,
        organization_id,
        publisher,
    ) -> None:
        service = await make_service()
        route = await make_route(service.id, path_pattern="/echo", methods=["get"])
        await make_rate_limit_policy(
            scope=RateLimitScope.ENDPOINT,
            scope_reference=route.path_pattern,
            max_requests=1,
            window_seconds=60,
        )

        first = await _proxy(proxy_service, organization_id)
        assert first.status_code == HTTP_OK

        second = await _proxy(proxy_service, organization_id)
        assert second.status_code == 429
        body = json.loads(second.body)
        assert body["success"] is False
        assert body["error"]["status_code"] == 429
        assert body["request_id"] == str(second.request_log.id)
        assert "RateLimitExceeded" in publisher.names

    async def test_rate_limit_refusal_still_publishes_received_and_completed(
        self,
        proxy_service,
        make_service,
        make_route,
        make_rate_limit_policy,
        organization_id,
        publisher,
    ) -> None:
        service = await make_service()
        route = await make_route(service.id, path_pattern="/echo", methods=["get"])
        await make_rate_limit_policy(
            scope=RateLimitScope.ENDPOINT,
            scope_reference=route.path_pattern,
            max_requests=0,
            window_seconds=60,
        )

        await _proxy(proxy_service, organization_id)

        assert publisher.names == ["ApiRequestReceived", "RateLimitExceeded", "ApiRequestCompleted"]

    async def test_response_log_flags_the_rate_limit_refusal(
        self,
        proxy_service,
        make_service,
        make_route,
        make_rate_limit_policy,
        organization_id,
        response_logs_repo,
    ) -> None:
        service = await make_service()
        route = await make_route(service.id, path_pattern="/echo", methods=["get"])
        await make_rate_limit_policy(
            scope=RateLimitScope.ENDPOINT,
            scope_reference=route.path_pattern,
            max_requests=0,
            window_seconds=60,
        )

        result = await _proxy(proxy_service, organization_id)

        stored = await response_logs_repo.require_by_id(result.response_log.id)
        assert stored.rate_limited is True
        assert stored.status_code == 429

    async def test_requests_within_the_configured_limit_are_not_refused(
        self, proxy_service, make_service, make_route, make_rate_limit_policy, organization_id
    ) -> None:
        service = await make_service()
        route = await make_route(service.id, path_pattern="/echo", methods=["get"])
        await make_rate_limit_policy(
            scope=RateLimitScope.ENDPOINT,
            scope_reference=route.path_pattern,
            max_requests=5,
            window_seconds=60,
        )

        result = await _proxy(proxy_service, organization_id)

        assert result.status_code == HTTP_OK


class TestProxyQuota:
    async def test_client_quota_exceeded_returns_429_and_publishes_an_event(
        self,
        proxy_service,
        make_service,
        make_route,
        make_client,
        make_quota_policy,
        organization_id,
        publisher,
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])
        client = await make_client()
        await make_quota_policy(
            scope=QuotaScope.CLIENT,
            scope_reference=str(client.id),
            kind=QuotaKind.REQUEST,
            limit_value=1,
        )

        first = await _proxy(proxy_service, organization_id, client_id=client.id)
        assert first.status_code == HTTP_OK

        second = await _proxy(proxy_service, organization_id, client_id=client.id)
        assert second.status_code == 429
        body = json.loads(second.body)
        assert body["error"]["message"] == "Quota exceeded."
        assert "QuotaExceeded" in publisher.names

    async def test_quota_is_never_checked_when_client_id_is_none(
        self, proxy_service, make_service, make_route, make_quota_policy, organization_id
    ) -> None:
        # A CLIENT-scoped quota is looked up by a specific client_id -- the
        # `if client_id is not None:` guard in `_forward` skips the whole
        # quota branch for an anonymous call, regardless of what quota
        # policy exists for any client.
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])
        await make_quota_policy(
            scope=QuotaScope.CLIENT,
            scope_reference="some-other-client",
            kind=QuotaKind.REQUEST,
            limit_value=0,
        )

        result = await _proxy(proxy_service, organization_id, client_id=None)

        assert result.status_code == HTTP_OK

    async def test_response_log_flags_the_quota_refusal(
        self,
        proxy_service,
        make_service,
        make_route,
        make_client,
        make_quota_policy,
        organization_id,
        response_logs_repo,
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])
        client = await make_client()
        await make_quota_policy(
            scope=QuotaScope.CLIENT,
            scope_reference=str(client.id),
            kind=QuotaKind.REQUEST,
            limit_value=0,
        )

        result = await _proxy(proxy_service, organization_id, client_id=client.id)

        stored = await response_logs_repo.require_by_id(result.response_log.id)
        assert stored.quota_exceeded is True
        assert stored.status_code == 429


class TestProxyNoInstances:
    async def test_returns_503_without_publishing_a_circuit_breaker_event(
        self, proxy_service, service_registry_service, make_route, organization_id, publisher
    ) -> None:
        service = await service_registry_service.register(
            organization_id, name="empty-service", instances=[]
        )
        await make_route(service.id, path_pattern="/echo", methods=["get"])

        result = await _proxy(proxy_service, organization_id)

        assert result.status_code == 503
        body = json.loads(result.body)
        assert body["error"]["message"] == "No backend instances configured."
        assert "CircuitBreakerOpened" not in publisher.names
        assert publisher.names == ["ApiRequestReceived", "ApiRequestCompleted"]


class TestProxyUnhealthyOrCircuitOpenInstances:
    async def test_an_unhealthy_instance_returns_503_and_publishes_circuit_breaker_opened(
        self, proxy_service, make_service, make_route, health_repo, organization_id, publisher
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])
        await health_repo.create(
            ApiServiceHealth(
                organization_id=organization_id,
                service_id=service.id,
                instance_url=FAKE_BACKEND_URL,
                status=HealthState.UNHEALTHY,
                circuit_state=CircuitBreakerState.CLOSED,
                consecutive_failures=3,
                checked_at=datetime.now(UTC),
            )
        )

        result = await _proxy(proxy_service, organization_id)

        assert result.status_code == 503
        assert result.response_log.circuit_breaker_tripped is True
        assert "CircuitBreakerOpened" in publisher.names

    async def test_a_circuit_open_instance_returns_503_and_publishes_circuit_breaker_opened(
        self, proxy_service, make_service, make_route, health_repo, organization_id, publisher
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])
        await health_repo.create(
            ApiServiceHealth(
                organization_id=organization_id,
                service_id=service.id,
                instance_url=FAKE_BACKEND_URL,
                status=HealthState.HEALTHY,
                circuit_state=CircuitBreakerState.OPEN,
                consecutive_failures=2,
                checked_at=datetime.now(UTC),
            )
        )

        result = await _proxy(proxy_service, organization_id)

        assert result.status_code == 503
        assert result.response_log.circuit_breaker_tripped is True
        assert "CircuitBreakerOpened" in publisher.names


class TestProxyUpstreamFailure:
    async def test_a_connection_failure_returns_502_and_trips_the_breaker(
        self,
        route_service,
        service_registry_service,
        rate_limit_service,
        quota_service,
        health_monitor_service,
        transformation_service,
        request_logs_repo,
        response_logs_repo,
        publisher,
        make_route,
        organization_id,
    ) -> None:
        # A real (unmocked) `httpx.AsyncClient` using its default
        # transport, pointed at a loopback port nothing listens on --
        # a genuine TCP connection attempt that genuinely fails, exactly
        # the `httpx.HTTPError` `_forward`'s own `except` clause exists
        # to handle. IPv4 loopback, never "localhost" (this environment's
        # own established gotcha: Docker's broken IPv6 loopback makes
        # "localhost" hang instead of failing fast).
        unreachable_url = "http://127.0.0.1:1"
        service = await service_registry_service.register(
            organization_id,
            name="unreachable-service",
            instances=[{"url": unreachable_url, "weight": 100}],
        )
        await make_route(service.id, path_pattern="/echo", methods=["get"])

        broken_client = httpx.AsyncClient(timeout=2.0)
        try:
            proxy = ProxyService(
                http_client=broken_client,
                routes=route_service,
                services=service_registry_service,
                rate_limits=rate_limit_service,
                quotas=quota_service,
                health=health_monitor_service,
                transformations=transformation_service,
                request_logs=request_logs_repo,
                response_logs=response_logs_repo,
                round_robin_counters={},
                sticky_maps={},
                publish_event=publisher,
            )
            first = await _proxy(proxy, organization_id)
            second = await _proxy(proxy, organization_id)
        finally:
            await broken_client.aclose()

        assert first.status_code == 502
        assert first.response_log.upstream_instance == unreachable_url
        assert first.response_log.error is not None
        assert second.status_code == 502
        # `service_settings` configures `circuit_breaker_failure_threshold=2`
        # -- two consecutive upstream failures against the same instance
        # must trip its breaker open.
        assert health_monitor_service.circuit_state(unreachable_url) == CircuitBreakerState.OPEN
        assert publisher.names == [
            "ApiRequestReceived",
            "ApiRequestCompleted",
            "ApiRequestReceived",
            "ApiRequestCompleted",
        ]


class TestProxyWithoutAPublisher:
    async def test_a_successful_call_does_not_raise_when_no_publisher_is_configured(
        self,
        route_service,
        service_registry_service,
        rate_limit_service,
        quota_service,
        health_monitor_service,
        transformation_service,
        request_logs_repo,
        response_logs_repo,
        http_client,
        make_service,
        make_route,
        organization_id,
    ) -> None:
        service = await make_service()
        await make_route(service.id, path_pattern="/echo", methods=["get"])
        proxy = ProxyService(
            http_client=http_client,
            routes=route_service,
            services=service_registry_service,
            rate_limits=rate_limit_service,
            quotas=quota_service,
            health=health_monitor_service,
            transformations=transformation_service,
            request_logs=request_logs_repo,
            response_logs=response_logs_repo,
            round_robin_counters={},
            sticky_maps={},
            publish_event=None,
        )

        result = await _proxy(proxy, organization_id)

        assert result.status_code == HTTP_OK
