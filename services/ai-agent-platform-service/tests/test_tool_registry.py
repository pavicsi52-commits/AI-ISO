"""Tests for app.tool_registry.registry.

``authorize()`` and ``validate_arguments()`` are pure decision functions
over a plain :class:`~app.models.tool.AgentTool` object -- no database
needed, since a transient (never-flushed) SQLAlchemy instance behaves
exactly like any other Python object for attribute access. Every field
these functions read is set explicitly on the tool fixtures below,
since an unset mapped column on a transient instance is ``None``, not
its eventual database-level default.
"""

from __future__ import annotations

from typing import Any

from app.clients.base import ToolSpecification
from app.models.enums import PermissionCategory, ToolKind
from app.models.tool import AgentTool
from app.tool_registry.registry import (
    ALLOWED,
    AuthorizationDecision,
    ToolHandlerRegistry,
    authorize,
    to_specification,
    validate_arguments,
)


def _tool(
    *,
    tool_key: str = "sample-tool",
    enabled: bool = True,
    is_mutating: bool = False,
    required_permission: PermissionCategory = PermissionCategory.TOOL_INVOCATION,
    parameters_schema: dict[str, Any] | None = None,
    description: str | None = "A sample tool.",
    tool_kind: ToolKind = ToolKind.CUSTOM,
) -> AgentTool:
    return AgentTool(
        tool_key=tool_key,
        name="Sample Tool",
        description=description,
        tool_kind=tool_kind,
        required_permission=required_permission,
        is_mutating=is_mutating,
        enabled=enabled,
        parameters_schema=parameters_schema,
    )


_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "count": {"type": "integer"},
        "ratio": {"type": "number"},
        "enabled": {"type": "boolean"},
        "items": {"type": "array"},
        "meta": {"type": "object"},
        "weird": {"type": "null"},
        "free": {},
    },
    "required": ["name"],
}


# ---------------------------------------------------------------------------
# authorize()
# ---------------------------------------------------------------------------


def test_authorize_allowed_when_all_checks_pass() -> None:
    tool = _tool(required_permission=PermissionCategory.NETWORK)
    decision = authorize(
        tool,
        agent_tool_keys=["sample-tool"],
        granted_categories=[PermissionCategory.NETWORK],
        allow_mutating=False,
    )
    assert decision == ALLOWED
    assert decision.allowed is True
    assert decision.reason is None


