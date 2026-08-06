"""Pure tests for app/models/enums.py -- no database, no fixtures."""

from __future__ import annotations

import pytest
from shared_core.connectors.retry import CircuitState as SharedCircuitState
from shared_core.enums.health_status import HealthStatus as SharedHealthStatus

from app.models.enums import (
    TERMINAL_HEALTH_STATES,
    ApiKeyStatus,
    AuthenticationMethod,
    CircuitBreakerState,
    ClientKind,
    HealthState,
    HttpMethod,
    LoadBalancingStrategy,
    QuotaKind,
    QuotaPeriod,
    QuotaScope,
    RateLimitAlgorithm,
    RateLimitScope,
    ReportFormat,
    ReportKind,
    ReportStatus,
    RouteMatchKind,
    TransformationDirection,
    TransformationKind,
    api_key_status_of,
    authentication_method_of,
    circuit_breaker_state_of,
    client_kind_of,
    from_shared_circuit_state,
    from_shared_health_status,
    health_state_of,
    http_method_of,
    load_balancing_strategy_of,
    quota_kind_of,
    quota_period_of,
    quota_scope_of,
    rate_limit_algorithm_of,
    rate_limit_scope_of,
    report_format_of,
    report_kind_of,
    report_status_of,
    route_match_kind_of,
    to_shared_circuit_state,
    to_shared_health_status,
    transformation_direction_of,
    transformation_kind_of,
)

pytestmark = pytest.mark.asyncio


class TestHealthStatusTranslationIsABijection:
    @pytest.mark.parametrize(
        ("local", "shared"),
        [
            (HealthState.HEALTHY, SharedHealthStatus.HEALTHY),
            (HealthState.DEGRADED, SharedHealthStatus.DEGRADED),
            (HealthState.WARNING, SharedHealthStatus.WARNING),
            (HealthState.UNHEALTHY, SharedHealthStatus.UNHEALTHY),
            (HealthState.MAINTENANCE, SharedHealthStatus.MAINTENANCE),
            (HealthState.UNKNOWN, SharedHealthStatus.UNKNOWN),
        ],
    )
    async def test_to_shared_maps_every_member(
        self, local: HealthState, shared: SharedHealthStatus
    ) -> None:
        assert to_shared_health_status(local) == shared

    @pytest.mark.parametrize(
        ("local", "shared"),
        [
            (HealthState.HEALTHY, SharedHealthStatus.HEALTHY),
            (HealthState.DEGRADED, SharedHealthStatus.DEGRADED),
            (HealthState.WARNING, SharedHealthStatus.WARNING),
            (HealthState.UNHEALTHY, SharedHealthStatus.UNHEALTHY),
            (HealthState.MAINTENANCE, SharedHealthStatus.MAINTENANCE),
            (HealthState.UNKNOWN, SharedHealthStatus.UNKNOWN),
        ],
    )
    async def test_from_shared_maps_every_member_back(
        self, local: HealthState, shared: SharedHealthStatus
    ) -> None:
        assert from_shared_health_status(shared) == local

    @pytest.mark.parametrize("state", list(HealthState))
    async def test_round_trips_through_shared_and_back(self, state: HealthState) -> None:
        assert from_shared_health_status(to_shared_health_status(state)) == state

    async def test_every_health_state_member_has_a_translation(self) -> None:
        for state in HealthState:
            to_shared_health_status(state)  # must not raise KeyError

    async def test_every_shared_health_status_member_has_a_translation(self) -> None:
        for status in SharedHealthStatus:
            from_shared_health_status(status)  # must not raise KeyError


