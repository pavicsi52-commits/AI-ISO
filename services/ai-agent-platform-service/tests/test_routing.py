"""Model-provider routing strategy resolution (docs/060 "MODEL ROUTING").

Everything in ``app/routing/engine.py`` is a pure function over enums
and dataclasses -- no network call, no database, no fixture beyond the
inputs a test builds itself. These tests exercise all four
``RoutingStrategy`` values and every branch of ``resolve_order``'s own
helpers with real inputs.
"""

from __future__ import annotations

from app.models.enums import ModelProvider, RoutingStrategy
from app.routing.engine import (
    ProviderCost,
    order_by_cost,
    order_by_fallback,
    order_by_latency,
    order_by_rules,
    resolve_order,
)


class TestProviderCost:
    def test_average_is_the_mean_of_prompt_and_completion(self) -> None:
        cost = ProviderCost(prompt_usd_per_1k=0.01, completion_usd_per_1k=0.03)
        assert cost.average_usd_per_1k == 0.02

    def test_equal_prompt_and_completion_cost(self) -> None:
        cost = ProviderCost(prompt_usd_per_1k=0.02, completion_usd_per_1k=0.02)
        assert cost.average_usd_per_1k == 0.02


class TestOrderByFallback:
    def test_default_first_then_fallbacks_in_order(self) -> None:
        chain = order_by_fallback(
            ModelProvider.OPENAI, [ModelProvider.ANTHROPIC, ModelProvider.OLLAMA]
        )
        assert chain == [ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.OLLAMA]

    def test_default_repeated_in_fallbacks_is_not_duplicated(self) -> None:
        chain = order_by_fallback(
            ModelProvider.OPENAI, [ModelProvider.OPENAI, ModelProvider.ANTHROPIC]
        )
        assert chain == [ModelProvider.OPENAI, ModelProvider.ANTHROPIC]

    def test_no_fallbacks_is_just_the_default(self) -> None:
        assert order_by_fallback(ModelProvider.OLLAMA, []) == [ModelProvider.OLLAMA]


class TestOrderByCost:
    def test_cheapest_first(self) -> None:
        costs = {
            ModelProvider.OPENAI: ProviderCost(0.03, 0.06),
            ModelProvider.ANTHROPIC: ProviderCost(0.003, 0.015),
            ModelProvider.OLLAMA: ProviderCost(0.0, 0.0),
        }
        ordered = order_by_cost(
            [ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.OLLAMA], costs
        )
        assert ordered == [ModelProvider.OLLAMA, ModelProvider.ANTHROPIC, ModelProvider.OPENAI]

    def test_unpriced_candidate_sorts_last(self) -> None:
        # An unpriced provider is not necessarily free -- treating it as
        # such would silently prefer an unmeasured provider over every
        # priced one.
        costs = {ModelProvider.ANTHROPIC: ProviderCost(0.003, 0.015)}
        ordered = order_by_cost([ModelProvider.OPENAI, ModelProvider.ANTHROPIC], costs)
        assert ordered == [ModelProvider.ANTHROPIC, ModelProvider.OPENAI]

    def test_no_costs_at_all_preserves_relative_order(self) -> None:
        ordered = order_by_cost([ModelProvider.OPENAI, ModelProvider.OLLAMA], {})
        assert ordered == [ModelProvider.OPENAI, ModelProvider.OLLAMA]


class TestOrderByLatency:
    def test_fastest_observed_first(self) -> None:
        latencies = {
            ModelProvider.OPENAI: 800.0,
            ModelProvider.ANTHROPIC: 150.0,
            ModelProvider.OLLAMA: 40.0,
        }
        ordered = order_by_latency(
            [ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.OLLAMA], latencies
        )
        assert ordered == [ModelProvider.OLLAMA, ModelProvider.ANTHROPIC, ModelProvider.OPENAI]

    def test_unmeasured_candidate_sorts_last(self) -> None:
        # Optimistically assuming an unmeasured provider is fast would
        # defeat the point of latency-aware routing the first time it
        # actually matters.
        latencies = {ModelProvider.ANTHROPIC: 100.0}
        ordered = order_by_latency([ModelProvider.OPENAI, ModelProvider.ANTHROPIC], latencies)
        assert ordered == [ModelProvider.ANTHROPIC, ModelProvider.OPENAI]

    def test_no_observations_at_all_preserves_relative_order(self) -> None:
        ordered = order_by_latency([ModelProvider.OPENAI, ModelProvider.OLLAMA], {})
        assert ordered == [ModelProvider.OPENAI, ModelProvider.OLLAMA]


