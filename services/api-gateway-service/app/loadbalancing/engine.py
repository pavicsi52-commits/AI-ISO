"""Pure load-balancing decisions.

A genuine gap in `shared_core` (confirmed during this prompt's own
research phase: zero matches for ``load_balanc``/``round_robin``/
``weighted``/``sticky`` anywhere in the framework) -- built new here.
Health-awareness and failover still lean on existing primitives rather
than reimplementing them: an instance's own health comes from
`shared_core.monitoring.checks.check_http_reachable` (via
:class:`app.models.enums.HealthState`) and its own circuit state from
`shared_core.connectors.retry.CircuitBreaker` (via
:class:`app.models.enums.CircuitBreakerState`) -- this module only
decides *which* still-viable instance to prefer, never whether an
instance is viable in the first place.

:class:`RoundRobinCounter` and :class:`StickySessionMap` are small,
self-mutating, no-I/O state machines -- the exact same shape
`shared_core.connectors.retry.CircuitBreaker` itself already is. A pure
decision function still needs *some* place to keep "whose turn is
next"; encapsulating it in a tiny dataclass the caller owns and passes
in is the established precedent for that, not a violation of it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from app.models.enums import (
    TERMINAL_HEALTH_STATES,
    CircuitBreakerState,
    HealthState,
    LoadBalancingStrategy,
)


@dataclass(frozen=True, slots=True)
class Instance:
    """One live backend instance, as read from :attr:`~app.models.service.ApiService.instances`."""

    url: str
    weight: int = 100


@dataclass(slots=True)
class RoundRobinCounter:
    """An encapsulated round-robin cursor, one per logical service."""

    _next_index: int = 0

    def next_index(self, count: int) -> int:
        """The index to use for this call, advancing the cursor for the next one."""
        if count <= 0:
            return 0
        index = self._next_index % count
        self._next_index += 1
        return index


@dataclass(slots=True)
class StickySessionMap:
    """An encapsulated sticky-session binding, one per logical service."""

    _bindings: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str | None:
        """The instance URL previously bound to *key*, if any."""
        return self._bindings.get(key)

    def bind(self, key: str, url: str) -> None:
        """Bind *key* to *url* for future sticky lookups."""
        self._bindings[key] = url


def choose_round_robin(instances: list[Instance], counter: RoundRobinCounter) -> Instance:
    """The next instance in round-robin order."""
    return instances[counter.next_index(len(instances))]


def choose_least_connections(
    instances: list[Instance], active_connections: dict[str, int]
) -> Instance:
    """The instance with the fewest currently in-flight requests."""
    return min(instances, key=lambda instance: active_connections.get(instance.url, 0))


def choose_weighted(instances: list[Instance]) -> Instance:
    """One instance, chosen by weighted-random selection."""
    total_weight = sum(instance.weight for instance in instances) or 1
    pick = random.uniform(0, total_weight)
    running_total = 0.0
    for instance in instances:
        running_total += instance.weight
        if pick <= running_total:
            return instance
    return instances[-1]


def filter_healthy(instances: list[Instance], health: dict[str, HealthState]) -> list[Instance]:
    """Every instance whose last-probed health is not terminal.

    An instance never probed yet (absent from *health*) is treated as
    available -- "unknown" must not silently remove a freshly-registered
    instance from rotation before its first health check has even run.
    """
    return [
        instance
        for instance in instances
        if health.get(instance.url, HealthState.HEALTHY) not in TERMINAL_HEALTH_STATES
    ]


def filter_circuit_closed(
    instances: list[Instance], circuit_states: dict[str, CircuitBreakerState]
) -> list[Instance]:
    """Every instance whose circuit breaker is not currently ``OPEN``."""
    return [
        instance
        for instance in instances
        if circuit_states.get(instance.url, CircuitBreakerState.CLOSED) != CircuitBreakerState.OPEN
    ]


def choose_instance(
    strategy: LoadBalancingStrategy,
    instances: list[Instance],
    *,
    round_robin_counter: RoundRobinCounter | None = None,
    active_connections: dict[str, int] | None = None,
    health: dict[str, HealthState] | None = None,
    circuit_states: dict[str, CircuitBreakerState] | None = None,
    sticky_key: str | None = None,
    sticky_map: StickySessionMap | None = None,
) -> Instance | None:
    """Choose one instance to route this call to, or ``None`` if none are viable.

    Health-aware filtering and circuit-breaker filtering ("Failover")
    are applied *first*, before any strategy-specific selection --
    "Health-aware Routing" is cross-cutting, not one strategy among
    several, so even a plain ``ROUND_ROBIN`` service never routes to a
    known-unhealthy or breaker-open instance. ``None`` means every
    instance is currently excluded ("Automatic Recovery" resumes once a
    future health probe or breaker half-open trial clears one).
    """
    viable = filter_circuit_closed(filter_healthy(instances, health or {}), circuit_states or {})
    if not viable:
        return None

    if strategy == LoadBalancingStrategy.STICKY_SESSION and sticky_key is not None:
        bindings = sticky_map if sticky_map is not None else StickySessionMap()
        bound_url = bindings.get(sticky_key)
        bound_instance = next((i for i in viable if i.url == bound_url), None)
        if bound_instance is not None:
            return bound_instance
        chosen = choose_round_robin(viable, round_robin_counter or RoundRobinCounter())
        bindings.bind(sticky_key, chosen.url)
        return chosen

    if strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
        return choose_least_connections(viable, active_connections or {})

    if strategy == LoadBalancingStrategy.WEIGHTED:
        return choose_weighted(viable)

    # HEALTH_AWARE and ROUND_ROBIN both round-robin among the already
    # health/circuit-filtered set -- HEALTH_AWARE's own distinguishing
    # behaviour (excluding unhealthy instances) already happened above,
    # uniformly, for every strategy.
    return choose_round_robin(viable, round_robin_counter or RoundRobinCounter())


__all__ = [
    "Instance",
    "RoundRobinCounter",
    "StickySessionMap",
    "choose_instance",
    "choose_least_connections",
    "choose_round_robin",
    "choose_weighted",
    "filter_circuit_closed",
    "filter_healthy",
]
