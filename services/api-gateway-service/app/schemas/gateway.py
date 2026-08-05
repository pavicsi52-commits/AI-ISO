"""Request and response schemas for the API gateway's own management surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    AuditAction,
    ClientKind,
    HealthState,
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
)

# ---- services ------------------------------------------------------------------


class ServiceInstanceIn(BaseModel):
    url: str = Field(min_length=1, max_length=512)
    weight: int = Field(default=100, ge=1, le=10_000)


class ServiceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    instances: list[ServiceInstanceIn] = Field(default_factory=list)
    description: str | None = None
    load_balancing_strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN
    health_check_path: str = "/health"
    timeout_seconds: float | None = Field(default=None, gt=0)
    circuit_breaker_enabled: bool = True


class ServiceUpdateRequest(BaseModel):
    description: str | None = None
    instances: list[ServiceInstanceIn] | None = None
    load_balancing_strategy: LoadBalancingStrategy | None = None
    health_check_path: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
    circuit_breaker_enabled: bool | None = None
    enabled: bool | None = None


class ServiceResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    instances: list[dict[str, Any]]
    load_balancing_strategy: LoadBalancingStrategy
    health_check_path: str
    timeout_seconds: float | None
    circuit_breaker_enabled: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---- versions ------------------------------------------------------------------


class VersionCreateRequest(BaseModel):
    service_id: UUID
    version: str = Field(min_length=1, max_length=32)
    is_default: bool = False


class VersionResponse(BaseModel):
    id: UUID
    service_id: UUID
    version: str
    is_default: bool
    is_deprecated: bool
    deprecation_message: str | None
    sunset_at: datetime | None

    model_config = {"from_attributes": True}


class VersionDeprecateRequest(BaseModel):
    message: str | None = None
    sunset_at: datetime | None = None


# ---- routes --------------------------------------------------------------------


class RouteCreateRequest(BaseModel):
    service_id: UUID
    name: str = Field(min_length=1, max_length=128)
    match_kind: RouteMatchKind = RouteMatchKind.PATH
    version_id: UUID | None = None
    path_pattern: str = Field(min_length=1, max_length=512)
    host_pattern: str | None = None
    methods: list[str] = Field(default_factory=list)
    header_match: dict[str, str] = Field(default_factory=dict)
    weight: int = Field(default=100, ge=1, le=10_000)
    priority: int = Field(default=100, ge=0, le=100_000)
    strip_prefix: bool = False
    rewrite_path: str | None = None
    requires_auth: bool = True
    allowed_auth_methods: list[str] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)
    required_permission: str | None = None
    is_fallback: bool = False
    description: str | None = None


class RouteUpdateRequest(BaseModel):
    name: str | None = None
    path_pattern: str | None = None
    host_pattern: str | None = None
    methods: list[str] | None = None
    header_match: dict[str, str] | None = None
    weight: int | None = Field(default=None, ge=1, le=10_000)
    priority: int | None = Field(default=None, ge=0, le=100_000)
    strip_prefix: bool | None = None
    rewrite_path: str | None = None
    requires_auth: bool | None = None
    allowed_auth_methods: list[str] | None = None
    required_scopes: list[str] | None = None
    required_permission: str | None = None
    description: str | None = None
    enabled: bool | None = None


class RouteResponse(BaseModel):
    id: UUID
    organization_id: UUID
    service_id: UUID
    version_id: UUID | None
    name: str
    match_kind: RouteMatchKind
    path_pattern: str
    host_pattern: str | None
    methods: list[str]
    header_match: dict[str, str]
    weight: int
    priority: int
    strip_prefix: bool
    rewrite_path: str | None
    requires_auth: bool
    allowed_auth_methods: list[str]
    required_scopes: list[str]
    required_permission: str | None
    is_fallback: bool
    description: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---- clients and api keys -------------------------------------------------------


class ClientCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    client_kind: ClientKind = ClientKind.THIRD_PARTY
    description: str | None = None
    contact_email: str | None = None


class ClientResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    client_kind: ClientKind
    description: str | None
    contact_email: str | None
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreateRequest(BaseModel):
    client_id: UUID
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=list)
    ttl_days: int | None = Field(default=None, ge=1, le=3_650)
    ip_allowlist: list[str] = Field(default_factory=list)


class ApiKeyResponse(BaseModel):
    id: UUID
    organization_id: UUID
    client_id: UUID
    key_id: str
    name: str
    scopes: list[str]
    ip_allowlist: list[str]
    status: str
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(BaseModel):
    """Returned only once, at creation/rotation time -- the raw key is never stored."""

    raw_key: str
    api_key: ApiKeyResponse


# ---- rate limits and quotas ---------------------------------------------------


class RateLimitPolicyRequest(BaseModel):
    scope: RateLimitScope
    scope_reference: str | None = None
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW
    max_requests: int = Field(ge=1)
    window_seconds: int = Field(ge=1, le=86_400)
    burst_max_requests: int | None = Field(default=None, ge=1)
    burst_window_seconds: int | None = Field(default=None, ge=1)


class RateLimitPolicyResponse(BaseModel):
    id: UUID
    scope: RateLimitScope
    scope_reference: str | None
    algorithm: RateLimitAlgorithm
    max_requests: int
    window_seconds: int
    burst_max_requests: int | None
    burst_window_seconds: int | None
    enabled: bool

    model_config = {"from_attributes": True}


class QuotaPolicyRequest(BaseModel):
    scope: QuotaScope
    scope_reference: str | None = None
    kind: QuotaKind = QuotaKind.REQUEST
    period: QuotaPeriod = QuotaPeriod.DAILY
    limit_value: float = Field(gt=0)


class QuotaPolicyResponse(BaseModel):
    id: UUID
    scope: QuotaScope
    scope_reference: str | None
    kind: QuotaKind
    period: QuotaPeriod
    limit_value: float
    used_value: float
    period_started_at: datetime
    period_resets_at: datetime
    enabled: bool

    model_config = {"from_attributes": True}


# ---- transformations --------------------------------------------------------------


class TransformationRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str
    direction: str = "request"
    config: dict[str, Any] = Field(default_factory=dict)
    route_id: UUID | None = None
    priority: int = Field(default=100, ge=0, le=100_000)


class TransformationRuleResponse(BaseModel):
    id: UUID
    route_id: UUID | None
    name: str
    kind: str
    direction: str
    config: dict[str, Any]
    priority: int
    enabled: bool

    model_config = {"from_attributes": True}


# ---- health --------------------------------------------------------------------


class ServiceHealthResponse(BaseModel):
    service_id: UUID
    instance_url: str
    status: HealthState
    latency_ms: float | None
    error: str | None
    circuit_state: str
    consecutive_failures: int
    checked_at: datetime

    model_config = {"from_attributes": True}


# ---- statistics, reports, audit --------------------------------------------------


class StatisticResponse(BaseModel):
    id: UUID
    window_start: datetime
    window_end: datetime
    total_requests: int
    successful_requests: int
    failed_requests: int
    rate_limited_requests: int
    quota_exceeded_requests: int
    average_latency_ms: float | None
    p95_latency_ms: float | None
    error_rate: float
    success_rate: float
    by_service: dict[str, int]
    by_status_code: dict[str, int]
    by_client: dict[str, int]

    model_config = {"from_attributes": True}


class ReportGenerateRequest(BaseModel):
    kind: ReportKind
    report_format: ReportFormat = ReportFormat.JSON
    title: str | None = None


class ReportResponse(BaseModel):
    id: UUID
    kind: ReportKind
    report_format: ReportFormat
    title: str
    status: ReportStatus
    content: dict[str, Any]
    row_count: int | None
    generated_by: str | None
    generated_at: datetime | None
    duration_ms: float | None
    error: str | None

    model_config = {"from_attributes": True}


class AuditEntryResponse(BaseModel):
    id: UUID
    action: AuditAction
    entity_type: str
    entity_id: UUID | None
    entity_reference: str | None
    actor_id: str | None
    actor_type: str
    occurred_at: datetime
    summary: str
    succeeded: bool
    changes: dict[str, Any]
    context: dict[str, Any]

    model_config = {"from_attributes": True}


__all__ = [
    "ApiKeyCreateRequest",
    "ApiKeyCreatedResponse",
    "ApiKeyResponse",
    "AuditEntryResponse",
    "ClientCreateRequest",
    "ClientResponse",
    "QuotaPolicyRequest",
    "QuotaPolicyResponse",
    "RateLimitPolicyRequest",
    "RateLimitPolicyResponse",
    "ReportGenerateRequest",
    "ReportResponse",
    "RouteCreateRequest",
    "RouteResponse",
    "RouteUpdateRequest",
    "ServiceCreateRequest",
    "ServiceHealthResponse",
    "ServiceInstanceIn",
    "ServiceResponse",
    "ServiceUpdateRequest",
    "StatisticResponse",
    "TransformationRuleRequest",
    "TransformationRuleResponse",
    "VersionCreateRequest",
    "VersionDeprecateRequest",
    "VersionResponse",
]
