"""The platform's fixed API gateway vocabulary (docs/056).

Every ``Mapped[SomeEnum]`` column below is backed by ``String`` at the
database layer, per this repository's established SQLAlchemy 2.0
pattern: a raw string round-trips through Postgres exactly, unlike a
native ``ENUM`` type, which turns every new member into a migration
against a type the whole cluster shares. The cost is that a value freshly
loaded from the database is a plain ``str``, not the enum member -- so
every column that is ever compared, branched on, or handed to another
enum-typed field carries an ``X_of()`` normaliser here, and application
code calls it on the *column*, never on the record that owns it.

**These enums are independent of `shared_core`'s own enums**, even where
the vocabulary overlaps (e.g. :class:`HealthState` duplicates
:class:`shared_core.enums.health_status.HealthStatus`'s members
verbatim, and :class:`CircuitBreakerState` duplicates
:class:`shared_core.connectors.retry.CircuitState`'s). This service's
own database schema must stay stable across a `shared_core` version
bump -- the ``X_of()``-plus-translator pattern is the same one every
prior service (054's ``calendar_rule_to_cron``, 055's
``to_shared_channel``) already established.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from shared_core.connectors.retry import CircuitState as SharedCircuitState
from shared_core.enums.health_status import HealthStatus as SharedHealthStatus


class HttpMethod(StrEnum):
    """Every HTTP method a route may match on."""

    GET = "get"
    POST = "post"
    PUT = "put"
    PATCH = "patch"
    DELETE = "delete"
    HEAD = "head"
    OPTIONS = "options"


class RouteMatchKind(StrEnum):
    """How a route decides whether it applies to a request (docs/056 "API ROUTING")."""

    STATIC = "static"
    DYNAMIC = "dynamic"
    PATH = "path"
    HOST = "host"
    HEADER = "header"
    METHOD = "method"
    VERSION = "version"
    WEIGHTED = "weighted"
    CONDITIONAL = "conditional"
    FALLBACK = "fallback"


class AuthenticationMethod(StrEnum):
    """How a caller proved their identity (docs/056 "AUTHENTICATION")."""

    JWT = "jwt"
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    API_KEY = "api_key"
    SERVICE_ACCOUNT = "service_account"
    MTLS = "mtls"
    ANONYMOUS = "anonymous"


class ClientKind(StrEnum):
    """The kind of caller a registered :class:`~app.models.client.ApiClient` represents.

    Per this prompt's own OBJECTIVE: "the single external entry point
    for web applications, mobile applications, SDKs, CLI tools, AI
    agents, automation systems, partner integrations, and third-party
    APIs."
    """

    WEB_APP = "web_app"
    MOBILE_APP = "mobile_app"
    SDK = "sdk"
    CLI = "cli"
    AI_AGENT = "ai_agent"
    AUTOMATION = "automation"
    PARTNER = "partner"
    THIRD_PARTY = "third_party"


class ApiKeyStatus(StrEnum):
    """An API key's own lifecycle."""

    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"
    EXPIRED = "expired"


class RateLimitScope(StrEnum):
    """What a rate limit policy applies to (docs/056 "RATE LIMITING")."""

    GLOBAL = "global"
    ORGANIZATION = "organization"
    PROJECT = "project"
    USER = "user"
    API_KEY = "api_key"
    ENDPOINT = "endpoint"


class RateLimitAlgorithm(StrEnum):
    """Which counting strategy a rate limit policy uses."""

    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    FIXED_WINDOW = "fixed_window"


class QuotaScope(StrEnum):
    """What a quota applies to (docs/056 "QUOTA MANAGEMENT")."""

    GLOBAL = "global"
    ORGANIZATION = "organization"
    PROJECT = "project"
    CLIENT = "client"


class QuotaKind(StrEnum):
    """What a quota counts."""

    REQUEST = "request"
    BANDWIDTH = "bandwidth"
    STORAGE = "storage"


class QuotaPeriod(StrEnum):
    """How often a quota resets."""

    DAILY = "daily"
    MONTHLY = "monthly"


class LoadBalancingStrategy(StrEnum):
    """How a service's own registered instances are chosen between (docs/056 "LOAD BALANCING")."""

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED = "weighted"
    HEALTH_AWARE = "health_aware"
    STICKY_SESSION = "sticky_session"


class TransformationKind(StrEnum):
    """What a transformation rule does (docs/056 "REQUEST/RESPONSE TRANSFORMATION")."""

    HEADER = "header"
    URL_REWRITE = "url_rewrite"
    BODY = "body"
    SCHEMA_VALIDATION = "schema_validation"
    RESPONSE_MAPPING = "response_mapping"
    COMPRESSION = "compression"
    ERROR_NORMALIZATION = "error_normalization"
    METADATA_INJECTION = "metadata_injection"


