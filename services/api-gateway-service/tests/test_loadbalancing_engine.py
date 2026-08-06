"""Pure tests for app/loadbalancing/engine.py -- no database, no fixtures."""

from __future__ import annotations

import pytest

from app.loadbalancing.engine import (
    Instance,
    RoundRobinCounter,
    StickySessionMap,
    choose_instance,
    choose_least_connections,
    choose_round_robin,
    choose_weighted,
    filter_circuit_closed,
    filter_healthy,
)
from app.models.enums import (
    TERMINAL_HEALTH_STATES,
    CircuitBreakerState,
    HealthState,
    LoadBalancingStrategy,
)

pytestmark = pytest.mark.asyncio


def _instance(url: str = "http://a", weight: int = 100) -> Instance:
    return Instance(url=url, weight=weight)


class TestRoundRobinCounter:
    async def test_cycles_through_indices_and_wraps_around(self) -> None:
        counter = RoundRobinCounter()
        assert counter.next_index(3) == 0
        assert counter.next_index(3) == 1
        assert counter.next_index(3) == 2
        assert counter.next_index(3) == 0

    async def test_a_non_positive_count_returns_zero_without_advancing_the_cursor(self) -> None:
        counter = RoundRobinCounter()
        assert counter.next_index(0) == 0
        assert counter.next_index(0) == 0
        # The cursor never moved, so the next real call still starts at 0.
        assert counter.next_index(2) == 0

    async def test_the_cursor_persists_across_calls_with_varying_counts(self) -> None:
        counter = RoundRobinCounter()
        assert counter.next_index(2) == 0  # cursor -> 1
        assert counter.next_index(3) == 1  # cursor -> 2
        assert counter.next_index(2) == 0  # 2 % 2 -> cursor -> 3


class TestStickySessionMap:
    async def test_an_unknown_key_returns_none(self) -> None:
        assert StickySessionMap().get("missing") is None

    async def test_bind_then_get_returns_the_bound_url(self) -> None:
        bindings = StickySessionMap()
        bindings.bind("session-1", "http://a")
        assert bindings.get("session-1") == "http://a"

    async def test_rebinding_a_key_overwrites_the_previous_binding(self) -> None:
        bindings = StickySessionMap()
        bindings.bind("session-1", "http://a")
        bindings.bind("session-1", "http://b")
        assert bindings.get("session-1") == "http://b"


class TestChooseRoundRobin:
    async def test_returns_the_index_from_the_counter(self) -> None:
        instances = [_instance("http://a"), _instance("http://b"), _instance("http://c")]
        counter = RoundRobinCounter()
        assert choose_round_robin(instances, counter).url == "http://a"
        assert choose_round_robin(instances, counter).url == "http://b"

    async def test_a_single_instance_is_always_returned(self) -> None:
        instances = [_instance("http://only")]
        counter = RoundRobinCounter()
        assert choose_round_robin(instances, counter).url == "http://only"
        assert choose_round_robin(instances, counter).url == "http://only"


class TestChooseLeastConnections:
    async def test_picks_the_instance_with_the_fewest_active_connections(self) -> None:
        instances = [_instance("http://a"), _instance("http://b")]
        chosen = choose_least_connections(instances, {"http://a": 5, "http://b": 1})
        assert chosen.url == "http://b"

    async def test_an_instance_absent_from_active_connections_is_treated_as_zero(self) -> None:
        instances = [_instance("http://a"), _instance("http://b")]
        chosen = choose_least_connections(instances, {"http://a": 5})
        assert chosen.url == "http://b"

    async def test_ties_resolve_to_the_first_instance_in_iteration_order(self) -> None:
        instances = [_instance("http://a"), _instance("http://b")]
        chosen = choose_least_connections(instances, {"http://a": 2, "http://b": 2})
        assert chosen.url == "http://a"


