"""Pure tests for app/filters/engine.py -- no database, no fixtures."""

from __future__ import annotations

import pytest

from app.filters.engine import evaluate_rule, evaluate_rules
from app.models.enums import FilterMatchMode


def _rule(field: str, operator: str, value: object = None) -> dict:
    return {"field": field, "operator": operator, "value": value}


class TestResolveFieldViaEvaluateRule:
    """`_resolve_field` has no public name -- exercised indirectly through `evaluate_rule`."""

    def test_top_level_field(self) -> None:
        assert evaluate_rule({"kind": "order"}, _rule("kind", "eq", "order")) is True

    def test_dotted_path_two_levels(self) -> None:
        attrs = {"labels": {"team": "payments"}}
        assert evaluate_rule(attrs, _rule("labels.team", "eq", "payments")) is True

    def test_dotted_path_three_levels(self) -> None:
        attrs = {"a": {"b": {"c": "deep"}}}
        assert evaluate_rule(attrs, _rule("a.b.c", "eq", "deep")) is True

    def test_missing_top_level_key_resolves_to_none(self) -> None:
        assert evaluate_rule({}, _rule("missing", "exists")) is False

    def test_missing_intermediate_key_resolves_to_none(self) -> None:
        attrs = {"labels": {}}
        assert evaluate_rule(attrs, _rule("labels.team", "exists")) is False

    def test_non_mapping_intermediate_value_resolves_to_none(self) -> None:
        # "labels" is a plain string, not a Mapping -- ".team" cannot descend into it.
        attrs = {"labels": "not-a-mapping"}
        assert evaluate_rule(attrs, _rule("labels.team", "exists")) is False


class TestEvaluateRuleOperators:
    def test_eq_matches(self) -> None:
        assert evaluate_rule({"status": "open"}, _rule("status", "eq", "open")) is True

    def test_eq_mismatches(self) -> None:
        assert evaluate_rule({"status": "open"}, _rule("status", "eq", "closed")) is False

    def test_operator_defaults_to_eq_when_omitted(self) -> None:
        rule = {"field": "status", "value": "open"}
        assert evaluate_rule({"status": "open"}, rule) is True

    def test_field_defaults_to_empty_string_when_omitted(self) -> None:
        rule = {"operator": "exists"}
        assert evaluate_rule({"": "present"}, rule) is True

    def test_ne_matches_on_difference(self) -> None:
        assert evaluate_rule({"status": "open"}, _rule("status", "ne", "closed")) is True

    def test_ne_mismatches_on_equality(self) -> None:
        assert evaluate_rule({"status": "open"}, _rule("status", "ne", "open")) is False

    def test_in_matches_when_value_present(self) -> None:
        rule = _rule("status", "in", ["open", "pending"])
        assert evaluate_rule({"status": "open"}, rule) is True

    def test_in_mismatches_when_value_absent(self) -> None:
        rule = _rule("status", "in", ["closed"])
        assert evaluate_rule({"status": "open"}, rule) is False

    def test_in_with_no_expected_value_is_defensively_false(self) -> None:
        rule = {"field": "status", "operator": "in"}
        assert evaluate_rule({"status": "open"}, rule) is False

    def test_not_in_matches_when_value_absent(self) -> None:
        rule = _rule("status", "not_in", ["closed"])
        assert evaluate_rule({"status": "open"}, rule) is True

    def test_not_in_mismatches_when_value_present(self) -> None:
        rule = _rule("status", "not_in", ["open", "pending"])
        assert evaluate_rule({"status": "open"}, rule) is False

    def test_not_in_with_no_expected_value_is_defensively_true(self) -> None:
        rule = {"field": "status", "operator": "not_in"}
        assert evaluate_rule({"status": "open"}, rule) is True

    def test_contains_matches_within_a_string(self) -> None:
        rule = _rule("message", "contains", "err")
        assert evaluate_rule({"message": "an error occurred"}, rule) is True

    def test_contains_matches_within_a_list(self) -> None:
        rule = _rule("tags", "contains", "urgent")
        assert evaluate_rule({"tags": ["urgent", "billing"]}, rule) is True

    def test_contains_mismatches_when_absent(self) -> None:
        rule = _rule("message", "contains", "zzz")
        assert evaluate_rule({"message": "an error occurred"}, rule) is False

    def test_contains_on_a_value_without_contains_support_is_false(self) -> None:
        # An int has no __contains__ -- the operator must not raise, just fail closed.
        rule = _rule("count", "contains", 1)
        assert evaluate_rule({"count": 42}, rule) is False

    def test_gt_matches(self) -> None:
        assert evaluate_rule({"count": 5}, _rule("count", "gt", 3)) is True

    def test_gt_mismatches(self) -> None:
        assert evaluate_rule({"count": 2}, _rule("count", "gt", 3)) is False

    def test_lt_matches(self) -> None:
        assert evaluate_rule({"count": 2}, _rule("count", "lt", 3)) is True

    def test_lt_mismatches(self) -> None:
        assert evaluate_rule({"count": 5}, _rule("count", "lt", 3)) is False

    def test_exists_true_when_field_present(self) -> None:
        assert evaluate_rule({"status": "open"}, _rule("status", "exists")) is True

    def test_exists_false_when_field_absent(self) -> None:
        assert evaluate_rule({}, _rule("status", "exists")) is False

    def test_exists_false_when_field_value_is_none(self) -> None:
        assert evaluate_rule({"status": None}, _rule("status", "exists")) is False

    @pytest.mark.parametrize("operator", ["eq", "ne", "in", "not_in", "contains", "gt", "lt"])
    def test_a_missing_field_always_fails_non_exists_operators(self, operator: str) -> None:
        # `actual is None` short-circuits every operator but `exists` to False -- even `ne`,
        # where "missing != expected" might intuitively seem like it should match.
        rule = _rule("missing", operator, "anything")
        assert evaluate_rule({}, rule) is False

    def test_unrecognised_operator_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unrecognised filter operator"):
            evaluate_rule({"status": "open"}, _rule("status", "bogus", "open"))


class TestEvaluateRules:
    def test_empty_rules_always_matches(self) -> None:
        assert evaluate_rules({"status": "open"}, []) is True

    def test_empty_rules_matches_even_with_any_mode(self) -> None:
        assert evaluate_rules({}, [], match_mode=FilterMatchMode.ANY) is True

    def test_default_match_mode_is_all(self) -> None:
        rules = [_rule("a", "eq", 1), _rule("b", "eq", 2)]
        assert evaluate_rules({"a": 1, "b": 2}, rules) is True

    def test_all_mode_requires_every_rule_to_match(self) -> None:
        rules = [_rule("a", "eq", 1), _rule("b", "eq", 999)]
        assert evaluate_rules({"a": 1, "b": 2}, rules, match_mode=FilterMatchMode.ALL) is False

    def test_all_mode_passes_when_every_rule_matches(self) -> None:
        rules = [_rule("a", "eq", 1), _rule("b", "eq", 2)]
        assert evaluate_rules({"a": 1, "b": 2}, rules, match_mode=FilterMatchMode.ALL) is True

    def test_any_mode_passes_when_at_least_one_rule_matches(self) -> None:
        rules = [_rule("a", "eq", 999), _rule("b", "eq", 2)]
        assert evaluate_rules({"a": 1, "b": 2}, rules, match_mode=FilterMatchMode.ANY) is True

    def test_any_mode_fails_when_no_rule_matches(self) -> None:
        rules = [_rule("a", "eq", 999), _rule("b", "eq", 998)]
        assert evaluate_rules({"a": 1, "b": 2}, rules, match_mode=FilterMatchMode.ANY) is False