class TestCircuitStateTranslationIsABijection:
    @pytest.mark.parametrize(
        ("local", "shared"),
        [
            (CircuitBreakerState.CLOSED, SharedCircuitState.CLOSED),
            (CircuitBreakerState.OPEN, SharedCircuitState.OPEN),
            (CircuitBreakerState.HALF_OPEN, SharedCircuitState.HALF_OPEN),
        ],
    )
    async def test_to_shared_maps_every_member(
        self, local: CircuitBreakerState, shared: SharedCircuitState
    ) -> None:
        assert to_shared_circuit_state(local) == shared

    @pytest.mark.parametrize(
        ("local", "shared"),
        [
            (CircuitBreakerState.CLOSED, SharedCircuitState.CLOSED),
            (CircuitBreakerState.OPEN, SharedCircuitState.OPEN),
            (CircuitBreakerState.HALF_OPEN, SharedCircuitState.HALF_OPEN),
        ],
    )
    async def test_from_shared_maps_every_member_back(
        self, local: CircuitBreakerState, shared: SharedCircuitState
    ) -> None:
        assert from_shared_circuit_state(shared) == local

    @pytest.mark.parametrize("state", list(CircuitBreakerState))
    async def test_round_trips_through_shared_and_back(self, state: CircuitBreakerState) -> None:
        assert from_shared_circuit_state(to_shared_circuit_state(state)) == state

    async def test_every_circuit_breaker_state_member_has_a_translation(self) -> None:
        for state in CircuitBreakerState:
            to_shared_circuit_state(state)  # must not raise KeyError

    async def test_every_shared_circuit_state_member_has_a_translation(self) -> None:
        for state in SharedCircuitState:
            from_shared_circuit_state(state)  # must not raise KeyError


class TestTerminalHealthStates:
    @pytest.mark.parametrize("state", [HealthState.UNHEALTHY, HealthState.MAINTENANCE])
    async def test_contains_the_states_a_load_balancer_must_never_route_to(
        self, state: HealthState
    ) -> None:
        assert state in TERMINAL_HEALTH_STATES

    @pytest.mark.parametrize(
        "state",
        [HealthState.HEALTHY, HealthState.DEGRADED, HealthState.WARNING, HealthState.UNKNOWN],
    )
    async def test_excludes_every_other_state(self, state: HealthState) -> None:
        assert state not in TERMINAL_HEALTH_STATES


