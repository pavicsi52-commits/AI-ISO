"""Compiles persisted policies into runtime predicates.

Per docs/032 "POLICY ENGINE": Conditional Access, Time-Based Access,
Location-Based Access, IP-Based Access, Custom Rules. Wraps
:class:`shared_core.security.policies.PolicyEngine` (an in-memory,
deny-by-default evaluator over ``Callable[[PolicyContext], bool]``
predicates) -- this module is what turns this service's own persisted
:class:`~app.models.authorization_policy.AuthorizationPolicy`/
:class:`~app.models.policy_condition.PolicyCondition` rows into
predicates that engine can actually run, since a raw Python
``Callable`` can't be stored in a database column.
"""

from __future__ import annotations

import ipaddress
import operator as operator_module
from collections.abc import Callable
from typing import Any

from shared_core.security.policies import Policy, PolicyContext, PolicyPredicate

from app.models.authorization_policy import AuthorizationPolicy
from app.models.enums import PolicyConditionType
from app.models.policy_condition import PolicyCondition

_COMPARISON_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "equals": operator_module.eq,
    "not_equals": operator_module.ne,
    "gt": operator_module.gt,
    "gte": operator_module.ge,
    "lt": operator_module.lt,
    "lte": operator_module.le,
    "in": lambda actual, expected: actual in expected,
    "not_in": lambda actual, expected: actual not in expected,
    "contains": lambda actual, expected: expected in actual,
}


def _time_based(condition: PolicyCondition, context: PolicyContext) -> bool:
    hour = context.attributes.get("hour")
    if hour is None:
        return False
    config = condition.value or {}
    start, end = config.get("start_hour", 0), config.get("end_hour", 23)
    return bool(start <= hour <= end)


def _location_based(condition: PolicyCondition, context: PolicyContext) -> bool:
    country = context.attributes.get("country")
    allowed = (condition.value or {}).get("allowed_countries", [])
    return country in allowed


def _ip_based(condition: PolicyCondition, context: PolicyContext) -> bool:
    ip_address = context.attributes.get("ip_address")
    if not ip_address:
        return False
    allowed_cidrs = (condition.value or {}).get("allowed_cidrs", [])
    try:
        candidate = ipaddress.ip_address(ip_address)
    except ValueError:
        return False
    return any(candidate in ipaddress.ip_network(cidr, strict=False) for cidr in allowed_cidrs)


def _scope_based(attribute_name: str) -> Callable[[PolicyCondition, PolicyContext], bool]:
    def _check(condition: PolicyCondition, context: PolicyContext) -> bool:
        expected = (condition.value or {}).get(attribute_name)
        return context.attributes.get(attribute_name) == expected

    return _check


def _custom(condition: PolicyCondition, context: PolicyContext) -> bool:
    if condition.field is None:
        return False
    comparator = _COMPARISON_OPERATORS.get(condition.operator)
    if comparator is None:
        return False
    actual = context.attributes.get(condition.field)
    try:
        return bool(comparator(actual, condition.value))
    except TypeError:
        return False


_CONDITION_EVALUATORS: dict[
    PolicyConditionType, Callable[[PolicyCondition, PolicyContext], bool]
] = {
    PolicyConditionType.TIME_BASED: _time_based,
    PolicyConditionType.LOCATION_BASED: _location_based,
    PolicyConditionType.IP_BASED: _ip_based,
    PolicyConditionType.ORGANIZATION_SCOPE: _scope_based("organization_id"),
    PolicyConditionType.PROJECT_SCOPE: _scope_based("project_id"),
    PolicyConditionType.RESOURCE_SCOPE: _scope_based("resource_id"),
    PolicyConditionType.CUSTOM: _custom,
}


def compile_condition(condition: PolicyCondition) -> PolicyPredicate:
    """Build a predicate evaluating one persisted :class:`PolicyCondition`."""
    condition_type = PolicyConditionType(str(condition.condition_type))
    evaluator = _CONDITION_EVALUATORS[condition_type]
    return lambda context: evaluator(condition, context)


def compile_policy(policy: AuthorizationPolicy, conditions: list[PolicyCondition]) -> Policy:
    """Build a :class:`~shared_core.security.policies.Policy` from a persisted
    policy and its conditions ("all conditions must hold" -- AND semantics,
    matching :class:`~shared_core.security.policies.PolicyEngine.evaluate`'s
    own all-registered-policies-must-pass behavior at the next level up).
    An unconditional policy (no rows) always matches once registered.
    """
    predicates = [compile_condition(condition) for condition in conditions]

    def _predicate(context: PolicyContext) -> bool:
        return all(predicate(context) for predicate in predicates)

    return Policy(name=policy.code, predicate=_predicate)


__all__ = ["compile_condition", "compile_policy"]
