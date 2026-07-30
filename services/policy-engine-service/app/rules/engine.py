"""Boolean rule evaluation over conditions and nested rules.

A rule is a logical operator (``all``/``any``/``none``) over a list of
conditions and a list of child rules. That covers docs/050's "Boolean
Logic", "Nested Rules", and "Expressions" without an expression language
-- see :mod:`app.conditions.operators` for why not having one is the
point.

**Every evaluation produces a trace.** Not as a debugging nicety: an
authorization decision a human cannot reconstruct is one nobody can
review, appeal, or audit, and "the policy engine said no" is not an
answer anyone can act on. The trace records which conditions were
checked, what they resolved to, and which one decided the outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared_core.exceptions.validation import ValidationError

from app.attributes.resolver import EvaluationContext, is_missing, resolve, validate_path
from app.conditions.operators import (
    OPERATORS_REQUIRING_VALUE,
    ComparisonResult,
    compile_pattern,
    evaluate,
)
from app.models.enums import AttributeSource, LogicalOperator, RuleOperator

MAX_RULE_DEPTH = 10
"""How deeply rules may nest.

Bounded because rules are caller-authored and evaluated recursively; an
unbounded depth is a stack overflow that a policy author can trigger
from an API call.
"""

MAX_CONDITIONS_PER_RULE = 100
"""How many conditions one rule may hold."""


@dataclass(slots=True)
class Condition:
    """One comparison: read an attribute, apply an operator."""

    source: AttributeSource
    path: str
    operator: RuleOperator
    value: Any = None
    negate: bool = False
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "source": str(self.source),
            "path": self.path,
            "operator": str(self.operator),
            "value": self.value,
            "negate": self.negate,
            "description": self.description,
        }


@dataclass(slots=True)
class ConditionTrace:
    """What one condition did, and why."""

    source: str
    path: str
    operator: str
    expected: Any
    actual: Any
    matched: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "source": self.source,
            "path": self.path,
            "operator": self.operator,
            "expected": self.expected,
            # Rendered rather than passed through: a resolved attribute
            # can be any shape the caller sent, and a trace is stored in
            # a JSON column and shown to a reviewer.
            "actual": _renderable(self.actual),
            "matched": self.matched,
            "detail": self.detail,
        }


@dataclass(slots=True)
class RuleTrace:
    """What one rule did, including its children."""

    name: str
    logical_operator: str
    matched: bool
    conditions: list[ConditionTrace] = field(default_factory=list)
    children: list[RuleTrace] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "name": self.name,
            "logical_operator": self.logical_operator,
            "matched": self.matched,
            "conditions": [one.as_dict() for one in self.conditions],
            "children": [one.as_dict() for one in self.children],
            "detail": self.detail,
        }


@dataclass(slots=True)
class Rule:
    """A logical combination of conditions and nested rules."""

    name: str = "rule"
    logical_operator: LogicalOperator = LogicalOperator.ALL
    conditions: list[Condition] = field(default_factory=list)
    children: list[Rule] = field(default_factory=list)
    negate: bool = False
    description: str = ""

    @property
    def is_empty(self) -> bool:
        """Whether this rule tests nothing at all."""
        return not self.conditions and not self.children

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "name": self.name,
            "logical_operator": str(self.logical_operator),
            "conditions": [one.as_dict() for one in self.conditions],
            "children": [one.as_dict() for one in self.children],
            "negate": self.negate,
            "description": self.description,
        }


def _renderable(value: Any) -> Any:
    """Coerce a resolved value into something JSON can hold."""
    if is_missing(value):
        return "<missing>"
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple | set | frozenset):
        return [_renderable(one) for one in value][:20]
    if isinstance(value, dict):
        return {str(k): _renderable(v) for k, v in list(value.items())[:20]}
    return str(value)[:200]


def validate_condition(condition: Condition) -> None:
    """Check one condition is usable before it is ever stored.

    Raises:
        ValidationError: If the path is malformed, the operator needs a
            value it was not given, or a pattern will not compile.
    """
    validate_path(condition.path)
    if condition.operator in OPERATORS_REQUIRING_VALUE and condition.value is None:
        raise ValidationError(
            f"Operator {str(condition.operator)!r} needs a value to compare against."
        )
    if condition.operator in (RuleOperator.MATCHES, RuleOperator.NOT_MATCHES):
        compile_pattern(str(condition.value))


def validate_rule(rule: Rule, *, depth: int = 0) -> None:
    """Check a whole rule tree before it is stored.

    Raises:
        ValidationError: If it nests too deeply, holds too many
            conditions, tests nothing, or contains an unusable
            condition.
    """
    if depth > MAX_RULE_DEPTH:
        raise ValidationError(
            f"Rules may nest at most {MAX_RULE_DEPTH} deep; {rule.name!r} is deeper."
        )
    if len(rule.conditions) > MAX_CONDITIONS_PER_RULE:
        raise ValidationError(
            f"A rule may hold at most {MAX_CONDITIONS_PER_RULE} conditions, "
            f"{rule.name!r} holds {len(rule.conditions)}."
        )
    if rule.is_empty:
        # An empty ALL rule is vacuously true, so a policy carrying one
        # would match every request in the estate. Refused rather than
        # silently treated as false: either reading is a guess, and one
        # of them is a platform-wide grant.
        raise ValidationError(
            f"Rule {rule.name!r} has no conditions and no child rules, so it would "
            "match every request. Give it at least one condition."
        )
    for condition in rule.conditions:
        validate_condition(condition)
    for child in rule.children:
        validate_rule(child, depth=depth + 1)


def evaluate_condition(
    condition: Condition, context: EvaluationContext
) -> tuple[bool, ConditionTrace]:
    """Evaluate one condition against a context."""
    actual = resolve(context, condition.source, condition.path)
    result: ComparisonResult = evaluate(condition.operator, actual, condition.value)
    matched = result.matched != condition.negate
    return matched, ConditionTrace(
        source=str(condition.source),
        path=condition.path,
        operator=str(condition.operator),
        expected=_renderable(condition.value),
        actual=actual,
        matched=matched,
        detail=result.detail,
    )


def evaluate_rule(rule: Rule, context: EvaluationContext) -> tuple[bool, RuleTrace]:
    """Evaluate a rule tree, producing its trace.

    Every condition is evaluated even once the outcome is decided --
    deliberately, and at a cost. Short-circuiting would make the trace
    depend on evaluation order, so two logically identical policies
    would explain themselves differently and a reviewer could not tell
    why one condition went unmentioned. For an authorization decision
    somebody may have to justify later, a complete account is worth more
    than the saved comparisons.
    """
    trace = RuleTrace(name=rule.name, logical_operator=str(rule.logical_operator), matched=False)
    outcomes: list[bool] = []

    for condition in rule.conditions:
        matched, condition_trace = evaluate_condition(condition, context)
        trace.conditions.append(condition_trace)
        outcomes.append(matched)

    for child in rule.children:
        matched, child_trace = evaluate_rule(child, context)
        trace.children.append(child_trace)
        outcomes.append(matched)

    if not outcomes:
        # Only reachable for a rule that bypassed validate_rule. Treated
        # as no-match, which is the safe direction: an empty rule that
        # matched would grant whatever it was attached to.
        trace.detail = "no conditions or child rules; treated as no match"
        trace.matched = rule.negate
        return trace.matched, trace

    combined = {
        LogicalOperator.ALL: all(outcomes),
        LogicalOperator.ANY: any(outcomes),
        LogicalOperator.NONE: not any(outcomes),
    }[rule.logical_operator]

    trace.matched = combined != rule.negate
    trace.detail = (
        f"{sum(outcomes)}/{len(outcomes)} matched under "
        f"{str(rule.logical_operator)!r}" + (" (negated)" if rule.negate else "")
    )
    return trace.matched, trace


def rule_from_dict(payload: dict[str, Any], *, name: str = "rule") -> Rule:
    """Build a rule tree from stored JSON.

    Raises:
        ValidationError: If the payload names an unknown operator,
            source, or logical operator. A stored rule that cannot be
            rebuilt must fail loudly at load rather than evaluate as
            something else.
    """
    try:
        logical = LogicalOperator(payload.get("logical_operator", LogicalOperator.ALL))
    except ValueError as exc:
        raise ValidationError(f"Unknown logical operator in rule {name!r}: {exc}") from exc

    conditions: list[Condition] = []
    for raw in payload.get("conditions") or []:
        try:
            conditions.append(
                Condition(
                    source=AttributeSource(raw["source"]),
                    path=str(raw["path"]),
                    operator=RuleOperator(raw["operator"]),
                    value=raw.get("value"),
                    negate=bool(raw.get("negate", False)),
                    description=str(raw.get("description") or ""),
                )
            )
        except (KeyError, ValueError) as exc:
            raise ValidationError(f"Unusable condition in rule {name!r}: {exc}") from exc

    children = [
        rule_from_dict(raw, name=str(raw.get("name") or f"{name}.child"))
        for raw in payload.get("children") or []
    ]
    return Rule(
        name=str(payload.get("name") or name),
        logical_operator=logical,
        conditions=conditions,
        children=children,
        negate=bool(payload.get("negate", False)),
        description=str(payload.get("description") or ""),
    )


def referenced_attributes(rule: Rule) -> set[tuple[str, str]]:
    """Every ``(source, path)`` a rule tree reads.

    Used by conflict detection and by impact analysis: two policies that
    read disjoint attributes cannot contradict each other on the same
    request, which is what makes conflict detection cheap enough to run
    over a whole catalogue.
    """
    found = {(str(one.source), one.path) for one in rule.conditions}
    for child in rule.children:
        found |= referenced_attributes(child)
    return found


def count_conditions(rule: Rule) -> int:
    """How many conditions a rule tree holds in total."""
    return len(rule.conditions) + sum(count_conditions(one) for one in rule.children)


__all__ = [
    "MAX_CONDITIONS_PER_RULE",
    "MAX_RULE_DEPTH",
    "Condition",
    "ConditionTrace",
    "Rule",
    "RuleTrace",
    "count_conditions",
    "evaluate_condition",
    "evaluate_rule",
    "referenced_attributes",
    "rule_from_dict",
    "validate_condition",
    "validate_rule",
]