class TestChooseWeighted:
    async def test_a_low_pick_selects_the_first_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        instances = [_instance("http://a", weight=30), _instance("http://b", weight=70)]
        monkeypatch.setattr("app.loadbalancing.engine.random.uniform", lambda _a, _b: 10.0)
        assert choose_weighted(instances).url == "http://a"

    async def test_a_high_pick_selects_the_second_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        instances = [_instance("http://a", weight=30), _instance("http://b", weight=70)]
        monkeypatch.setattr("app.loadbalancing.engine.random.uniform", lambda _a, _b: 50.0)
        assert choose_weighted(instances).url == "http://b"

    async def test_zero_weight_everywhere_still_returns_the_first_instance_on_pick_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        instances = [_instance("http://a", weight=0), _instance("http://b", weight=0)]
        monkeypatch.setattr("app.loadbalancing.engine.random.uniform", lambda _a, _b: 0.0)
        assert choose_weighted(instances).url == "http://a"

    async def test_a_pick_exceeding_every_running_total_falls_back_to_the_last_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        instances = [_instance("http://a", weight=10), _instance("http://b", weight=20)]
        monkeypatch.setattr("app.loadbalancing.engine.random.uniform", lambda _a, _b: 999.0)
        assert choose_weighted(instances).url == "http://b"


class TestFilterHealthy:
    async def test_an_instance_never_probed_is_treated_as_healthy(self) -> None:
        instances = [_instance("http://a")]
        assert filter_healthy(instances, {}) == instances

    @pytest.mark.parametrize(
        "state",
        [HealthState.HEALTHY, HealthState.DEGRADED, HealthState.WARNING, HealthState.UNKNOWN],
    )
    async def test_non_terminal_states_are_kept(self, state: HealthState) -> None:
        instances = [_instance("http://a")]
        assert filter_healthy(instances, {"http://a": state}) == instances

    @pytest.mark.parametrize("state", [HealthState.UNHEALTHY, HealthState.MAINTENANCE])
    async def test_terminal_states_are_excluded(self, state: HealthState) -> None:
        instances = [_instance("http://a")]
        assert filter_healthy(instances, {"http://a": state}) == []

    async def test_only_the_terminal_instance_is_removed_from_a_mixed_list(self) -> None:
        healthy = _instance("http://healthy")
        unhealthy = _instance("http://unhealthy")
        result = filter_healthy([healthy, unhealthy], {"http://unhealthy": HealthState.UNHEALTHY})
        assert result == [healthy]


class TestFilterCircuitClosed:
    async def test_an_instance_with_no_recorded_circuit_state_is_treated_as_closed(self) -> None:
        instances = [_instance("http://a")]
        assert filter_circuit_closed(instances, {}) == instances

    async def test_closed_is_kept(self) -> None:
        instances = [_instance("http://a")]
        result = filter_circuit_closed(instances, {"http://a": CircuitBreakerState.CLOSED})
        assert result == instances

    async def test_half_open_is_kept(self) -> None:
        instances = [_instance("http://a")]
        result = filter_circuit_closed(instances, {"http://a": CircuitBreakerState.HALF_OPEN})
        assert result == instances

    async def test_open_is_excluded(self) -> None:
        instances = [_instance("http://a")]
        result = filter_circuit_closed(instances, {"http://a": CircuitBreakerState.OPEN})
        assert result == []


