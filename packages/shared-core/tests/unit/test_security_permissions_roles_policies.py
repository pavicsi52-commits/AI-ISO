"""Tests for resource-scoped permissions, custom/inherited roles, and the policy engine."""

from __future__ import annotations

from uuid import uuid4

from shared_core.enums import Permission, Role
from shared_core.security.permissions import can_access_resource, effective_permissions
from shared_core.security.policies import Policy, PolicyContext, PolicyEngine
from shared_core.security.roles import CustomRole, resolve_custom_role_permissions

# --- permissions/ ---


def test_can_access_resource_true_when_role_grants_permission() -> None:
    assert can_access_resource(role=Role.OPERATOR, permission=Permission.CREATE) is True


def test_can_access_resource_true_when_requester_owns_resource() -> None:
    owner_id = uuid4()

    result = can_access_resource(
        role=Role.VIEWER,
        permission=Permission.DELETE,
        resource_owner_id=owner_id,
        requester_id=owner_id,
    )

    assert result is True


def test_can_access_resource_false_when_neither_role_nor_ownership() -> None:
    result = can_access_resource(
        role=Role.VIEWER,
        permission=Permission.DELETE,
        resource_owner_id=uuid4(),
        requester_id=uuid4(),
    )

    assert result is False


def test_effective_permissions_includes_role_and_explicit_grants() -> None:
    result = effective_permissions(Role.VIEWER, explicit_grants=frozenset({Permission.DELETE}))

    assert Permission.READ in result  # from role
    assert Permission.DELETE in result  # explicit grant


# --- roles/ ---


def test_resolve_custom_role_with_no_inheritance() -> None:
    role = CustomRole(name="custom", additional_permissions=frozenset({Permission.READ}))

    assert resolve_custom_role_permissions(role) == frozenset({Permission.READ})


def test_resolve_custom_role_inherits_base_role_permissions() -> None:
    role = CustomRole(name="custom", inherits_from=Role.VIEWER)

    result = resolve_custom_role_permissions(role)

    assert Permission.READ in result


def test_resolve_custom_role_adds_additional_permissions() -> None:
    role = CustomRole(
        name="custom",
        inherits_from=Role.OPERATOR,
        additional_permissions=frozenset({Permission.APPROVE}),
    )

    result = resolve_custom_role_permissions(role)

    assert Permission.APPROVE in result
    assert Permission.CREATE in result  # from OPERATOR


def test_resolve_custom_role_subtracts_revoked_permissions() -> None:
    role = CustomRole(
        name="custom",
        inherits_from=Role.OPERATOR,
        revoked_permissions=frozenset({Permission.EXECUTE}),
    )

    result = resolve_custom_role_permissions(role)

    assert Permission.EXECUTE not in result
    assert Permission.READ in result


# --- policies/ ---


def test_policy_engine_denies_by_default_for_unregistered_action() -> None:
    engine = PolicyEngine()

    result = engine.evaluate(PolicyContext(action="delete_project"))

    assert result is False


def test_policy_engine_grants_when_all_policies_pass() -> None:
    engine = PolicyEngine()
    engine.register("delete_project", Policy(name="always_true", predicate=lambda ctx: True))

    result = engine.evaluate(PolicyContext(action="delete_project"))

    assert result is True


def test_policy_engine_denies_when_any_policy_fails() -> None:
    engine = PolicyEngine()
    engine.register("delete_project", Policy(name="always_true", predicate=lambda ctx: True))
    engine.register("delete_project", Policy(name="always_false", predicate=lambda ctx: False))

    result = engine.evaluate(PolicyContext(action="delete_project"))

    assert result is False


def test_policy_engine_predicate_receives_context_attributes() -> None:
    engine = PolicyEngine()

    def _is_business_hours(ctx: PolicyContext) -> bool:
        return ctx.attributes.get("hour", 0) < 18

    engine.register("publish", Policy(name="business_hours_only", predicate=_is_business_hours))

    daytime_result = engine.evaluate(PolicyContext(action="publish", attributes={"hour": 10}))
    nighttime_result = engine.evaluate(PolicyContext(action="publish", attributes={"hour": 22}))

    assert daytime_result is True
    assert nighttime_result is False


def test_policy_engine_policies_for_returns_registered_policies() -> None:
    engine = PolicyEngine()
    policy = Policy(name="p1", predicate=lambda ctx: True)
    engine.register("action", policy)

    assert engine.policies_for("action") == [policy]


def test_policy_engine_policies_for_empty_for_unregistered_action() -> None:
    engine = PolicyEngine()

    assert engine.policies_for("unknown") == []