class TestNormalizers:
    async def test_http_method_of_accepts_enum_member(self) -> None:
        assert http_method_of(HttpMethod.POST) == HttpMethod.POST

    async def test_http_method_of_accepts_raw_string(self) -> None:
        assert http_method_of("post") == HttpMethod.POST

    async def test_route_match_kind_of_accepts_enum_member(self) -> None:
        assert route_match_kind_of(RouteMatchKind.WEIGHTED) == RouteMatchKind.WEIGHTED

    async def test_route_match_kind_of_accepts_raw_string(self) -> None:
        assert route_match_kind_of("weighted") == RouteMatchKind.WEIGHTED

    async def test_authentication_method_of_accepts_enum_member(self) -> None:
        assert authentication_method_of(AuthenticationMethod.JWT) == AuthenticationMethod.JWT

    async def test_authentication_method_of_accepts_raw_string(self) -> None:
        assert authentication_method_of("jwt") == AuthenticationMethod.JWT

    async def test_client_kind_of_accepts_enum_member(self) -> None:
        assert client_kind_of(ClientKind.AI_AGENT) == ClientKind.AI_AGENT

    async def test_client_kind_of_accepts_raw_string(self) -> None:
        assert client_kind_of("ai_agent") == ClientKind.AI_AGENT

    async def test_api_key_status_of_accepts_enum_member(self) -> None:
        assert api_key_status_of(ApiKeyStatus.REVOKED) == ApiKeyStatus.REVOKED

    async def test_api_key_status_of_accepts_raw_string(self) -> None:
        assert api_key_status_of("revoked") == ApiKeyStatus.REVOKED

    async def test_rate_limit_scope_of_accepts_enum_member(self) -> None:
        assert rate_limit_scope_of(RateLimitScope.API_KEY) == RateLimitScope.API_KEY

    async def test_rate_limit_scope_of_accepts_raw_string(self) -> None:
        assert rate_limit_scope_of("api_key") == RateLimitScope.API_KEY

    async def test_rate_limit_algorithm_of_accepts_enum_member(self) -> None:
        assert (
            rate_limit_algorithm_of(RateLimitAlgorithm.SLIDING_WINDOW)
            == RateLimitAlgorithm.SLIDING_WINDOW
        )

    async def test_rate_limit_algorithm_of_accepts_raw_string(self) -> None:
        assert rate_limit_algorithm_of("sliding_window") == RateLimitAlgorithm.SLIDING_WINDOW

    async def test_quota_scope_of_accepts_enum_member(self) -> None:
        assert quota_scope_of(QuotaScope.PROJECT) == QuotaScope.PROJECT

    async def test_quota_scope_of_accepts_raw_string(self) -> None:
        assert quota_scope_of("project") == QuotaScope.PROJECT

    async def test_quota_kind_of_accepts_enum_member(self) -> None:
        assert quota_kind_of(QuotaKind.BANDWIDTH) == QuotaKind.BANDWIDTH

    async def test_quota_kind_of_accepts_raw_string(self) -> None:
        assert quota_kind_of("bandwidth") == QuotaKind.BANDWIDTH

    async def test_quota_period_of_accepts_enum_member(self) -> None:
        assert quota_period_of(QuotaPeriod.MONTHLY) == QuotaPeriod.MONTHLY

    async def test_quota_period_of_accepts_raw_string(self) -> None:
        assert quota_period_of("monthly") == QuotaPeriod.MONTHLY

    async def test_load_balancing_strategy_of_accepts_enum_member(self) -> None:
        assert (
            load_balancing_strategy_of(LoadBalancingStrategy.STICKY_SESSION)
            == LoadBalancingStrategy.STICKY_SESSION
        )

    async def test_load_balancing_strategy_of_accepts_raw_string(self) -> None:
        assert load_balancing_strategy_of("sticky_session") == LoadBalancingStrategy.STICKY_SESSION

    async def test_transformation_kind_of_accepts_enum_member(self) -> None:
        assert (
            transformation_kind_of(TransformationKind.ERROR_NORMALIZATION)
            == TransformationKind.ERROR_NORMALIZATION
        )

    async def test_transformation_kind_of_accepts_raw_string(self) -> None:
        assert (
            transformation_kind_of("error_normalization") == TransformationKind.ERROR_NORMALIZATION
        )

    async def test_transformation_direction_of_accepts_enum_member(self) -> None:
        assert (
            transformation_direction_of(TransformationDirection.RESPONSE)
            == TransformationDirection.RESPONSE
        )

    async def test_transformation_direction_of_accepts_raw_string(self) -> None:
        assert transformation_direction_of("response") == TransformationDirection.RESPONSE

    async def test_health_state_of_accepts_enum_member(self) -> None:
        assert health_state_of(HealthState.DEGRADED) == HealthState.DEGRADED

    async def test_health_state_of_accepts_raw_string(self) -> None:
        assert health_state_of("degraded") == HealthState.DEGRADED

    async def test_circuit_breaker_state_of_accepts_enum_member(self) -> None:
        assert (
            circuit_breaker_state_of(CircuitBreakerState.HALF_OPEN) == CircuitBreakerState.HALF_OPEN
        )

    async def test_circuit_breaker_state_of_accepts_raw_string(self) -> None:
        assert circuit_breaker_state_of("half_open") == CircuitBreakerState.HALF_OPEN

    async def test_report_kind_of_accepts_enum_member(self) -> None:
        assert report_kind_of(ReportKind.SECURITY) == ReportKind.SECURITY

    async def test_report_kind_of_accepts_raw_string(self) -> None:
        assert report_kind_of("security") == ReportKind.SECURITY

    async def test_report_format_of_accepts_enum_member(self) -> None:
        assert report_format_of(ReportFormat.MARKDOWN) == ReportFormat.MARKDOWN

    async def test_report_format_of_accepts_raw_string(self) -> None:
        assert report_format_of("markdown") == ReportFormat.MARKDOWN

    async def test_report_status_of_accepts_enum_member(self) -> None:
        assert report_status_of(ReportStatus.FAILED) == ReportStatus.FAILED

    async def test_report_status_of_accepts_raw_string(self) -> None:
        assert report_status_of("failed") == ReportStatus.FAILED
