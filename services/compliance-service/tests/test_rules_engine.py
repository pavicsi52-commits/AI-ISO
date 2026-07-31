"""The control rule evaluator.

Pure: no fixtures, no database, no clock these tests did not supply.
That is the point of the module and the reason this file can afford to
be exhaustive about the operators -- an operator that is subtly wrong
produces a compliance verdict that is confidently wrong, and nobody
re-derives a verdict.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from shared_core.exceptions.validation import ValidationError

from app.rules.engine import (
    MAX_PATH_DEPTH,
    MAX_PATTERN_LENGTH,
    MAX_RULE_DEPTH,
    MISSING,
    Check,
    CheckOperator,
    LogicalOperator,
    Rule,
    describe_failures,
    evaluate_check,
    evaluate_rule,
    referenced_paths,
    resolve,
    rule_from_dict,
    rule_to_dict,
    validate_path,
    validate_rule,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def check(path: str, operator: CheckOperator, value: Any = None, **kwargs: Any) -> Check:
    return Check(path=path, operator=operator, value=value, **kwargs)


def decide(payload: dict[str, Any], one: Check, *, now: datetime = NOW) -> bool:
    return evaluate_check(one, payload, now=now).passed


class TestPathResolution:
    def test_a_dotted_path_walks_nested_objects(self) -> None:
        assert resolve({"ssh": {"port": 22}}, "ssh.port") == 22

    def test_a_numeric_segment_indexes_a_list(self) -> None:
        payload = {"users": [{"name": "root"}, {"name": "app"}]}
        assert resolve(payload, "users.1.name") == "app"

    @pytest.mark.parametrize(
        "path",
        ["ssh.missing", "missing.port", "ssh.port.deeper", "users.9.name", "users.x"],
    )
    def test_an_unreachable_path_is_missing_not_none(self, path: str) -> None:
        # The distinction the whole module rests on. A collector that
        # never reported `ssh` must not satisfy a check about it.
        payload = {"ssh": {"port": 22}, "users": [{"name": "root"}]}
        assert resolve(payload, path) is MISSING

    def test_a_stored_null_is_none_not_missing(self) -> None:
        # "The collector reported null" and "the collector never
        # reported this" are different facts, and an operator must be
        # able to tell them apart.
        assert resolve({"tls": None}, "tls") is None

    @pytest.mark.parametrize("path", ["", "   ", "a..b", "a." + "b." * MAX_PATH_DEPTH])
    def test_a_path_that_cannot_address_anything_is_refused(self, path: str) -> None:
        with pytest.raises(ValidationError):
            validate_path(path)


class TestOperators:
    @pytest.mark.parametrize(
        ("operator", "value", "observed", "expected"),
        [
            (CheckOperator.EQUALS, "no", "no", True),
            (CheckOperator.EQUALS, "no", "yes", False),
            (CheckOperator.NOT_EQUALS, "yes", "no", True),
            (CheckOperator.IN, ["no", "prohibit-password"], "no", True),
            (CheckOperator.IN, ["no"], "yes", False),
            (CheckOperator.NOT_IN, ["yes"], "no", True),
            (CheckOperator.CONTAINS, "tls", "use-tls-only", True),
            (CheckOperator.CONTAINS, "x", ["a", "b"], False),
            (CheckOperator.NOT_CONTAINS, "x", ["a"], True),
            (CheckOperator.STARTS_WITH, "prod", "prod-web-1", True),
            (CheckOperator.ENDS_WITH, "-1", "prod-web-1", True),
            (CheckOperator.MATCHES, r"^prod-", "prod-web-1", True),
            (CheckOperator.MATCHES, r"^prod-", "dev-web-1", False),
            (CheckOperator.NOT_MATCHES, r"^dev-", "prod-web-1", True),
            (CheckOperator.GREATER_THAN, 1.1, 1.2, True),
            (CheckOperator.GREATER_OR_EQUAL, 1.2, 1.2, True),
            (CheckOperator.LESS_THAN, 10, 5, True),
            (CheckOperator.LESS_OR_EQUAL, 5, 5, True),
            (CheckOperator.BETWEEN, [-5, 5], 0, True),
            (CheckOperator.BETWEEN, [-5, 5], 9, False),
            (CheckOperator.IS_TRUE, None, True, True),
            (CheckOperator.IS_FALSE, None, False, True),
            (CheckOperator.IS_EMPTY, None, [], True),
            (CheckOperator.IS_NOT_EMPTY, None, ["zone-a"], True),
            (CheckOperator.SUBSET_OF, ["a", "b", "c"], ["a", "b"], True),
            (CheckOperator.SUPERSET_OF, ["a"], ["a", "b"], True),
            (CheckOperator.INTERSECTS, ["a", "z"], ["a", "b"], True),
            (CheckOperator.INTERSECTS, ["z"], ["a", "b"], False),
            (CheckOperator.CIDR_CONTAINS, "10.0.0.0/8", "10.1.2.3", True),
            (CheckOperator.CIDR_CONTAINS, "10.0.0.0/8", "192.168.1.1", False),
            (CheckOperator.COUNT_EQUALS, 2, ["a", "b"], True),
            (CheckOperator.COUNT_AT_LEAST, 1, ["a"], True),
            (CheckOperator.COUNT_AT_MOST, 0, [], True),
            (CheckOperator.COUNT_AT_MOST, 0, ["a"], False),
        ],
    )
    def test_each_operator_decides_what_it_says(
        self, operator: CheckOperator, value: Any, observed: Any, expected: bool
    ) -> None:
        assert decide({"x": observed}, check("x", operator, value)) is expected

    def test_exists_distinguishes_absent_from_null(self) -> None:
        assert decide({"tls": None}, check("tls", CheckOperator.EXISTS)) is True
        assert decide({}, check("tls", CheckOperator.EXISTS)) is False
        assert decide({}, check("tls", CheckOperator.NOT_EXISTS)) is True

    @pytest.mark.parametrize(
        "operator",
        [
            CheckOperator.EQUALS,
            CheckOperator.GREATER_OR_EQUAL,
            CheckOperator.CONTAINS,
            CheckOperator.IN,
            CheckOperator.STARTS_WITH,
            CheckOperator.MATCHES,
            CheckOperator.IS_TRUE,
            CheckOperator.COUNT_AT_LEAST,
        ],
    )
    def test_a_missing_attribute_never_satisfies_a_check(self, operator: CheckOperator) -> None:
        # The single most important property in the module. A control
        # asserting `tls.min_version >= 1.2` must not pass because the
        # collector never reported `tls` at all -- that is how a
        # compliance tool comes to certify hosts it never inspected.
        assert decide({}, check("tls.min_version", operator, 1.2)) is False

    def test_a_boolean_is_not_a_number(self) -> None:
        # Python says True == 1, so `replicas >= 1` would otherwise be
        # satisfied by a collector reporting `replicas: true`.
        assert (
            decide({"replicas": True}, check("replicas", CheckOperator.GREATER_OR_EQUAL, 1))
            is False
        )

    def test_a_string_is_a_scalar_not_a_sequence(self) -> None:
        # Without this, `count_at_most 0` against the string "" would
        # pass and against "abc" would compare 3 characters.
        assert decide({"zone": "abc"}, check("zone", CheckOperator.COUNT_EQUALS, 3)) is False

    def test_a_numeric_string_still_compares_numerically(self) -> None:
        # Collectors return "1.2" as often as 1.2.
        assert decide({"v": "1.2"}, check("v", CheckOperator.GREATER_OR_EQUAL, 1.2)) is True

    def test_negate_inverts_the_outcome(self) -> None:
        assert decide({"x": 1}, check("x", CheckOperator.EQUALS, 1, negate=True)) is False

    @pytest.mark.parametrize(
        ("operator", "value", "observed"),
        [
            (CheckOperator.MATCHES, "[unclosed", "anything"),
            (CheckOperator.MATCHES, "x" * (MAX_PATTERN_LENGTH + 1), "anything"),
            (CheckOperator.MATCHES, 42, "anything"),
            (CheckOperator.CIDR_CONTAINS, "not-a-network", "10.0.0.1"),
            (CheckOperator.CIDR_CONTAINS, "10.0.0.0/8", "not-an-address"),
            (CheckOperator.BETWEEN, [1], 5),
            (CheckOperator.BETWEEN, ["a", "b"], 5),
            (CheckOperator.SUBSET_OF, "not-a-list", ["a"]),
            (CheckOperator.COUNT_AT_LEAST, "not-a-number", ["a"]),
        ],
    )
    def test_an_unusable_comparison_fails_closed_rather_than_raising(
        self, operator: CheckOperator, value: Any, observed: Any
    ) -> None:
        # An assessment must not abort because one control was authored
        # badly -- but nor may a nonsensical comparison be reported as
        # met. Failing is the only answer that is both safe and honest.
        assert decide({"x": observed}, check("x", operator, value)) is False


class TestTimeOperators:
    def test_older_than_days_measures_against_the_supplied_moment(self) -> None:
        stale = (NOW - timedelta(days=45)).isoformat()
        assert decide({"at": stale}, check("at", CheckOperator.OLDER_THAN_DAYS, 30)) is True
        assert decide({"at": stale}, check("at", CheckOperator.NEWER_THAN_DAYS, 30)) is False

    def test_newer_than_days_accepts_the_boundary(self) -> None:
        fresh = (NOW - timedelta(days=7)).isoformat()
        assert decide({"at": fresh}, check("at", CheckOperator.NEWER_THAN_DAYS, 7)) is True

    def test_a_z_suffixed_timestamp_parses(self) -> None:
        # What a JSON collector actually emits.
        assert (
            decide({"at": "2026-07-29T12:00:00Z"}, check("at", CheckOperator.NEWER_THAN_DAYS, 7))
            is True
        )

    @pytest.mark.parametrize("observed", ["not-a-date", 42, None])
    def test_an_unparseable_timestamp_fails_rather_than_raising(self, observed: Any) -> None:
        assert decide({"at": observed}, check("at", CheckOperator.NEWER_THAN_DAYS, 7)) is False

    def test_a_naive_timestamp_is_refused(self) -> None:
        # Comparing a naive timestamp against an aware one raises in
        # Python; guessing its zone would silently shift a verdict by
        # hours, which near a boundary changes the answer.
        naive = datetime(2026, 7, 29, 12, 0).isoformat()
        assert decide({"at": naive}, check("at", CheckOperator.NEWER_THAN_DAYS, 7)) is False


class TestRuleTrees:
    def test_all_requires_every_check(self) -> None:
        rule = Rule(
            name="r",
            logical_operator=LogicalOperator.ALL,
            checks=[
                check("a", CheckOperator.IS_TRUE),
                check("b", CheckOperator.IS_TRUE),
            ],
        )
        assert evaluate_rule(rule, {"a": True, "b": True}, now=NOW).passed is True
        assert evaluate_rule(rule, {"a": True, "b": False}, now=NOW).passed is False

    def test_any_requires_one(self) -> None:
        rule = Rule(
            name="r",
            logical_operator=LogicalOperator.ANY,
            checks=[check("a", CheckOperator.IS_TRUE), check("b", CheckOperator.IS_TRUE)],
        )
        assert evaluate_rule(rule, {"a": False, "b": True}, now=NOW).passed is True
        assert evaluate_rule(rule, {"a": False, "b": False}, now=NOW).passed is False

    def test_none_requires_no_match(self) -> None:
        rule = Rule(
            name="r",
            logical_operator=LogicalOperator.NONE,
            checks=[check("a", CheckOperator.IS_TRUE)],
        )
        assert evaluate_rule(rule, {"a": False}, now=NOW).passed is True
        assert evaluate_rule(rule, {"a": True}, now=NOW).passed is False

    def test_an_empty_any_is_false_not_true(self) -> None:
        # Python's any([]) is False and that is the right answer here:
        # "at least one of nothing" is not satisfied. Stated explicitly
        # because the ALL case goes the other way.
        rule = Rule(name="r", logical_operator=LogicalOperator.ANY)
        assert evaluate_rule(rule, {}, now=NOW).passed is False

    def test_an_empty_all_passes_vacuously_but_cannot_be_saved(self) -> None:
        # Evaluation is consistent -- all([]) is True -- and authoring
        # refuses it, because a control that passes unconditionally
        # certifies an estate nobody looked at.
        rule = Rule(name="r", logical_operator=LogicalOperator.ALL)
        assert evaluate_rule(rule, {}, now=NOW).passed is True
        with pytest.raises(ValidationError, match=r"passes everything|no checks"):
            validate_rule(rule)

    def test_children_combine_with_checks(self) -> None:
        rule = Rule(
            name="root",
            logical_operator=LogicalOperator.ALL,
            checks=[check("a", CheckOperator.IS_TRUE)],
            children=[
                Rule(
                    name="child",
                    logical_operator=LogicalOperator.ANY,
                    checks=[
                        check("b", CheckOperator.IS_TRUE),
                        check("c", CheckOperator.IS_TRUE),
                    ],
                )
            ],
        )
        assert evaluate_rule(rule, {"a": True, "b": False, "c": True}, now=NOW).passed is True
        assert evaluate_rule(rule, {"a": False, "b": True, "c": True}, now=NOW).passed is False

    def test_negate_inverts_a_whole_subtree(self) -> None:
        rule = Rule(
            name="r",
            logical_operator=LogicalOperator.ALL,
            checks=[check("a", CheckOperator.IS_TRUE)],
            negate=True,
        )
        assert evaluate_rule(rule, {"a": True}, now=NOW).passed is False

    def test_the_outcome_names_every_failing_check(self) -> None:
        # A control reporting only "failed" produces a finding nobody
        # can act on.
        rule = Rule(
            name="r",
            checks=[
                check("tls.min_version", CheckOperator.GREATER_OR_EQUAL, 1.2),
                check("firewall.enabled", CheckOperator.IS_TRUE),
            ],
        )
        outcome = evaluate_rule(rule, {"tls": {"min_version": 1.0}, "firewall": {}}, now=NOW)
        failures = outcome.failures()
        assert {one.path for one in failures} == {"tls.min_version", "firewall.enabled"}
        assert failures[0].observed == 1.0

    def test_failures_are_collected_from_nested_rules(self) -> None:
        rule = Rule(
            name="root",
            children=[Rule(name="child", checks=[check("a", CheckOperator.IS_TRUE)])],
        )
        assert len(evaluate_rule(rule, {"a": False}, now=NOW).failures()) == 1

    def test_the_outcome_is_json_serialisable(self) -> None:
        # It is stored on the result row, so a value json.dumps refuses
        # is a 500 at write time rather than a test failure.
        rule = Rule(name="r", checks=[check("at", CheckOperator.NEWER_THAN_DAYS, 7)])
        outcome = evaluate_rule(rule, {"at": NOW.isoformat()}, now=NOW)
        assert json.dumps(outcome.as_dict())

    def test_a_missing_observation_serialises_as_null_not_a_sentinel(self) -> None:
        rule = Rule(name="r", checks=[check("nope", CheckOperator.EXISTS)])
        payload = json.loads(json.dumps(evaluate_rule(rule, {}, now=NOW).as_dict()))
        assert payload["checks"][0]["observed"] is None


class TestAuthoring:
    def test_a_rule_that_nests_too_deep_is_refused(self) -> None:
        deepest = Rule(name="leaf", checks=[check("a", CheckOperator.EXISTS)])
        for index in range(MAX_RULE_DEPTH + 2):
            deepest = Rule(name=f"n{index}", children=[deepest])
        with pytest.raises(ValidationError, match="nests deeper"):
            validate_rule(deepest)

    def test_a_rule_with_too_many_checks_is_refused(self) -> None:
        rule = Rule(name="r", checks=[check(f"p{i}", CheckOperator.EXISTS) for i in range(101)])
        with pytest.raises(ValidationError, match="maximum"):
            validate_rule(rule)

    def test_a_rule_naming_an_unusable_path_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            validate_rule(Rule(name="r", checks=[check("", CheckOperator.EXISTS)]))

    def test_a_child_is_validated_too(self) -> None:
        rule = Rule(name="root", children=[Rule(name="child")])
        with pytest.raises(ValidationError):
            validate_rule(rule)

    def test_a_rule_round_trips_through_its_stored_form(self) -> None:
        rule = Rule(
            name="root",
            logical_operator=LogicalOperator.ANY,
            checks=[check("a.b", CheckOperator.IN, ["x", "y"], negate=True)],
            children=[Rule(name="child", checks=[check("c", CheckOperator.IS_TRUE)])],
            negate=True,
            description="why",
        )
        restored = rule_from_dict(rule_to_dict(rule))
        assert rule_to_dict(restored) == rule_to_dict(rule)
        assert evaluate_rule(restored, {"a": {"b": "z"}, "c": True}, now=NOW).passed == (
            evaluate_rule(rule, {"a": {"b": "z"}, "c": True}, now=NOW).passed
        )

    def test_a_stored_rule_naming_a_dead_operator_fails_loudly(self) -> None:
        # A control silently degrading to "no rule" would evaluate as
        # NOT_ASSESSED forever while still looking configured.
        with pytest.raises(ValidationError, match="unknown operator"):
            rule_from_dict({"checks": [{"path": "a", "operator": "telepathy"}]})

    def test_a_stored_rule_naming_a_dead_combinator_fails_loudly(self) -> None:
        with pytest.raises(ValidationError, match="unknown combinator"):
            rule_from_dict({"logical_operator": "maybe"})

    @pytest.mark.parametrize("data", [{"checks": ["not-an-object"]}, "not-an-object", 42])
    def test_a_malformed_stored_rule_is_refused(self, data: Any) -> None:
        with pytest.raises(ValidationError):
            rule_from_dict(data)

    def test_a_stored_rule_that_nests_too_deep_is_refused(self) -> None:
        data: dict[str, Any] = {"checks": [{"path": "a", "operator": "exists"}]}
        for _ in range(MAX_RULE_DEPTH + 2):
            data = {"children": [data]}
        with pytest.raises(ValidationError, match="nests deeper"):
            rule_from_dict(data)

    def test_referenced_paths_lists_what_a_collector_must_produce(self) -> None:
        rule = Rule(
            name="root",
            checks=[check("b", CheckOperator.EXISTS), check("a", CheckOperator.EXISTS)],
            children=[Rule(name="c", checks=[check("a", CheckOperator.EXISTS)])],
        )
        assert referenced_paths(rule) == ["a", "b"]


class TestFailureDescriptions:
    def test_a_passing_rule_says_so(self) -> None:
        rule = Rule(name="r", checks=[check("a", CheckOperator.IS_TRUE)])
        assert describe_failures(evaluate_rule(rule, {"a": True}, now=NOW)) == "All checks passed."

    def test_a_description_names_expected_and_observed(self) -> None:
        rule = Rule(name="r", checks=[check("tls.min", CheckOperator.GREATER_OR_EQUAL, 1.2)])
        sentence = describe_failures(evaluate_rule(rule, {"tls": {"min": 1.0}}, now=NOW))
        assert "tls.min" in sentence
        assert "1.2" in sentence
        assert "1.0" in sentence

    def test_a_long_failure_list_is_truncated_with_a_count(self) -> None:
        # A control failing on 400 paths produces a reason nobody reads;
        # the full detail stays in the stored outcome.
        rule = Rule(name="r", checks=[check(f"p{i}", CheckOperator.IS_TRUE) for i in range(12)])
        sentence = describe_failures(evaluate_rule(rule, {}, now=NOW), limit=5)
        assert "and 7 more" in sentence