def test_authorize_denied_when_tool_not_granted_to_agent() -> None:
    tool = _tool(tool_key="not-granted")
    decision = authorize(
        tool,
        agent_tool_keys=["some-other-tool"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
        allow_mutating=False,
    )
    assert decision.allowed is False
    assert decision.reason == "Agent is not granted tool 'not-granted'."


def test_authorize_denied_when_tool_disabled() -> None:
    tool = _tool(tool_key="disabled-tool", enabled=False)
    decision = authorize(
        tool,
        agent_tool_keys=["disabled-tool"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
        allow_mutating=False,
    )
    assert decision.allowed is False
    assert decision.reason == "Tool 'disabled-tool' is disabled."


def test_authorize_denied_when_permission_not_granted() -> None:
    tool = _tool(tool_key="net-tool", required_permission=PermissionCategory.NETWORK)
    decision = authorize(
        tool,
        agent_tool_keys=["net-tool"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
        allow_mutating=False,
    )
    assert decision.allowed is False
    assert decision.reason == (
        "Caller lacks a granted network permission required by tool 'net-tool'."
    )


def test_authorize_denied_when_mutating_and_not_opted_in() -> None:
    tool = _tool(tool_key="mutator", is_mutating=True)
    decision = authorize(
        tool,
        agent_tool_keys=["mutator"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
        allow_mutating=False,
    )
    assert decision.allowed is False
    assert decision.reason == (
        "Tool 'mutator' mutates state and this request did not opt into mutating tool calls."
    )


def test_authorize_allowed_when_mutating_and_opted_in() -> None:
    tool = _tool(tool_key="mutator", is_mutating=True)
    decision = authorize(
        tool,
        agent_tool_keys=["mutator"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
        allow_mutating=True,
    )
    assert decision == ALLOWED


def test_authorize_not_granted_check_wins_over_disabled() -> None:
    # Not in agent_tool_keys AND disabled -- the recorded reason must
    # name the check ordered first (cheapest-and-most-specific), not
    # the ambiguous "and also disabled" fact.
    tool = _tool(tool_key="ghost", enabled=False)
    decision = authorize(tool, agent_tool_keys=[], granted_categories=[], allow_mutating=False)
    assert decision.reason == "Agent is not granted tool 'ghost'."


def test_authorize_disabled_check_wins_over_permission() -> None:
    tool = _tool(
        tool_key="both-broken",
        enabled=False,
        required_permission=PermissionCategory.ADMINISTRATIVE,
    )
    decision = authorize(
        tool,
        agent_tool_keys=["both-broken"],
        granted_categories=[],
        allow_mutating=False,
    )
    assert decision.reason == "Tool 'both-broken' is disabled."


def test_authorize_permission_check_wins_over_mutating() -> None:
    tool = _tool(
        tool_key="perm-and-mutate",
        required_permission=PermissionCategory.ADMINISTRATIVE,
        is_mutating=True,
    )
    decision = authorize(
        tool,
        agent_tool_keys=["perm-and-mutate"],
        granted_categories=[],
        allow_mutating=False,
    )
    assert decision.reason == (
        "Caller lacks a granted administrative permission required by tool 'perm-and-mutate'."
    )


def test_authorization_decision_equality() -> None:
    assert AuthorizationDecision(allowed=True) == ALLOWED
    assert AuthorizationDecision(allowed=False, reason="x") != ALLOWED


# ---------------------------------------------------------------------------
# validate_arguments()
# ---------------------------------------------------------------------------


def test_validate_arguments_valid_returns_none() -> None:
    tool = _tool(parameters_schema=_SCHEMA)
    assert validate_arguments(tool, {"name": "x", "count": 3}) is None


def test_validate_arguments_missing_required_reports_sorted_names() -> None:
    schema = {**_SCHEMA, "required": ["name", "count"]}
    tool = _tool(parameters_schema=schema)
    error = validate_arguments(tool, {})
    assert error == "Missing required argument(s): count, name."


def test_validate_arguments_unknown_argument_denied_by_default() -> None:
    tool = _tool(parameters_schema=_SCHEMA)
    error = validate_arguments(tool, {"name": "x", "bogus": 1})
    assert error == "Unknown argument(s): bogus."


def test_validate_arguments_unknown_argument_allowed_when_additional_properties() -> None:
    schema = {**_SCHEMA, "additionalProperties": True}
    tool = _tool(parameters_schema=schema)
    error = validate_arguments(tool, {"name": "x", "extra": "anything"})
    assert error is None


def test_validate_arguments_unknown_check_skipped_when_no_properties_declared() -> None:
    # No `properties` key at all -- the unknown-argument check never
    # runs, even without an explicit additionalProperties: True.
    tool = _tool(parameters_schema={"required": ["x"]})
    assert validate_arguments(tool, {"x": 1, "anything": "goes"}) is None


def test_validate_arguments_no_schema_defaults_to_empty_dict() -> None:
    tool = _tool(parameters_schema=None)
    assert validate_arguments(tool, {"whatever": 1}) is None


def test_validate_arguments_string_type_mismatch() -> None:
    tool = _tool(parameters_schema=_SCHEMA)
    error = validate_arguments(tool, {"name": 5})
    assert error == "Argument 'name' must be string, got int."


def test_validate_arguments_integer_type_mismatch() -> None:
    tool = _tool(parameters_schema=_SCHEMA)
    error = validate_arguments(tool, {"name": "ok", "count": "3"})
    assert error == "Argument 'count' must be integer, got str."


def test_validate_arguments_number_accepts_int_and_float() -> None:
    tool = _tool(parameters_schema=_SCHEMA)
    assert validate_arguments(tool, {"name": "ok", "ratio": 1}) is None
    assert validate_arguments(tool, {"name": "ok", "ratio": 1.5}) is None


def test_validate_arguments_boolean_field_accepts_bool_rejects_int() -> None:
    tool = _tool(parameters_schema=_SCHEMA)
    assert validate_arguments(tool, {"name": "ok", "enabled": True}) is None
    error = validate_arguments(tool, {"name": "ok", "enabled": 1})
    assert error == "Argument 'enabled' must be boolean, got int."


def test_validate_arguments_bool_rejected_for_integer_field() -> None:
    # bool is a subclass of int in Python -- an integer field must not
    # silently accept True/False.
    tool = _tool(parameters_schema=_SCHEMA)
    error = validate_arguments(tool, {"name": "ok", "count": True})
    assert error == "Argument 'count' must be integer, got boolean."


def test_validate_arguments_bool_rejected_for_number_field() -> None:
    tool = _tool(parameters_schema=_SCHEMA)
    error = validate_arguments(tool, {"name": "ok", "ratio": False})
    assert error == "Argument 'ratio' must be number, got boolean."


def test_validate_arguments_array_and_object_types() -> None:
    tool = _tool(parameters_schema=_SCHEMA)
    assert validate_arguments(tool, {"name": "ok", "items": [1, 2]}) is None
    error = validate_arguments(tool, {"name": "ok", "items": "not-a-list"})
    assert error == "Argument 'items' must be array, got str."

    assert validate_arguments(tool, {"name": "ok", "meta": {"a": 1}}) is None
    error = validate_arguments(tool, {"name": "ok", "meta": []})
    assert error == "Argument 'meta' must be object, got list."


def test_validate_arguments_unknown_declared_type_is_skipped() -> None:
    # "null" is not in the expected_types table -- the field's own
    # type check is silently skipped, real production behaviour.
    tool = _tool(parameters_schema=_SCHEMA)
    assert validate_arguments(tool, {"name": "ok", "weird": object()}) is None


def test_validate_arguments_property_without_declared_type_is_skipped() -> None:
    tool = _tool(parameters_schema=_SCHEMA)
    assert validate_arguments(tool, {"name": "ok", "free": ["anything"]}) is None


# ---------------------------------------------------------------------------
# to_specification()
# ---------------------------------------------------------------------------


def test_to_specification_carries_real_fields() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    tool = _tool(tool_key="my-tool", description="Does X.", parameters_schema=schema)
    spec = to_specification(tool)
    assert spec == ToolSpecification(
        name="my-tool", description="Does X.", parameters_schema=schema
    )


def test_to_specification_defaults_missing_description_and_schema() -> None:
    tool = _tool(tool_key="bare-tool", description=None, parameters_schema=None)
    spec = to_specification(tool)
    assert spec.name == "bare-tool"
    assert spec.description == ""
    assert spec.parameters_schema == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# ToolHandlerRegistry
# ---------------------------------------------------------------------------


async def _echo(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"echo": arguments}


async def _shout(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"shout": arguments}


def test_registry_starts_empty() -> None:
    registry = ToolHandlerRegistry()
    assert registry.registered_keys == []
    assert registry.get("anything") is None


def test_registry_register_and_get() -> None:
    registry = ToolHandlerRegistry()
    registry.register("echo", _echo)
    assert registry.get("echo") is _echo


def test_registry_get_unregistered_returns_none() -> None:
    registry = ToolHandlerRegistry()
    registry.register("echo", _echo)
    assert registry.get("does-not-exist") is None


def test_registry_register_replaces_existing_handler() -> None:
    registry = ToolHandlerRegistry()
    registry.register("key", _echo)
    registry.register("key", _shout)
    assert registry.get("key") is _shout


def test_registry_registered_keys_sorted() -> None:
    registry = ToolHandlerRegistry()
    registry.register("zeta", _echo)
    registry.register("alpha", _shout)
    assert registry.registered_keys == ["alpha", "zeta"]


def test_registry_seeded_via_constructor() -> None:
    registry = ToolHandlerRegistry({"seeded": _echo})
    assert registry.get("seeded") is _echo
    assert registry.registered_keys == ["seeded"]


async def test_registry_handler_is_actually_callable() -> None:
    registry = ToolHandlerRegistry({"echo": _echo})
    handler = registry.get("echo")
    assert handler is not None
    result = await handler({"x": 1})
    assert result == {"echo": {"x": 1}}