class TransformationDirection(StrEnum):
    """Whether a transformation applies to the inbound request or the outbound response."""

    REQUEST = "request"
    RESPONSE = "response"


class HealthState(StrEnum):
    """One backend instance's own last-probed health.

    Mirrors :class:`shared_core.enums.health_status.HealthStatus`
    verbatim -- see :func:`to_shared_health_status`.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    WARNING = "warning"
    UNHEALTHY = "unhealthy"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


class CircuitBreakerState(StrEnum):
    """One backend instance's own circuit-breaker state.

    Mirrors :class:`shared_core.connectors.retry.CircuitState` verbatim
    -- see :func:`to_shared_circuit_state`.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ReportKind(StrEnum):
    """Which report a request wants (docs/056 "REPORTING")."""

    API_USAGE = "api_usage"
    LATENCY = "latency"
    TRAFFIC = "traffic"
    QUOTA = "quota"
    SECURITY = "security"
    GATEWAY_HEALTH = "gateway_health"
    AUDIT = "audit"


class ReportFormat(StrEnum):
    """How a report is rendered."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ReportStatus(StrEnum):
    """A generated report's own build lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditAction(StrEnum):
    """What an audit row records (docs/056 "AUDIT")."""

    ROUTE_CREATED = "route_created"
    ROUTE_UPDATED = "route_updated"
    ROUTE_DELETED = "route_deleted"
    SERVICE_REGISTERED = "service_registered"
    SERVICE_UPDATED = "service_updated"
    API_KEY_CREATED = "api_key_created"
    API_KEY_ROTATED = "api_key_rotated"
    API_KEY_REVOKED = "api_key_revoked"
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTHORIZATION_DENIED = "authorization_denied"
    GATEWAY_CONFIG_CHANGED = "gateway_config_changed"
    ADMINISTRATIVE = "administrative"


# ---- translators to shared_core's own vocabulary --------------------------

_HEALTH_STATE_TO_SHARED: Final[dict[HealthState, SharedHealthStatus]] = {
    HealthState.HEALTHY: SharedHealthStatus.HEALTHY,
    HealthState.DEGRADED: SharedHealthStatus.DEGRADED,
    HealthState.WARNING: SharedHealthStatus.WARNING,
    HealthState.UNHEALTHY: SharedHealthStatus.UNHEALTHY,
    HealthState.MAINTENANCE: SharedHealthStatus.MAINTENANCE,
    HealthState.UNKNOWN: SharedHealthStatus.UNKNOWN,
}

_HEALTH_STATE_FROM_SHARED: Final[dict[SharedHealthStatus, HealthState]] = {
    shared: local for local, shared in _HEALTH_STATE_TO_SHARED.items()
}

_CIRCUIT_STATE_TO_SHARED: Final[dict[CircuitBreakerState, SharedCircuitState]] = {
    CircuitBreakerState.CLOSED: SharedCircuitState.CLOSED,
    CircuitBreakerState.OPEN: SharedCircuitState.OPEN,
    CircuitBreakerState.HALF_OPEN: SharedCircuitState.HALF_OPEN,
}

_CIRCUIT_STATE_FROM_SHARED: Final[dict[SharedCircuitState, CircuitBreakerState]] = {
    shared: local for local, shared in _CIRCUIT_STATE_TO_SHARED.items()
}


def to_shared_health_status(state: HealthState) -> SharedHealthStatus:
    """Translate this service's own health state to `shared_core`'s (direct, one-to-one)."""
    return _HEALTH_STATE_TO_SHARED[state]


def from_shared_health_status(status: SharedHealthStatus) -> HealthState:
    """Translate a `shared_core` health status back into this service's own vocabulary."""
    return _HEALTH_STATE_FROM_SHARED[status]


def to_shared_circuit_state(state: CircuitBreakerState) -> SharedCircuitState:
    """Translate this service's own circuit state to `shared_core`'s (direct, one-to-one)."""
    return _CIRCUIT_STATE_TO_SHARED[state]


def from_shared_circuit_state(state: SharedCircuitState) -> CircuitBreakerState:
    """Translate a `shared_core` circuit state back into this service's own vocabulary."""
    return _CIRCUIT_STATE_FROM_SHARED[state]


# ---- weightings and derivations ----------------------------------------

TERMINAL_HEALTH_STATES: Final[frozenset[HealthState]] = frozenset(
    {HealthState.UNHEALTHY, HealthState.MAINTENANCE}
)
"""States a load balancer must never route new traffic to."""

# ---- normalisers ---------------------------------------------------------


def http_method_of(value: str | HttpMethod) -> HttpMethod:
    """Coerce a stored value to :class:`HttpMethod`."""
    return value if isinstance(value, HttpMethod) else HttpMethod(value)


def route_match_kind_of(value: str | RouteMatchKind) -> RouteMatchKind:
    """Coerce a stored value to :class:`RouteMatchKind`."""
    return value if isinstance(value, RouteMatchKind) else RouteMatchKind(value)


