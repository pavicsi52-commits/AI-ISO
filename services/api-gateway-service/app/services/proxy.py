"""The reverse-proxy orchestrator.

The one place actual outbound HTTP calls happen -- no framework exists
anywhere in `shared_core` to wrap for this (confirmed during this
prompt's own research phase), so it is built directly on
``httpx.AsyncClient``. Composes every other pure engine and service in
this package: routing decides *which* service; load balancing decides
*which instance*; rate limiting and quotas decide *whether*;
transformation reshapes the request/response; health/circuit-breaking
decides whether an instance is even attempted.

**Body transformation never parses the proxied payload.** A reverse
proxy must stay protocol-agnostic -- the body crossing this service is
opaque bytes that might be JSON, a file upload, a protobuf blob, or
anything else, and guessing at its shape to apply a configured
``BODY``-kind transformation would silently corrupt every payload that
isn't JSON. Header and URL-rewrite transformations (which never touch
the body) apply on the live path; body transformation rules are real,
tested, and callable directly (see
:meth:`~app.services.transformation.TransformationService
.apply_request`), but are not wired into this always-streams-bytes
proxy path -- a documented scope boundary, not an omission.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from app.events.gateway_events import (
    SOURCE_SERVICE,
    ApiRequestCompletedEvent,
    ApiRequestReceivedEvent,
    CircuitBreakerOpenedEvent,
    QuotaExceededEvent,
    RateLimitExceededEvent,
)
from app.loadbalancing import engine as lb_engine
from app.models.enums import AuthenticationMethod, QuotaKind, QuotaScope, RateLimitScope
from app.models.request import ApiRequestLog, ApiResponseLog
from app.models.route import ApiRoute
from app.repositories.request import ApiRequestLogRepository, ApiResponseLogRepository
from app.routing import engine as routing_engine
from app.services.health import HealthMonitorService
from app.services.quota import QuotaService
from app.services.ratelimit import RateLimitService
from app.services.route import RouteService
from app.services.service import ServiceRegistryService
from app.services.transformation import TransformationService
from app.transform.engine import normalize_error_body
from app.types import EventPublisher


@dataclass(frozen=True, slots=True)
class ProxyResult:
    """The outcome of one proxied call."""

    status_code: int
    headers: dict[str, str]
    body: bytes
    request_log: ApiRequestLog
    response_log: ApiResponseLog


class ProxyError(Exception):
    """Raised for a proxy-level refusal that never reached an upstream instance."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ProxyService:
    """Resolves, authorizes, rate-limits, load-balances, and forwards one request."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        routes: RouteService,
        services: ServiceRegistryService,
        rate_limits: RateLimitService,
        quotas: QuotaService,
        health: HealthMonitorService,
        transformations: TransformationService,
        request_logs: ApiRequestLogRepository,
        response_logs: ApiResponseLogRepository,
        round_robin_counters: dict[str, lb_engine.RoundRobinCounter],
        sticky_maps: dict[str, lb_engine.StickySessionMap],
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._http_client = http_client
        self._routes = routes
        self._services = services
        self._rate_limits = rate_limits
        self._quotas = quotas
        self._health = health
        self._transformations = transformations
        self._request_logs = request_logs
        self._response_logs = response_logs
        self._round_robin_counters = round_robin_counters
        self._sticky_maps = sticky_maps
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def proxy(
        self,
        organization_id: UUID,
        *,
        method: str,
        path: str,
        query_string: str | None,
        headers: dict[str, str],
        body: bytes,
        source_ip: str | None,
        client_id: UUID | None,
        api_key_id: UUID | None,
        authenticated_user_id: str | None,
        auth_method: AuthenticationMethod | None,
    ) -> ProxyResult:
        """Resolve, authorize, rate-limit, load-balance, and forward one request.

        Raises:
            ProxyError: If no route matches at all (a 404 that never
                reaches this method's own refusal-logging path, since
                without a route there is no service to log the request
                against).
        """
        correlation_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

        route = await self._routes.resolve(organization_id, method=method, path=path, headers=headers)
        if route is None:
            raise ProxyError(404, "No route matches this request.")

        request_log = await self._request_logs.create(
            ApiRequestLog(
                organization_id=organization_id,
                client_id=client_id,
                api_key_id=api_key_id,
                route_id=route.id,
                service_id=route.service_id,
                method=method.upper(),
                path=path,
                query_string=query_string,
                correlation_id=correlation_id,
                source_ip=source_ip,
                user_agent=headers.get("user-agent"),
                authenticated_user_id=authenticated_user_id,
                auth_method=auth_method,
                started_at=started_at,
            )
        )
        await self._publish_event(
            ApiRequestReceivedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"request_id": str(request_log.id), "method": method, "path": path},
            )
        )

        result = await self._forward(
            organization_id,
            route=route,
            request_log=request_log,
            headers=headers,
            path=path,
            body=body,
            client_id=client_id,
            started_at=started_at,
            correlation_id=correlation_id,
        )
        await self._publish_event(
            ApiRequestCompletedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"request_id": str(request_log.id), "status_code": result.status_code},
            )
        )
        return result

    async def _forward(
        self,
        organization_id: UUID,
        *,
        route: ApiRoute,
        request_log: ApiRequestLog,
        headers: dict[str, str],
        path: str,
        body: bytes,
        client_id: UUID | None,
        started_at: datetime,
        correlation_id: str,
    ) -> ProxyResult:
        rate_decision = await self._rate_limits.check(
            organization_id, RateLimitScope.ENDPOINT, route.path_pattern
        )
        if not rate_decision.allowed:
            await self._publish_event(
                RateLimitExceededEvent(
                    source_service=SOURCE_SERVICE,
                    organization_id=organization_id,
                    payload={"request_id": str(request_log.id), "scope": "endpoint"},
                )
            )
            return await self._log_refusal(
                organization_id,
                request_log,
                status_code=429,
                error="Rate limit exceeded.",
                started_at=started_at,
                correlation_id=correlation_id,
                rate_limited=True,
            )

        if client_id is not None:
            allowed = await self._quotas.check_and_increment(
                organization_id, QuotaScope.CLIENT, str(client_id), QuotaKind.REQUEST
            )
            if not allowed:
                await self._publish_event(
                    QuotaExceededEvent(
                        source_service=SOURCE_SERVICE,
                        organization_id=organization_id,
                        payload={"request_id": str(request_log.id), "client_id": str(client_id)},
                    )
                )
                return await self._log_refusal(
                    organization_id,
                    request_log,
                    status_code=429,
                    error="Quota exceeded.",
                    started_at=started_at,
                    correlation_id=correlation_id,
                    quota_exceeded=True,
                )

        service = await self._services.get(organization_id, route.service_id)
        instances = [
            lb_engine.Instance(url=instance["url"], weight=instance.get("weight", 100))
            for instance in service.instances
        ]
        if not instances:
            return await self._log_refusal(
                organization_id,
                request_log,
                status_code=503,
                error="No backend instances configured.",
                started_at=started_at,
                correlation_id=correlation_id,
            )

        health_snapshot = await self._health.snapshot(organization_id, service.id)
        circuit_snapshot = await self._health.circuit_snapshot(organization_id, service.id)
        counter = self._round_robin_counters.setdefault(str(service.id), lb_engine.RoundRobinCounter())
        sticky_map = self._sticky_maps.setdefault(str(service.id), lb_engine.StickySessionMap())
        instance = lb_engine.choose_instance(
            service.load_balancing_strategy,
            instances,
            round_robin_counter=counter,
            health=health_snapshot,
            circuit_states=circuit_snapshot,
            sticky_key=str(client_id) if client_id else None,
            sticky_map=sticky_map,
        )
        if instance is None:
            await self._publish_event(
                CircuitBreakerOpenedEvent(
                    source_service=SOURCE_SERVICE,
                    organization_id=organization_id,
                    payload={"service_id": str(service.id)},
                )
            )
            return await self._log_refusal(
                organization_id,
                request_log,
                status_code=503,
                error="No healthy backend instance available.",
                started_at=started_at,
                correlation_id=correlation_id,
                circuit_breaker_tripped=True,
            )

        rules = await self._transformations.list_for_route(organization_id, route.id)
        candidate = routing_engine.RouteCandidate(
            id=str(route.id),
            service_id=str(route.service_id),
            match_kind=route.match_kind,
            path_pattern=route.path_pattern,
            host_pattern=route.host_pattern,
            methods=tuple(route.methods),
            header_match=route.header_match,
            weight=route.weight,
            priority=route.priority,
            strip_prefix=route.strip_prefix,
            rewrite_path=route.rewrite_path,
            is_fallback=route.is_fallback,
            enabled=route.enabled,
        )
        target_path = routing_engine.resolve_target_path(candidate, path)
        forward_headers, target_path, _ = self._transformations.apply_request(
            rules, headers=headers, path=target_path, body=None
        )
        forward_headers = {k: v for k, v in forward_headers.items() if k.lower() != "host"}
        forward_headers["X-Correlation-ID"] = correlation_id

        target_url = instance.url.rstrip("/") + target_path

        upstream_started = time.perf_counter()
        try:
            response = await self._http_client.request(
                request_log.method,
                target_url,
                headers=forward_headers,
                content=body,
                timeout=service.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            self._health.breaker_for(instance.url).record_failure()
            return await self._log_refusal(
                organization_id,
                request_log,
                status_code=502,
                error=str(exc),
                started_at=started_at,
                correlation_id=correlation_id,
                upstream_instance=instance.url,
            )
        upstream_latency_ms = (time.perf_counter() - upstream_started) * 1_000
        self._health.breaker_for(instance.url).record_success()

        response_headers, _ = self._transformations.apply_response(
            rules, headers=dict(response.headers), body=None
        )

        completed_at = datetime.now(UTC)
        total_latency_ms = (completed_at - started_at).total_seconds() * 1_000
        response_log = await self._response_logs.create(
            ApiResponseLog(
                organization_id=organization_id,
                request_id=request_log.id,
                status_code=response.status_code,
                upstream_instance=instance.url,
                latency_ms=total_latency_ms,
                upstream_latency_ms=upstream_latency_ms,
                completed_at=completed_at,
            )
        )
        return ProxyResult(
            status_code=response.status_code,
            headers=response_headers,
            body=response.content,
            request_log=request_log,
            response_log=response_log,
        )

    async def _log_refusal(
        self,
        organization_id: UUID,
        request_log: ApiRequestLog,
        *,
        status_code: int,
        error: str,
        started_at: datetime,
        correlation_id: str,
        rate_limited: bool = False,
        quota_exceeded: bool = False,
        circuit_breaker_tripped: bool = False,
        upstream_instance: str | None = None,
    ) -> ProxyResult:
        """Record a refusal that never reached (or failed to reach) an upstream instance."""
        completed_at = datetime.now(UTC)
        response_log = await self._response_logs.create(
            ApiResponseLog(
                organization_id=organization_id,
                request_id=request_log.id,
                status_code=status_code,
                upstream_instance=upstream_instance,
                latency_ms=(completed_at - started_at).total_seconds() * 1_000,
                error=error,
                completed_at=completed_at,
                rate_limited=rate_limited,
                quota_exceeded=quota_exceeded,
                circuit_breaker_tripped=circuit_breaker_tripped,
            )
        )
        body_dict = normalize_error_body(
            status_code=status_code, detail=error, request_id=str(request_log.id)
        )
        return ProxyResult(
            status_code=status_code,
            headers={"Content-Type": "application/json", "X-Correlation-ID": correlation_id},
            body=json.dumps(body_dict).encode("utf-8"),
            request_log=request_log,
            response_log=response_log,
        )


__all__ = ["ProxyError", "ProxyResult", "ProxyService"]