class TestChooseInstance:
    async def test_no_instances_returns_none(self) -> None:
        result = choose_instance(LoadBalancingStrategy.ROUND_ROBIN, [])
        assert result is None

    async def test_every_instance_excluded_by_health_returns_none(self) -> None:
        instances = [_instance("http://a")]
        result = choose_instance(
            LoadBalancingStrategy.ROUND_ROBIN,
            instances,
            health={"http://a": HealthState.UNHEALTHY},
        )
        assert result is None

    async def test_every_instance_excluded_by_open_circuit_returns_none(self) -> None:
        instances = [_instance("http://a")]
        result = choose_instance(
            LoadBalancingStrategy.ROUND_ROBIN,
            instances,
            circuit_states={"http://a": CircuitBreakerState.OPEN},
        )
        assert result is None

    async def test_terminal_health_states_are_never_selected_regardless_of_strategy(self) -> None:
        healthy = _instance("http://healthy")
        unhealthy = _instance("http://unhealthy")
        health = {"http://unhealthy": HealthState.UNHEALTHY}
        assert HealthState.UNHEALTHY in TERMINAL_HEALTH_STATES
        for _ in range(5):
            chosen = choose_instance(
                LoadBalancingStrategy.ROUND_ROBIN, [unhealthy, healthy], health=health
            )
            assert chosen is not None
            assert chosen.url == "http://healthy"

    async def test_round_robin_with_no_explicit_counter_always_returns_the_first_viable_instance(
        self,
    ) -> None:
        instances = [_instance("http://a"), _instance("http://b")]
        first_call = choose_instance(LoadBalancingStrategy.ROUND_ROBIN, instances)
        second_call = choose_instance(LoadBalancingStrategy.ROUND_ROBIN, instances)
        assert first_call.url == "http://a"
        assert second_call.url == "http://a"  # a fresh counter is created each call by default

    async def test_round_robin_with_a_shared_counter_advances_across_calls(self) -> None:
        instances = [_instance("http://a"), _instance("http://b")]
        counter = RoundRobinCounter()
        first_call = choose_instance(
            LoadBalancingStrategy.ROUND_ROBIN, instances, round_robin_counter=counter
        )
        second_call = choose_instance(
            LoadBalancingStrategy.ROUND_ROBIN, instances, round_robin_counter=counter
        )
        assert first_call.url == "http://a"
        assert second_call.url == "http://b"

    async def test_least_connections_picks_the_least_busy_viable_instance(self) -> None:
        instances = [_instance("http://a"), _instance("http://b")]
        result = choose_instance(
            LoadBalancingStrategy.LEAST_CONNECTIONS,
            instances,
            active_connections={"http://a": 9, "http://b": 1},
        )
        assert result.url == "http://b"

    async def test_weighted_uses_weighted_random_choice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        instances = [_instance("http://a", weight=30), _instance("http://b", weight=70)]
        monkeypatch.setattr("app.loadbalancing.engine.random.uniform", lambda _a, _b: 50.0)
        result = choose_instance(LoadBalancingStrategy.WEIGHTED, instances)
        assert result.url == "http://b"

    async def test_health_aware_excludes_unhealthy_instances_and_then_round_robins(self) -> None:
        healthy_a = _instance("http://a")
        healthy_b = _instance("http://b")
        unhealthy = _instance("http://c")
        health = {"http://c": HealthState.UNHEALTHY}
        counter = RoundRobinCounter()
        first = choose_instance(
            LoadBalancingStrategy.HEALTH_AWARE,
            [healthy_a, healthy_b, unhealthy],
            health=health,
            round_robin_counter=counter,
        )
        second = choose_instance(
            LoadBalancingStrategy.HEALTH_AWARE,
            [healthy_a, healthy_b, unhealthy],
            health=health,
            round_robin_counter=counter,
        )
        assert {first.url, second.url} == {"http://a", "http://b"}

    async def test_sticky_session_with_no_sticky_key_falls_back_to_round_robin(self) -> None:
        instances = [_instance("http://a"), _instance("http://b")]
        result = choose_instance(LoadBalancingStrategy.STICKY_SESSION, instances, sticky_key=None)
        assert result.url == "http://a"

    async def test_sticky_session_binds_on_first_use_and_reuses_the_binding(self) -> None:
        instances = [_instance("http://a"), _instance("http://b")]
        sticky_map = StickySessionMap()
        first = choose_instance(
            LoadBalancingStrategy.STICKY_SESSION,
            instances,
            sticky_key="session-1",
            sticky_map=sticky_map,
        )
        # Reversing instance order proves the second lookup is a genuine bound-URL match,
        # not an accidental repeat of round-robin's index 0.
        second = choose_instance(
            LoadBalancingStrategy.STICKY_SESSION,
            list(reversed(instances)),
            sticky_key="session-1",
            sticky_map=sticky_map,
        )
        assert first.url == second.url
        assert sticky_map.get("session-1") == first.url

    async def test_sticky_session_without_a_shared_map_never_actually_sticks(self) -> None:
        instances = [_instance("http://a"), _instance("http://b")]
        first = choose_instance(
            LoadBalancingStrategy.STICKY_SESSION, instances, sticky_key="session-1"
        )
        second = choose_instance(
            LoadBalancingStrategy.STICKY_SESSION, instances, sticky_key="session-1"
        )
        # Each call builds a fresh StickySessionMap when none is supplied, so nothing persists.
        assert first.url == "http://a"
        assert second.url == "http://a"

    async def test_sticky_session_rebinds_when_the_bound_instance_is_no_longer_viable(self) -> None:
        instances = [_instance("http://a"), _instance("http://b")]
        sticky_map = StickySessionMap()
        sticky_map.bind("session-1", "http://a")
        result = choose_instance(
            LoadBalancingStrategy.STICKY_SESSION,
            instances,
            sticky_key="session-1",
            sticky_map=sticky_map,
            health={"http://a": HealthState.UNHEALTHY},
        )
        assert result.url == "http://b"
        assert sticky_map.get("session-1") == "http://b"