def authentication_method_of(value: str | AuthenticationMethod) -> AuthenticationMethod:
    """Coerce a stored value to :class:`AuthenticationMethod`."""
    return value if isinstance(value, AuthenticationMethod) else AuthenticationMethod(value)


def client_kind_of(value: str | ClientKind) -> ClientKind:
    """Coerce a stored value to :class:`ClientKind`."""
    return value if isinstance(value, ClientKind) else ClientKind(value)


def api_key_status_of(value: str | ApiKeyStatus) -> ApiKeyStatus:
    """Coerce a stored value to :class:`ApiKeyStatus`."""
    return value if isinstance(value, ApiKeyStatus) else ApiKeyStatus(value)


def rate_limit_scope_of(value: str | RateLimitScope) -> RateLimitScope:
    """Coerce a stored value to :class:`RateLimitScope`."""
    return value if isinstance(value, RateLimitScope) else RateLimitScope(value)


def rate_limit_algorithm_of(value: str | RateLimitAlgorithm) -> RateLimitAlgorithm:
    """Coerce a stored value to :class:`RateLimitAlgorithm`."""
    return value if isinstance(value, RateLimitAlgorithm) else RateLimitAlgorithm(value)


def quota_scope_of(value: str | QuotaScope) -> QuotaScope:
    """Coerce a stored value to :class:`QuotaScope`."""
    return value if isinstance(value, QuotaScope) else QuotaScope(value)


def quota_kind_of(value: str | QuotaKind) -> QuotaKind:
    """Coerce a stored value to :class:`QuotaKind`."""
    return value if isinstance(value, QuotaKind) else QuotaKind(value)


def quota_period_of(value: str | QuotaPeriod) -> QuotaPeriod:
    """Coerce a stored value to :class:`QuotaPeriod`."""
    return value if isinstance(value, QuotaPeriod) else QuotaPeriod(value)


def load_balancing_strategy_of(value: str | LoadBalancingStrategy) -> LoadBalancingStrategy:
    """Coerce a stored value to :class:`LoadBalancingStrategy`."""
    return value if isinstance(value, LoadBalancingStrategy) else LoadBalancingStrategy(value)


def transformation_kind_of(value: str | TransformationKind) -> TransformationKind:
    """Coerce a stored value to :class:`TransformationKind`."""
    return value if isinstance(value, TransformationKind) else TransformationKind(value)


def transformation_direction_of(value: str | TransformationDirection) -> TransformationDirection:
    """Coerce a stored value to :class:`TransformationDirection`."""
    return value if isinstance(value, TransformationDirection) else TransformationDirection(value)


def health_state_of(value: str | HealthState) -> HealthState:
    """Coerce a stored value to :class:`HealthState`."""
    return value if isinstance(value, HealthState) else HealthState(value)


def circuit_breaker_state_of(value: str | CircuitBreakerState) -> CircuitBreakerState:
    """Coerce a stored value to :class:`CircuitBreakerState`."""
    return value if isinstance(value, CircuitBreakerState) else CircuitBreakerState(value)


def report_kind_of(value: str | ReportKind) -> ReportKind:
    """Coerce a stored value to :class:`ReportKind`."""
    return value if isinstance(value, ReportKind) else ReportKind(value)


def report_format_of(value: str | ReportFormat) -> ReportFormat:
    """Coerce a stored value to :class:`ReportFormat`."""
    return value if isinstance(value, ReportFormat) else ReportFormat(value)


def report_status_of(value: str | ReportStatus) -> ReportStatus:
    """Coerce a stored value to :class:`ReportStatus`."""
    return value if isinstance(value, ReportStatus) else ReportStatus(value)


__all__ = [
    "TERMINAL_HEALTH_STATES",
    "ApiKeyStatus",
    "AuditAction",
    "AuthenticationMethod",
    "CircuitBreakerState",
    "ClientKind",
    "HealthState",
    "HttpMethod",
    "LoadBalancingStrategy",
    "QuotaKind",
    "QuotaPeriod",
    "QuotaScope",
    "RateLimitAlgorithm",
    "RateLimitScope",
    "ReportFormat",
    "ReportKind",
    "ReportStatus",
    "RouteMatchKind",
    "TransformationDirection",
    "TransformationKind",
    "api_key_status_of",
    "authentication_method_of",
    "circuit_breaker_state_of",
    "client_kind_of",
    "from_shared_circuit_state",
    "from_shared_health_status",
    "health_state_of",
    "http_method_of",
    "load_balancing_strategy_of",
    "quota_kind_of",
    "quota_period_of",
    "quota_scope_of",
    "rate_limit_algorithm_of",
    "rate_limit_scope_of",
    "report_format_of",
    "report_kind_of",
    "report_status_of",
    "route_match_kind_of",
    "transformation_direction_of",
    "transformation_kind_of",
]