class TestOrderByRules:
    def test_no_rules_returns_candidates_unchanged(self) -> None:
        candidates = [ModelProvider.OPENAI, ModelProvider.ANTHROPIC]
        assert order_by_rules(candidates, [], {}) == candidates

    def test_first_matching_rule_wins(self) -> None:
        rules = [
            ("tier == 'gold'", ModelProvider.ANTHROPIC),
            ("tier == 'silver'", ModelProvider.OPENAI),
        ]
        ordered = order_by_rules(
            [ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.OLLAMA],
            rules,
            {"tier": "gold"},
        )
        assert ordered == [ModelProvider.ANTHROPIC, ModelProvider.OPENAI, ModelProvider.OLLAMA]

    def test_only_the_first_matching_rule_applies(self) -> None:
        # Two rules both match; only the earlier one's provider may win.
        rules = [
            ("tier == 'gold'", ModelProvider.ANTHROPIC),
            ("tier == 'gold'", ModelProvider.OLLAMA),
        ]
        ordered = order_by_rules(
            [ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.OLLAMA],
            rules,
            {"tier": "gold"},
        )
        assert ordered[0] == ModelProvider.ANTHROPIC

    def test_no_rule_matches_returns_candidates_unchanged(self) -> None:
        rules = [("tier == 'gold'", ModelProvider.ANTHROPIC)]
        candidates = [ModelProvider.OPENAI, ModelProvider.OLLAMA]
        assert order_by_rules(candidates, rules, {"tier": "bronze"}) == candidates

    def test_winner_outside_the_original_candidates_is_still_placed_first(self) -> None:
        # resolve_order narrows `candidates` to whatever is actually
        # configured before this ever runs, so a rule naming a provider
        # that was never offered is a real state this must handle, not
        # a hypothetical: the caller (ModelRegistry.chat) still tries it
        # and fails over to the rest of the chain when it isn't
        # registered.
        rules = [("go", ModelProvider.AZURE_OPENAI)]
        ordered = order_by_rules([ModelProvider.OPENAI, ModelProvider.OLLAMA], rules, {"go": True})
        assert ordered == [ModelProvider.AZURE_OPENAI, ModelProvider.OPENAI, ModelProvider.OLLAMA]


class TestResolveOrder:
    def test_fallback_strategy_is_the_default_chain_plus_the_rest(self) -> None:
        chain = resolve_order(
            RoutingStrategy.FALLBACK,
            default_provider=ModelProvider.OPENAI,
            candidates=[ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.OLLAMA],
            fallback_providers=[ModelProvider.ANTHROPIC],
        )
        assert chain == [ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.OLLAMA]

    def test_default_provider_outside_candidates_is_dropped(self) -> None:
        # A strategy never recommends a provider the caller didn't offer.
        chain = resolve_order(
            RoutingStrategy.FALLBACK,
            default_provider=ModelProvider.OPENAI,
            candidates=[ModelProvider.OLLAMA, ModelProvider.ANTHROPIC],
        )
        assert ModelProvider.OPENAI not in chain
        assert chain == [ModelProvider.OLLAMA, ModelProvider.ANTHROPIC]

    def test_cost_aware_strategy_sorts_the_narrowed_pool_by_price(self) -> None:
        chain = resolve_order(
            RoutingStrategy.COST_AWARE,
            default_provider=ModelProvider.OPENAI,
            candidates=[ModelProvider.OPENAI, ModelProvider.OLLAMA],
            costs={
                ModelProvider.OPENAI: ProviderCost(0.03, 0.06),
                ModelProvider.OLLAMA: ProviderCost(0.0, 0.0),
            },
        )
        assert chain == [ModelProvider.OLLAMA, ModelProvider.OPENAI]

    def test_latency_aware_strategy_sorts_the_narrowed_pool_by_speed(self) -> None:
        chain = resolve_order(
            RoutingStrategy.LATENCY_AWARE,
            default_provider=ModelProvider.OPENAI,
            candidates=[ModelProvider.OPENAI, ModelProvider.OLLAMA],
            observed_latency_ms={ModelProvider.OPENAI: 500.0, ModelProvider.OLLAMA: 20.0},
        )
        assert chain == [ModelProvider.OLLAMA, ModelProvider.OPENAI]

    def test_rule_based_strategy_applies_the_first_matching_rule(self) -> None:
        chain = resolve_order(
            RoutingStrategy.RULE_BASED,
            default_provider=ModelProvider.OPENAI,
            candidates=[ModelProvider.OPENAI, ModelProvider.ANTHROPIC],
            rules=[("urgent", ModelProvider.ANTHROPIC)],
            variables={"urgent": True},
        )
        assert chain == [ModelProvider.ANTHROPIC, ModelProvider.OPENAI]

    def test_rule_based_strategy_with_no_rules_behaves_like_fallback(self) -> None:
        chain = resolve_order(
            RoutingStrategy.RULE_BASED,
            default_provider=ModelProvider.OPENAI,
            candidates=[ModelProvider.OPENAI, ModelProvider.OLLAMA],
        )
        assert chain == [ModelProvider.OPENAI, ModelProvider.OLLAMA]

    def test_every_narrowing_strategy_offers_only_the_given_candidates(self) -> None:
        # True for fallback/cost-aware/latency-aware; rule-based has its
        # own explicit override, covered separately above.
        for strategy in (
            RoutingStrategy.FALLBACK,
            RoutingStrategy.COST_AWARE,
            RoutingStrategy.LATENCY_AWARE,
        ):
            chain = resolve_order(
                strategy,
                default_provider=ModelProvider.AZURE_OPENAI,
                candidates=[ModelProvider.OLLAMA],
            )
            assert chain == [ModelProvider.OLLAMA], strategy

    def test_default_provider_present_and_fallback_providers_reordered(self) -> None:
        # candidates lists OLLAMA before ANTHROPIC, but the fallback
        # chain is [default, *fallback_providers] first -- the pool
        # follows that order, not the candidates' own order, for
        # whichever of them were named explicitly.
        chain = resolve_order(
            RoutingStrategy.FALLBACK,
            default_provider=ModelProvider.ANTHROPIC,
            candidates=[ModelProvider.OLLAMA, ModelProvider.ANTHROPIC, ModelProvider.OPENAI],
            fallback_providers=[ModelProvider.OPENAI],
        )
        assert chain == [ModelProvider.ANTHROPIC, ModelProvider.OPENAI, ModelProvider.OLLAMA]
