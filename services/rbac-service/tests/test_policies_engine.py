"""Tests for :mod:`app.policies.engine`'s condition compilation."""

from __future__ import annotations

import uuid

from shared_core.security.policies import PolicyContext

from app.models.authorization_policy import AuthorizationPolicy
from app.models.enums import PolicyConditionType, PolicyEffect
from app.models.policy_condition import PolicyCondition
from app.policies.engine import compile_condition, compile_policy


def _condition(condition_type: PolicyConditionType, **kwargs: object) -> PolicyCondition:
    return PolicyCondition(
        id=uuid.uuid4(),
        policy_id=uuid.uuid4(),
        condition_type=condition_type,
        field=kwargs.get("field"),
        operator=kwargs.get("operator", "equals"),
        value=kwargs.get("value"),
    )


def test_time_based_condition_within_window() -> None:
    condition = _condition(PolicyConditionType.TIME_BASED, value={"start_hour": 9, "end_hour": 17})
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"hour": 12})) is True
    assert predicate(PolicyContext(action="read", attributes={"hour": 20})) is False


def test_time_based_condition_missing_hour_denies() -> None:
    condition = _condition(PolicyConditionType.TIME_BASED, value={"start_hour": 0, "end_hour": 23})
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={})) is False


def test_location_based_condition() -> None:
    condition = _condition(
        PolicyConditionType.LOCATION_BASED, value={"allowed_countries": ["US", "CA"]}
    )
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"country": "US"})) is True
    assert predicate(PolicyContext(action="read", attributes={"country": "FR"})) is False


def test_ip_based_condition_matches_cidr() -> None:
    condition = _condition(PolicyConditionType.IP_BASED, value={"allowed_cidrs": ["10.0.0.0/8"]})
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"ip_address": "10.1.2.3"})) is True
    assert predicate(PolicyContext(action="read", attributes={"ip_address": "8.8.8.8"})) is False


def test_ip_based_condition_rejects_malformed_ip() -> None:
    condition = _condition(PolicyConditionType.IP_BASED, value={"allowed_cidrs": ["10.0.0.0/8"]})
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"ip_address": "not-an-ip"})) is False


def test_ip_based_condition_missing_ip_denies() -> None:
    condition = _condition(PolicyConditionType.IP_BASED, value={"allowed_cidrs": ["10.0.0.0/8"]})
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={})) is False


def test_organization_scope_condition() -> None:
    org_id = str(uuid.uuid4())
    condition = _condition(
        PolicyConditionType.ORGANIZATION_SCOPE, value={"organization_id": org_id}
    )
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"organization_id": org_id})) is True
    assert predicate(PolicyContext(action="read", attributes={"organization_id": "other"})) is False


def test_project_scope_condition() -> None:
    project_id = str(uuid.uuid4())
    condition = _condition(PolicyConditionType.PROJECT_SCOPE, value={"project_id": project_id})
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"project_id": project_id})) is True


def test_resource_scope_condition() -> None:
    resource_id = str(uuid.uuid4())
    condition = _condition(PolicyConditionType.RESOURCE_SCOPE, value={"resource_id": resource_id})
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"resource_id": resource_id})) is True


def test_custom_condition_equals() -> None:
    condition = _condition(
        PolicyConditionType.CUSTOM, field="department", operator="equals", value="engineering"
    )
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"department": "engineering"})) is True
    assert predicate(PolicyContext(action="read", attributes={"department": "sales"})) is False


def test_custom_condition_in_operator() -> None:
    condition = _condition(
        PolicyConditionType.CUSTOM, field="tier", operator="in", value=["gold", "platinum"]
    )
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"tier": "gold"})) is True
    assert predicate(PolicyContext(action="read", attributes={"tier": "bronze"})) is False


def test_custom_condition_gt_operator() -> None:
    condition = _condition(PolicyConditionType.CUSTOM, field="age", operator="gt", value=18)
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"age": 21})) is True
    assert predicate(PolicyContext(action="read", attributes={"age": 10})) is False


def test_custom_condition_unknown_operator_denies() -> None:
    condition = _condition(PolicyConditionType.CUSTOM, field="age", operator="unknown", value=18)
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"age": 21})) is False


def test_custom_condition_missing_field_denies() -> None:
    condition = _condition(PolicyConditionType.CUSTOM, field=None, operator="equals", value="x")
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={})) is False


def test_custom_condition_type_mismatch_denies_rather_than_raises() -> None:
    condition = _condition(
        PolicyConditionType.CUSTOM, field="age", operator="gt", value="not-a-number"
    )
    predicate = compile_condition(condition)

    assert predicate(PolicyContext(action="read", attributes={"age": 21})) is False


def test_compile_policy_requires_all_conditions() -> None:
    policy = AuthorizationPolicy(
        id=uuid.uuid4(), name="Test", code="test_policy", effect=PolicyEffect.ALLOW
    )
    conditions = [
        _condition(PolicyConditionType.CUSTOM, field="a", operator="equals", value=1),
        _condition(PolicyConditionType.CUSTOM, field="b", operator="equals", value=2),
    ]
    compiled = compile_policy(policy, conditions)

    assert compiled.name == "test_policy"
    assert compiled.predicate(PolicyContext(action="read", attributes={"a": 1, "b": 2})) is True
    assert compiled.predicate(PolicyContext(action="read", attributes={"a": 1, "b": 99})) is False


def test_compile_policy_with_no_conditions_always_matches() -> None:
    policy = AuthorizationPolicy(
        id=uuid.uuid4(), name="Test", code="unconditional", effect=PolicyEffect.ALLOW
    )

    compiled = compile_policy(policy, [])

    assert compiled.predicate(PolicyContext(action="read", attributes={})) is True
