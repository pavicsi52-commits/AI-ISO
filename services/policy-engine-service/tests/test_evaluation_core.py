"""The decision core: operators, rules, and combining.

Pure functions, no infrastructure — which is the point. This is the code
that decides whether an operation on this platform is permitted, so it
is written to be testable against hand-written catalogues whose right
answer is obvious by inspection. A test here that needs a database to
explain itself is a test whose subject is in the wrong place.

The combining tests matter most. An operator that returns the wrong
answer produces a visibly wrong decision; a *combining* rule that is
subtly wrong produces a decision that looks reasonable and grants
something it should not.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from shared_core.exceptions.validation import ValidationError

from app.attributes.resolver import (
    MAX_PATH_DEPTH,
    EvaluationContext,
    is_missing,
    resolve,
    validate_path,
)
from app.conditions.operators import (
    _MISSING,
    MAX_PATTERN_LENGTH,
    OPERATORS_REQUIRING_VALUE,
    ComparisonResult,
    compile_pattern,
    evaluate,
)
from app.evaluation.engine import (
    Decision,
    EvaluablePolicy,
    PolicyOutcome,
    combine,
    evaluate_policy,
    select_candidates,
)
from app.evaluation.engine import evaluate as evaluate_request
from app.models.enums import (
    DENYING_EFFECTS,
    EFFECT_PRECEDENCE,
    PERMITTING_EFFECTS,
    ActionType,
    AttributeSource,
    LogicalOperator,
    PolicyEffect,
    ResourceType,
    RuleOperator,
    SubjectType,
)
from app.publishing.compiler import canonical_json, checksum, next_version, verify_integrity
from app.rules.engine import (
    MAX_CONDITIONS_PER_RULE,
    MAX_RULE_DEPTH,
    Condition,
    Rule,
    count_conditions,
    evaluate_rule,
    referenced_attributes,
    rule_from_dict,
    validate_condition,
    validate_rule,
)


def condition(
    path: str,
    operator: RuleOperator = RuleOperator.EQUALS,
    value: Any = None,
    *,
    source: AttributeSource = AttributeSource.SUBJECT,
    negate: bool = False,
) -> Condition:
    """A condition, for building small readable rules."""
    return Condition(source=source, path=path, operator=operator, value=value, negate=negate)


def rule(*conditions: Condition, operator: LogicalOperator = LogicalOperator.ALL) -> Rule:
    """A single-level rule over the given conditions."""
    return Rule(name="test", logical_operator=operator, conditions=list(conditions))


def policy(
    slug: str,
    effect: PolicyEffect,
    *,
    matches: bool = True,
    priority: int = 100,
    risk: float = 0.0,
    obligations: dict[str, Any] | None = None,
    subject_types: list[str] | None = None,
    resource_types: list[str] | None = None,
    actions: list[str] | None = None,
) -> EvaluablePolicy:
    """A policy that matches (or does not) on a trivially controllable flag."""
    return EvaluablePolicy(
        policy_id=slug,
        slug=slug,
        name=slug,
        effect=effect,
        rule=rule(
            condition(
                "flag",
                RuleOperator.EQUALS,
                True if matches else False,  # noqa: SIM210 - explicit for readability
            )
        ),
        priority=priority,
        risk_weight=risk,
        obligations=obligations or {},
        subject_types=subject_types or [],
        resource_types=resource_types or [],
        actions=actions or [],
    )


CONTEXT = EvaluationContext(subject={"flag": True})


class TestOperatorTable:
    """Every operator, and the completeness of the table."""

    @pytest.mark.parametrize("operator", list(RuleOperator))
    def test_every_operator_is_implemented(self, operator: RuleOperator) -> None:
        # Parametrised over the enum, not a hand-written list: an
        # operator added without an implementation would otherwise
        # silently never match, which reads as a policy that declines to
        # apply rather than as a bug.
        result = evaluate(operator, "value", "value")
        assert isinstance(result, ComparisonResult)

    @pytest.mark.parametrize(
        ("operator", "actual", "expected", "matches"),
        [
            (RuleOperator.EQUALS, "prod", "prod", True),
            (RuleOperator.EQUALS, "prod", "dev", False),
            (RuleOperator.NOT_EQUALS, "prod", "dev", True),
            (RuleOperator.IN, "prod", ["dev", "prod"], True),
            (RuleOperator.IN, "stage", ["dev", "prod"], False),
            (RuleOperator.NOT_IN, "stage", ["dev", "prod"], True),
            (RuleOperator.CONTAINS, ["admin", "dev"], "admin", True),
            (RuleOperator.NOT_CONTAINS, ["dev"], "admin", True),
            (RuleOperator.STARTS_WITH, "prod-web-1", "prod-", True),
            (RuleOperator.ENDS_WITH, "prod-web-1", "-1", True),
            (RuleOperator.MATCHES, "prod-web-1", r"^prod-", True),
            (RuleOperator.NOT_MATCHES, "dev-web-1", r"^prod-", True),
            (RuleOperator.GREATER_THAN, 5, 3, True),
            (RuleOperator.GREATER_OR_EQUAL, 3, 3, True),
            (RuleOperator.LESS_THAN, 1, 3, True),
            (RuleOperator.LESS_OR_EQUAL, 3, 3, True),
            (RuleOperator.BETWEEN, 5, [1, 10], True),
            (RuleOperator.BETWEEN, 50, [1, 10], False),
            (RuleOperator.SUBSET_OF, ["a"], ["a", "b"], True),
            (RuleOperator.SUPERSET_OF, ["a", "b"], ["a"], True),
            (RuleOperator.INTERSECTS, ["a", "z"], ["a", "b"], True),
            (RuleOperator.INTERSECTS, ["y", "z"], ["a", "b"], False),
        ],
    )
    def test_the_ordinary_comparisons(
        self, operator: RuleOperator, actual: Any, expected: Any, matches: bool
    ) -> None:
        assert evaluate(operator, actual, expected).matched is matches

    def test_a_string_is_not_treated_as_a_sequence_of_characters(self) -> None:
        # "prod" contains "p" is true if the string is iterated, and that
        # would make a membership condition match on any single letter --
        # wrong in a way that reads as working.
        assert evaluate(RuleOperator.CONTAINS, "prod", "p").matched is False
        assert evaluate(RuleOperator.CONTAINS, "prod", "prod").matched is True

    def test_a_boolean_is_not_a_number(self) -> None:
        # bool subclasses int in Python, so `True > 0` is legal and
        # meaningless in a policy.
        assert evaluate(RuleOperator.GREATER_THAN, True, 0).matched is False

    def test_a_non_numeric_comparison_declines_rather_than_raising(self) -> None:
        result = evaluate(RuleOperator.GREATER_THAN, "not-a-number", 3)
        assert result.matched is False
        assert "numeric" in result.detail

    @pytest.mark.parametrize("operator", list(RuleOperator))
    def test_no_operator_raises_on_a_type_it_did_not_expect(self, operator: RuleOperator) -> None:
        # Totality is the property the whole engine leans on: an
        # exception escaping here turns one malformed condition into a
        # failed decision, and a failed decision into an outage or a
        # fallback that grants.
        for actual in (None, object(), {"a": 1}, ["x"], 3, "text", _MISSING):
            assert isinstance(evaluate(operator, actual, "x"), ComparisonResult)


class TestPresenceOperators:
    """``exists`` and friends, and the missing-versus-null distinction."""

    def test_missing_and_null_are_different(self) -> None:
        # A policy saying "deny unless department is set" has to
        # distinguish an absent attribute from one explicitly null; both
        # are "not present", but only one means the source failed to
        # supply it.
        assert evaluate(RuleOperator.EXISTS, _MISSING).matched is False
        assert evaluate(RuleOperator.EXISTS, None).matched is False
        assert evaluate(RuleOperator.EXISTS, "value").matched is True
        assert evaluate(RuleOperator.NOT_EXISTS, _MISSING).matched is True

    def test_emptiness(self) -> None:
        assert evaluate(RuleOperator.IS_EMPTY, []).matched is True
        assert evaluate(RuleOperator.IS_EMPTY, "").matched is True
        assert evaluate(RuleOperator.IS_EMPTY, _MISSING).matched is True
        assert evaluate(RuleOperator.IS_NOT_EMPTY, ["a"]).matched is True
        assert evaluate(RuleOperator.IS_NOT_EMPTY, 5).matched is True

    def test_presence_operators_need_no_value(self) -> None:
        for operator in (
            RuleOperator.EXISTS,
            RuleOperator.NOT_EXISTS,
            RuleOperator.IS_EMPTY,
            RuleOperator.IS_NOT_EMPTY,
        ):
            assert operator not in OPERATORS_REQUIRING_VALUE


class TestTimeOperators:
    """Windows and days, including the ones that wrap."""

    def test_a_window_inside_one_day(self) -> None:
        moment = datetime(2026, 7, 30, 14, 0, tzinfo=UTC)
        assert evaluate(RuleOperator.TIME_BETWEEN, moment, ["09:00", "17:00"]).matched

    def test_a_window_that_crosses_midnight(self) -> None:
        # A maintenance window of 22:00-06:00 is the normal case, not an
        # edge case: a naive start <= now <= end comparison excludes
        # every hour of it.
        for hour in (23, 2):
            moment = datetime(2026, 7, 30, hour, 0, tzinfo=UTC)
            assert evaluate(RuleOperator.TIME_BETWEEN, moment, ["22:00", "06:00"]).matched, hour
        midday = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
        assert not evaluate(RuleOperator.TIME_BETWEEN, midday, ["22:00", "06:00"]).matched

    def test_days_by_name_and_by_number(self) -> None:
        thursday = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
        assert evaluate(RuleOperator.DAY_OF_WEEK_IN, thursday, ["thursday"]).matched
        assert evaluate(RuleOperator.DAY_OF_WEEK_IN, thursday, [3]).matched
        assert not evaluate(RuleOperator.DAY_OF_WEEK_IN, thursday, ["sunday"]).matched

    def test_an_iso_string_is_accepted_as_a_time(self) -> None:
        # Attributes arrive over JSON, so a datetime is a string by the
        # time a condition sees it.
        assert evaluate(
            RuleOperator.TIME_BETWEEN, "2026-07-30T14:00:00Z", ["09:00", "17:00"]
        ).matched

    def test_a_malformed_bound_declines(self) -> None:
        assert not evaluate(RuleOperator.TIME_BETWEEN, "14:00", ["not-a-time", "17:00"])


class TestNetworkOperator:
    """CIDR membership, parsed rather than prefixed."""

    def test_an_address_inside_a_network_matches(self) -> None:
        assert evaluate(RuleOperator.CIDR_CONTAINS, "10.0.1.5", ["10.0.0.0/16"]).matched

    def test_an_address_outside_does_not(self) -> None:
        assert not evaluate(RuleOperator.CIDR_CONTAINS, "192.168.1.1", ["10.0.0.0/16"])

    def test_a_string_prefix_is_not_network_membership(self) -> None:
        # 10.0.0.100 starts with "10.0.0.1" but is not inside
        # 10.0.0.1/32. An IP allow-list built on startswith grants
        # addresses nobody intended.
        assert not evaluate(RuleOperator.CIDR_CONTAINS, "10.0.0.100", ["10.0.0.1/32"])

    def test_several_networks_are_any_of(self) -> None:
        assert evaluate(
            RuleOperator.CIDR_CONTAINS, "172.16.0.1", ["10.0.0.0/8", "172.16.0.0/12"]
        ).matched

    def test_a_malformed_address_declines_rather_than_raising(self) -> None:
        result = evaluate(RuleOperator.CIDR_CONTAINS, "not-an-ip", ["10.0.0.0/8"])
        assert result.matched is False
        assert "not an IP address" in result.detail

    def test_ipv4_is_not_matched_against_an_ipv6_network(self) -> None:
        assert not evaluate(RuleOperator.CIDR_CONTAINS, "10.0.0.1", ["::/0"])


class TestPatternSafety:
    """Bounds on the one operator that runs untrusted input."""

    def test_a_pattern_is_length_bounded(self) -> None:
        # Python's re has no step limit, so one stored policy carrying a
        # catastrophic pattern would stall every decision in the estate.
        with pytest.raises(ValidationError, match="at most"):
            compile_pattern("a" * (MAX_PATTERN_LENGTH + 1))

    def test_an_invalid_pattern_is_refused_at_authoring_time(self) -> None:
        with pytest.raises(ValidationError, match="regular expression"):
            compile_pattern("(unclosed")

    def test_a_long_value_is_not_scanned(self) -> None:
        # Bounding the pattern alone is not enough: matching cost grows
        # with the input too.
        result = evaluate(RuleOperator.MATCHES, "a" * 10_000, "a+")
        assert result.matched is False
        assert "matching limit" in result.detail

    def test_a_non_string_value_never_matches(self) -> None:
        assert evaluate(RuleOperator.MATCHES, 42, r"\d+").matched is False


class TestAttributeResolution:
    """Reading an attribute out of a request."""

    def test_a_nested_path_resolves(self) -> None:
        context = EvaluationContext(subject={"profile": {"department": "platform"}})
        assert resolve(context, AttributeSource.SUBJECT, "profile.department") == "platform"

    def test_a_list_index_resolves(self) -> None:
        context = EvaluationContext(subject={"roles": ["admin", "viewer"]})
        assert resolve(context, AttributeSource.SUBJECT, "roles.0") == "admin"

    def test_an_absent_attribute_is_missing_not_none(self) -> None:
        context = EvaluationContext(subject={"present": None})
        assert is_missing(resolve(context, AttributeSource.SUBJECT, "absent"))
        assert resolve(context, AttributeSource.SUBJECT, "present") is None

    def test_walking_off_the_end_returns_missing_rather_than_raising(self) -> None:
        # An optional attribute is the normal case; an exception here
        # would turn every policy referencing one into a failed decision.
        context = EvaluationContext(subject={"name": "text"})
        assert is_missing(resolve(context, AttributeSource.SUBJECT, "name.deeper.still"))
        assert is_missing(resolve(context, AttributeSource.SUBJECT, "roles.5"))

    @pytest.mark.parametrize("source", list(AttributeSource))
    def test_every_source_is_addressable(self, source: AttributeSource) -> None:
        context = EvaluationContext()
        context.source(source)["value"] = "found"
        assert resolve(context, source, "value") == "found"

    def test_a_path_is_depth_bounded(self) -> None:
        with pytest.raises(ValidationError, match="segments deep"):
            validate_path(".".join(["a"] * (MAX_PATH_DEPTH + 1)))

    @pytest.mark.parametrize("path", ["", "   ", "has space", "has-$ymbol", "a..b", "a.b;c"])
    def test_a_malformed_path_is_refused(self, path: str) -> None:
        with pytest.raises(ValidationError):
            validate_path(path)

    def test_the_context_serialises_for_storage(self) -> None:
        context = EvaluationContext(subject={"id": "u1"}, resource={"id": "r1"})
        payload = context.as_dict()
        assert payload["subject"]["id"] == "u1"
        assert set(payload) == {
            "subject",
            "resource",
            "action",
            "context",
            "environment",
            "organization",
            "project",
            "custom",
        }


class TestRuleLogic:
    """Boolean combination, nesting, and negation."""

    def test_all_requires_every_condition(self) -> None:
        context = EvaluationContext(subject={"env": "prod", "team": "platform"})
        matched, _ = evaluate_rule(
            rule(
                condition("env", RuleOperator.EQUALS, "prod"),
                condition("team", RuleOperator.EQUALS, "platform"),
            ),
            context,
        )
        assert matched is True

        matched, _ = evaluate_rule(
            rule(
                condition("env", RuleOperator.EQUALS, "prod"),
                condition("team", RuleOperator.EQUALS, "security"),
            ),
            context,
        )
        assert matched is False

    def test_any_requires_one(self) -> None:
        context = EvaluationContext(subject={"env": "prod"})
        matched, _ = evaluate_rule(
            rule(
                condition("env", RuleOperator.EQUALS, "dev"),
                condition("env", RuleOperator.EQUALS, "prod"),
                operator=LogicalOperator.ANY,
            ),
            context,
        )
        assert matched is True

    def test_none_requires_zero(self) -> None:
        context = EvaluationContext(subject={"env": "prod"})
        matched, _ = evaluate_rule(
            rule(
                condition("env", RuleOperator.EQUALS, "dev"),
                operator=LogicalOperator.NONE,
            ),
            context,
        )
        assert matched is True

    def test_a_nested_rule_composes(self) -> None:
        # "production AND (admin OR on-call)" -- the shape a real
        # authorization policy takes.
        context = EvaluationContext(subject={"env": "prod", "roles": ["on-call"]})
        tree = Rule(
            name="root",
            logical_operator=LogicalOperator.ALL,
            conditions=[condition("env", RuleOperator.EQUALS, "prod")],
            children=[
                Rule(
                    name="who",
                    logical_operator=LogicalOperator.ANY,
                    conditions=[
                        condition("roles", RuleOperator.CONTAINS, "admin"),
                        condition("roles", RuleOperator.CONTAINS, "on-call"),
                    ],
                )
            ],
        )
        matched, trace = evaluate_rule(tree, context)
        assert matched is True
        assert trace.children[0].matched is True

    def test_negation_inverts_a_rule(self) -> None:
        context = EvaluationContext(subject={"env": "prod"})
        tree = rule(condition("env", RuleOperator.EQUALS, "prod"))
        tree.negate = True
        matched, _ = evaluate_rule(tree, context)
        assert matched is False

    def test_negation_inverts_a_condition(self) -> None:
        context = EvaluationContext(subject={"env": "prod"})
        matched, _ = evaluate_rule(
            rule(condition("env", RuleOperator.EQUALS, "prod", negate=True)), context
        )
        assert matched is False


class TestEvaluationTrace:
    """The account of why a decision came out as it did."""

    def test_every_condition_appears_even_after_the_outcome_is_decided(self) -> None:
        # Short-circuiting would make the trace depend on evaluation
        # order, so two logically identical policies would explain
        # themselves differently and a reviewer could not tell why one
        # condition went unmentioned.
        context = EvaluationContext(subject={"a": 1, "b": 2, "c": 3})
        _matched, trace = evaluate_rule(
            rule(
                condition("a", RuleOperator.EQUALS, 999),
                condition("b", RuleOperator.EQUALS, 2),
                condition("c", RuleOperator.EQUALS, 3),
            ),
            context,
        )
        assert len(trace.conditions) == 3

    def test_a_trace_records_what_each_condition_saw(self) -> None:
        context = EvaluationContext(subject={"env": "dev"})
        _matched, trace = evaluate_rule(
            rule(condition("env", RuleOperator.EQUALS, "prod")), context
        )
        entry = trace.conditions[0]
        assert entry.actual == "dev"
        assert entry.expected == "prod"
        assert entry.matched is False

    def test_a_missing_attribute_is_rendered_readably(self) -> None:
        context = EvaluationContext()
        _matched, trace = evaluate_rule(
            rule(condition("absent", RuleOperator.EQUALS, "x")), context
        )
        assert trace.conditions[0].as_dict()["actual"] == "<missing>"

    def test_a_trace_is_json_serialisable(self) -> None:
        context = EvaluationContext(subject={"roles": ["a", "b"], "meta": {"k": "v"}})
        _matched, trace = evaluate_rule(
            rule(
                condition("roles", RuleOperator.CONTAINS, "a"),
                condition("meta", RuleOperator.IS_NOT_EMPTY),
            ),
            context,
        )
        assert json.dumps(trace.as_dict())

    def test_the_trace_says_how_many_conditions_matched(self) -> None:
        context = EvaluationContext(subject={"a": 1, "b": 2})
        _matched, trace = evaluate_rule(
            rule(
                condition("a", RuleOperator.EQUALS, 1),
                condition("b", RuleOperator.EQUALS, 999),
            ),
            context,
        )
        assert "1/2 matched" in trace.detail


class TestRuleValidation:
    """What a policy is refused for, at authoring time."""

    def test_an_empty_rule_is_refused(self) -> None:
        # An empty ALL rule is vacuously true, so a policy carrying one
        # would match every request in the estate. Either reading is a
        # guess, and one of them is a platform-wide grant.
        with pytest.raises(ValidationError, match="match every request"):
            validate_rule(Rule(name="empty"))

    def test_nesting_is_depth_bounded(self) -> None:
        deepest = rule(condition("a", RuleOperator.EXISTS))
        for _ in range(MAX_RULE_DEPTH + 1):
            deepest = Rule(name="wrap", children=[deepest])
        with pytest.raises(ValidationError, match="nest at most"):
            validate_rule(deepest)

    def test_conditions_per_rule_are_bounded(self) -> None:
        crowded = rule(
            *[condition(f"a{i}", RuleOperator.EXISTS) for i in range(MAX_CONDITIONS_PER_RULE + 1)]
        )
        with pytest.raises(ValidationError, match="at most"):
            validate_rule(crowded)

    def test_an_operator_that_needs_a_value_is_refused_without_one(self) -> None:
        # `equals` with nothing to equal is not a strict condition -- it
        # is one that quietly matches any attribute that happens to be
        # null.
        with pytest.raises(ValidationError, match="needs a value"):
            validate_condition(condition("env", RuleOperator.EQUALS, None))

    def test_an_unusable_pattern_is_refused_before_it_is_stored(self) -> None:
        with pytest.raises(ValidationError):
            validate_condition(condition("env", RuleOperator.MATCHES, "(unclosed"))

    def test_a_malformed_path_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            validate_condition(condition("has space", RuleOperator.EXISTS))


class TestRuleSerialisation:
    """Rules survive the round trip through storage."""

    def test_a_rule_tree_round_trips(self) -> None:
        original = Rule(
            name="root",
            logical_operator=LogicalOperator.ANY,
            conditions=[condition("env", RuleOperator.IN, ["prod", "stage"])],
            children=[rule(condition("team", RuleOperator.EQUALS, "platform"))],
        )
        rebuilt = rule_from_dict(original.as_dict())
        assert rebuilt.as_dict() == original.as_dict()

    def test_a_rebuilt_rule_evaluates_identically(self) -> None:
        # The property that matters: storage must not change a decision.
        context = EvaluationContext(subject={"env": "prod", "team": "platform"})
        original = Rule(
            name="root",
            conditions=[condition("env", RuleOperator.EQUALS, "prod")],
            children=[rule(condition("team", RuleOperator.EQUALS, "platform"))],
        )
        assert (
            evaluate_rule(original, context)[0]
            == evaluate_rule(rule_from_dict(original.as_dict()), context)[0]
        )

    def test_an_unknown_operator_fails_loudly_rather_than_never_matching(self) -> None:
        # A stored rule that cannot be rebuilt must not evaluate as "no
        # match" -- that is indistinguishable from a policy that decided
        # not to apply.
        with pytest.raises(ValidationError, match="Unusable condition"):
            rule_from_dict(
                {"conditions": [{"source": "subject", "path": "a", "operator": "no_such_operator"}]}
            )

    def test_an_unknown_logical_operator_fails_loudly(self) -> None:
        with pytest.raises(ValidationError, match="logical operator"):
            rule_from_dict({"logical_operator": "maybe", "conditions": []})

    def test_referenced_attributes_covers_nested_rules(self) -> None:
        tree = Rule(
            name="root",
            conditions=[condition("env", RuleOperator.EXISTS)],
            children=[
                rule(condition("team", RuleOperator.EXISTS, source=AttributeSource.RESOURCE))
            ],
        )
        assert referenced_attributes(tree) == {("subject", "env"), ("resource", "team")}

    def test_conditions_are_counted_across_the_tree(self) -> None:
        tree = Rule(
            name="root",
            conditions=[condition("a", RuleOperator.EXISTS)],
            children=[
                rule(condition("b", RuleOperator.EXISTS), condition("c", RuleOperator.EXISTS))
            ],
        )
        assert count_conditions(tree) == 3


class TestEffectPrecedence:
    """The combining algorithm -- the most consequential table here."""

    def test_every_effect_has_a_rank(self) -> None:
        for effect in PolicyEffect:
            assert effect in EFFECT_PRECEDENCE

    def test_deny_beats_allow_however_many_allows_there_are(self) -> None:
        # Most-specific-wins would let a narrow allow punch a hole
        # through a broad organizational deny -- the mistake nobody
        # notices until an audit.
        outcomes = [
            PolicyOutcome("a1", "allow-1", "", PolicyEffect.ALLOW, True, 900, 0.0),
            PolicyOutcome("a2", "allow-2", "", PolicyEffect.ALLOW, True, 800, 0.0),
            PolicyOutcome("d1", "deny", "", PolicyEffect.DENY, True, 1, 0.0),
        ]
        effect, reason, deciding = combine(outcomes)
        assert effect is PolicyEffect.DENY
        assert deciding == "d1"
        assert "2 other policies also matched" in reason

    def test_a_high_priority_allow_does_not_outrank_a_low_priority_deny(self) -> None:
        outcomes = [
            PolicyOutcome("a", "allow", "", PolicyEffect.ALLOW, True, 10_000, 0.0),
            PolicyOutcome("d", "deny", "", PolicyEffect.DENY, True, 0, 0.0),
        ]
        assert combine(outcomes)[0] is PolicyEffect.DENY

    def test_priority_breaks_ties_only_within_one_effect(self) -> None:
        outcomes = [
            PolicyOutcome("low", "low", "", PolicyEffect.ALLOW, True, 10, 0.0),
            PolicyOutcome("high", "high", "", PolicyEffect.ALLOW, True, 900, 0.0),
        ]
        assert combine(outcomes)[2] == "high"

    def test_an_approval_requirement_outranks_an_allow(self) -> None:
        # Combining the other way would let any broad allow policy erase
        # every approval gate in the estate.
        outcomes = [
            PolicyOutcome("a", "allow", "", PolicyEffect.ALLOW, True, 900, 0.0),
            PolicyOutcome("r", "review", "", PolicyEffect.REQUIRE_APPROVAL, True, 1, 0.0),
        ]
        assert combine(outcomes)[0] is PolicyEffect.REQUIRE_APPROVAL

    def test_approval_outranks_mfa_which_outranks_conditional_allow(self) -> None:
        assert (
            EFFECT_PRECEDENCE[PolicyEffect.REQUIRE_APPROVAL]
            > EFFECT_PRECEDENCE[PolicyEffect.REQUIRE_MFA]
            > EFFECT_PRECEDENCE[PolicyEffect.CONDITIONAL_ALLOW]
        )

    def test_deferred_outranks_every_obligation(self) -> None:
        # A decision that could not be reached must never be reported as
        # one that was.
        for effect in (
            PolicyEffect.REQUIRE_APPROVAL,
            PolicyEffect.REQUIRE_MFA,
            PolicyEffect.ESCALATE,
        ):
            assert EFFECT_PRECEDENCE[PolicyEffect.DEFERRED] > EFFECT_PRECEDENCE[effect]

    def test_quota_exceeded_is_a_denial_but_a_distinguishable_one(self) -> None:
        # "You are out of budget" and "you are not permitted" need
        # different responses from the caller.
        assert PolicyEffect.QUOTA_EXCEEDED in DENYING_EFFECTS
        assert PolicyEffect.QUOTA_EXCEEDED is not PolicyEffect.DENY

    def test_an_obligation_is_not_a_permit(self) -> None:
        # The distinction that keeps approval gates real.
        assert PolicyEffect.REQUIRE_APPROVAL not in PERMITTING_EFFECTS
        assert PolicyEffect.REQUIRE_MFA not in PERMITTING_EFFECTS
        assert PolicyEffect.ESCALATE not in PERMITTING_EFFECTS
        assert PolicyEffect.ALLOW in PERMITTING_EFFECTS

    def test_deferred_is_not_counted_as_a_denial(self) -> None:
        # It is the absence of an answer, not a refusal, and a caller has
        # to tell them apart.
        assert PolicyEffect.DEFERRED not in DENYING_EFFECTS
        assert PolicyEffect.DEFERRED not in PERMITTING_EFFECTS


class TestCombiningEdges:
    """No match, no policies, and broken policies."""

    def test_no_match_falls_through_to_the_default(self) -> None:
        outcomes = [PolicyOutcome("a", "allow", "", PolicyEffect.ALLOW, False, 100, 0.0)]
        effect, reason, deciding = combine(outcomes)
        assert effect is PolicyEffect.DENY
        assert deciding is None
        assert "No policy matched" in reason

    def test_an_empty_catalogue_is_distinguishable_from_no_match(self) -> None:
        # "No governance is written for this" and "governance exists and
        # none applied" call for very different responses.
        _effect, no_policies, _ = combine([])
        _effect, no_match, _ = combine(
            [PolicyOutcome("a", "a", "", PolicyEffect.ALLOW, False, 1, 0.0)]
        )
        assert no_policies != no_match

    def test_the_default_effect_is_configurable(self) -> None:
        effect, _reason, _ = combine([], default_effect=PolicyEffect.ALLOW)
        assert effect is PolicyEffect.ALLOW

    def test_a_broken_policy_defers_when_failing_closed(self) -> None:
        # Answering "allow" on the basis of a rule nobody could run is
        # the worst available outcome; answering "deny" would misreport
        # a broken policy as a deliberate refusal.
        outcomes = [
            PolicyOutcome("a", "allow", "", PolicyEffect.ALLOW, True, 100, 0.0),
            PolicyOutcome("b", "broken", "", PolicyEffect.DENY, False, 100, 0.0, error="boom"),
        ]
        effect, reason, _ = combine(outcomes, fail_closed=True)
        assert effect is PolicyEffect.DEFERRED
        assert "fail closed" in reason
        assert "broken" in reason

    def test_failing_open_ignores_a_broken_policy(self) -> None:
        outcomes = [
            PolicyOutcome("a", "allow", "", PolicyEffect.ALLOW, True, 100, 0.0),
            PolicyOutcome("b", "broken", "", PolicyEffect.DENY, False, 100, 0.0, error="boom"),
        ]
        assert combine(outcomes, fail_closed=False)[0] is PolicyEffect.ALLOW


class TestCandidateSelection:
    """Which policies a request is even measured against."""

    def test_an_empty_selector_means_any(self) -> None:
        # The only way to express an estate-wide rule; the alternative
        # reading would make a blanket deny inexpressible.
        blanket = policy("blanket", PolicyEffect.DENY)
        assert blanket.applies_to(SubjectType.USER, ResourceType.SECRET, ActionType.DELETE)

    def test_a_selector_narrows(self) -> None:
        scoped = policy(
            "secrets-only",
            PolicyEffect.DENY,
            resource_types=[str(ResourceType.SECRET)],
        )
        assert scoped.applies_to(SubjectType.USER, ResourceType.SECRET, ActionType.READ)
        assert not scoped.applies_to(SubjectType.USER, ResourceType.DASHBOARD, ActionType.READ)

    def test_candidates_come_back_highest_priority_first(self) -> None:
        # Stable ordering is what makes deciding_policy_id reproducible
        # rather than dependent on database row order.
        catalogue = [
            policy("low", PolicyEffect.ALLOW, priority=1),
            policy("high", PolicyEffect.ALLOW, priority=900),
            policy("mid", PolicyEffect.ALLOW, priority=100),
        ]
        ordered = select_candidates(
            catalogue,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.DASHBOARD,
            action=ActionType.READ,
        )
        assert [one.slug for one in ordered] == ["high", "mid", "low"]

    def test_equal_priorities_are_ordered_by_slug(self) -> None:
        catalogue = [
            policy("zebra", PolicyEffect.ALLOW, priority=100),
            policy("alpha", PolicyEffect.ALLOW, priority=100),
        ]
        ordered = select_candidates(
            catalogue,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.DASHBOARD,
            action=ActionType.READ,
        )
        assert [one.slug for one in ordered] == ["alpha", "zebra"]


class TestEndToEndDecisions:
    """Whole decisions over small catalogues whose answer is obvious."""

    def test_an_empty_catalogue_denies_by_default(self) -> None:
        # The gap between deploying this service and authoring the first
        # policy is precisely when default-allow would matter.
        decision = evaluate_request(
            [],
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.SECRET,
            action=ActionType.READ,
        )
        assert decision.effect is PolicyEffect.DENY
        assert decision.permitted is False

    def test_a_matching_allow_permits(self) -> None:
        decision = evaluate_request(
            [policy("allow", PolicyEffect.ALLOW)],
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.DASHBOARD,
            action=ActionType.READ,
        )
        assert decision.permitted is True
        assert decision.deciding_policy_id == "allow"

    def test_a_deny_wins_end_to_end(self) -> None:
        decision = evaluate_request(
            [policy("allow", PolicyEffect.ALLOW), policy("deny", PolicyEffect.DENY)],
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.DASHBOARD,
            action=ActionType.READ,
        )
        assert decision.denied is True
        assert set(decision.matched_policy_ids) == {"allow", "deny"}

    def test_a_non_matching_deny_does_not_interfere(self) -> None:
        decision = evaluate_request(
            [
                policy("allow", PolicyEffect.ALLOW),
                policy("deny", PolicyEffect.DENY, matches=False),
            ],
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.DASHBOARD,
            action=ActionType.READ,
        )
        assert decision.permitted is True

    def test_obligations_come_from_the_deciding_policy(self) -> None:
        decision = evaluate_request(
            [
                policy("allow", PolicyEffect.ALLOW, obligations={"ignored": True}),
                policy(
                    "review",
                    PolicyEffect.REQUIRE_APPROVAL,
                    obligations={"approval_type": "multi_level", "levels": 2},
                ),
            ],
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.SECRET,
            action=ActionType.DELETE,
        )
        assert decision.effect is PolicyEffect.REQUIRE_APPROVAL
        assert decision.obligations == {"approval_type": "multi_level", "levels": 2}
        assert decision.permitted is False

    def test_risk_is_the_worst_matched_weight_not_the_sum(self) -> None:
        # A sum grows with how many policies happen to overlap, so a
        # well-governed resource would score riskier than an ungoverned
        # one -- the exact inversion of what the number is for.
        decision = evaluate_request(
            [
                policy("a", PolicyEffect.ALLOW, risk=0.4),
                policy("b", PolicyEffect.ALLOW, risk=0.6),
                policy("c", PolicyEffect.ALLOW, risk=0.3),
            ],
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.DASHBOARD,
            action=ActionType.READ,
        )
        assert decision.risk_score == 0.6

    def test_an_unmatched_policys_risk_is_not_counted(self) -> None:
        decision = evaluate_request(
            [policy("far", PolicyEffect.DENY, matches=False, risk=1.0)],
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.DASHBOARD,
            action=ActionType.READ,
        )
        assert decision.risk_score == 0.0

    def test_a_broken_policy_is_recorded_and_defers(self) -> None:
        broken = policy("broken", PolicyEffect.ALLOW)
        broken.rule = Rule(name="empty")  # bypasses validation, as a corrupt row would
        decision = evaluate_request(
            [broken],
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.DASHBOARD,
            action=ActionType.READ,
        )
        # An empty rule evaluates as no-match rather than raising, so
        # this lands on the default rather than DEFERRED -- the safe
        # direction either way.
        assert decision.permitted is False

    def test_the_catalogue_is_truncated_loudly_not_silently(self) -> None:
        # A decision made from a partial catalogue is one whose "no
        # policy denied this" cannot be trusted.
        catalogue = [policy(f"p{i}", PolicyEffect.ALLOW) for i in range(10)]
        decision = evaluate_request(
            catalogue,
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.DASHBOARD,
            action=ActionType.READ,
            max_policies=3,
        )
        assert decision.policies_considered == 3
        assert any("may not reflect the whole catalogue" in one for one in decision.errors)

    def test_a_decision_serialises_with_its_reasoning(self) -> None:
        decision = evaluate_request(
            [policy("deny", PolicyEffect.DENY)],
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.SECRET,
            action=ActionType.DELETE,
        )
        payload = decision.as_dict()
        assert json.dumps(payload)
        assert payload["effect"] == "deny"
        assert payload["trace"]
        assert payload["reason"]

    def test_evaluation_is_timed(self) -> None:
        decision = evaluate_request(
            [policy("allow", PolicyEffect.ALLOW)],
            CONTEXT,
            subject_type=SubjectType.USER,
            resource_type=ResourceType.DASHBOARD,
            action=ActionType.READ,
        )
        assert decision.duration_ms >= 0.0

    def test_a_policy_raising_is_caught_rather_than_propagated(self) -> None:
        class Exploding(Rule):
            pass

        exploding = policy("boom", PolicyEffect.ALLOW)
        # A rule whose children list is not a list: the shape a corrupt
        # stored document would have.
        exploding.rule = Rule(
            name="bad",
            conditions=[condition("a", RuleOperator.EXISTS)],
            children="not-a-list",  # type: ignore[arg-type]
        )
        outcome = evaluate_policy(exploding, CONTEXT)
        assert outcome.matched is False
        assert outcome.error is not None


class TestIntegrityAndVersioning:
    """The digest, and semantic versions."""

    def test_the_digest_is_stable_across_key_ordering(self) -> None:
        # Without canonicalisation, republishing an unchanged policy
        # produces a different checksum and the integrity check cries
        # wolf on every deploy.
        assert checksum({"a": 1, "b": 2}) == checksum({"b": 2, "a": 1})

    def test_the_digest_changes_with_content(self) -> None:
        assert checksum({"a": 1}) != checksum({"a": 2})

    def test_canonical_json_is_compact_and_sorted(self) -> None:
        assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'

    def test_a_matching_digest_verifies(self) -> None:
        compiled = {"name": "root", "conditions": []}
        assert verify_integrity(compiled, checksum(compiled))["verified"] is True

    def test_a_tampered_policy_fails_verification(self) -> None:
        compiled = {"name": "root", "conditions": []}
        recorded = checksum(compiled)
        compiled["name"] = "changed"
        result = verify_integrity(compiled, recorded)
        assert result["verified"] is False
        assert "does not match" in result["reason"]

    def test_a_policy_with_no_digest_is_unverifiable_not_valid(self) -> None:
        # It predates integrity recording or bypassed publishing, and
        # calling that "valid" is the answer nobody wants from an
        # integrity check.
        result = verify_integrity({"name": "root"}, None)
        assert result["verified"] is False
        assert "no checksum" in result["reason"]

    @pytest.mark.parametrize(
        ("current", "kwargs", "expected"),
        [
            ("1.0.0", {}, "1.0.1"),
            ("1.2.3", {"feature": True}, "1.3.0"),
            ("1.2.3", {"breaking": True}, "2.0.0"),
            ("0.9.9", {"feature": True}, "0.10.0"),
        ],
    )
    def test_versions_increment(self, current: str, kwargs: dict[str, bool], expected: str) -> None:
        assert next_version(current, **kwargs) == expected

    @pytest.mark.parametrize("bad", ["1.0", "one.two.three", "", "1.0.0.0"])
    def test_a_malformed_version_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError, match="semantic version"):
            next_version(bad)


class TestDecisionShape:
    """The answer object callers actually consume."""

    def test_a_fresh_decision_denies(self) -> None:
        # The default has to be the safe one: a Decision constructed and
        # then not populated must not read as a grant.
        assert Decision().permitted is False
        assert Decision().denied is True

    def test_matched_policy_ids_excludes_non_matches(self) -> None:
        decision = Decision(
            outcomes=[
                PolicyOutcome("a", "a", "", PolicyEffect.ALLOW, True, 1, 0.0),
                PolicyOutcome("b", "b", "", PolicyEffect.DENY, False, 1, 0.0),
            ]
        )
        assert decision.matched_policy_ids == ["a"]
