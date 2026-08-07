"""The tool registry and its authorization rules (docs/060 "TOOL
REGISTRY", "TOOL EXECUTION").

A tool has two halves: a database row (:class:`~app.models.tool
.AgentTool`) describing it to the model and carrying its required
permission, and a Python handler that actually does the work. This
module binds them and enforces the rules before anything runs --
mirrors ``ai-assistant-service``'s own ``app/tool_calling/registry.py``
(Prompt 046) shape, generalized from its per-conversation
``required_permission: str | None`` to this service's own agent-shaped
:class:`~app.models.enums.PermissionCategory`, and from a static
``caller_permissions`` list to *granted* categories
(:class:`~app.models.permission.AgentPermissionGrant`, status
``GRANTED``) -- an agent's own capability grants, not a per-request
claim.

**Authorization is structural, layered, and fails closed:**

1. The agent must list the tool in its own profile's
   ``allowed_tool_keys``. A model cannot invoke a tool its agent was
   never granted, no matter what it emits.
2. The tool must be enabled.
3. The caller must hold a ``GRANTED`` permission for the tool's own
   ``required_permission`` category.
4. A mutating tool additionally requires the caller to have explicitly
   opted into mutations for that turn -- so an agent answering a
   question can never restart a server as a side effect.

Every attempt is recorded either way by :mod:`app.tool_execution
.executor`. A denial is a first-class outcome
(:attr:`~app.models.enums.ToolCallStatus.DENIED`) with its own reason,
not a silent no-op, which is what makes "Permission-aware Tool Calls"
auditable after the fact.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.clients.base import ToolSpecification
from app.models.enums import PermissionCategory
from app.models.tool import AgentTool

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
"""A tool's own implementation: arguments in, JSON-shaped result out."""


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    """Whether one tool call may proceed, and why not if it may not."""

    allowed: bool
    reason: str | None = None


ALLOWED = AuthorizationDecision(allowed=True)


def authorize(
    tool: AgentTool,
    *,
    agent_tool_keys: Sequence[str],
    granted_categories: Sequence[PermissionCategory],
    allow_mutating: bool,
) -> AuthorizationDecision:
    """Decide whether a tool call may run.

    Checks are ordered cheapest-and-most-specific first so the recorded
    denial reason names the *actual* blocker rather than a later,
    vaguer one.
    """
    if tool.tool_key not in agent_tool_keys:
        return AuthorizationDecision(
            allowed=False,
            reason=f"Agent is not granted tool {tool.tool_key!r}.",
        )
    if not tool.enabled:
        return AuthorizationDecision(allowed=False, reason=f"Tool {tool.tool_key!r} is disabled.")
    if tool.required_permission not in granted_categories:
        return AuthorizationDecision(
            allowed=False,
            reason=(
                f"Caller lacks a granted {tool.required_permission!s} permission "
                f"required by tool {tool.tool_key!r}."
            ),
        )
    if tool.is_mutating and not allow_mutating:
        return AuthorizationDecision(
            allowed=False,
            reason=(
                f"Tool {tool.tool_key!r} mutates state and this request did not "
                "opt into mutating tool calls."
            ),
        )
    return ALLOWED


def validate_arguments(tool: AgentTool, arguments: dict[str, Any]) -> str | None:
    """Validate *arguments* against the tool's own declared schema.

    Returns an error message, or ``None`` when valid. Deliberately a
    focused check of the JSON Schema subset actually used by tool
    definitions -- required keys, known properties, and primitive
    types -- rather than a full validator: a model's own malformed
    output fails on exactly these, and pulling in a schema library for
    the rest would not catch anything more in practice.
    """
    schema = tool.parameters_schema or {}
    properties = schema.get("properties") or {}
    required = schema.get("required") or []

    missing = [name for name in required if name not in arguments]
    if missing:
        return f"Missing required argument(s): {', '.join(sorted(missing))}."

    if properties and not schema.get("additionalProperties", False):
        unknown = [name for name in arguments if name not in properties]
        if unknown:
            return f"Unknown argument(s): {', '.join(sorted(unknown))}."

    expected_types: dict[str, tuple[type, ...]] = {
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "array": (list,),
        "object": (dict,),
    }
    for name, value in arguments.items():
        declared = (properties.get(name) or {}).get("type")
        if not declared:
            continue
        allowed_types = expected_types.get(declared)
        if allowed_types is None:
            continue
        # bool is a subclass of int in Python; an integer field must not
        # silently accept True.
        if declared in ("integer", "number") and isinstance(value, bool):
            return f"Argument {name!r} must be {declared}, got boolean."
        if not isinstance(value, allowed_types):
            return f"Argument {name!r} must be {declared}, got {type(value).__name__}."

    return None


def to_specification(tool: AgentTool) -> ToolSpecification:
    """Describe a tool to the model in provider-neutral form."""
    return ToolSpecification(
        name=tool.tool_key,
        description=tool.description or "",
        parameters_schema=tool.parameters_schema or {"type": "object", "properties": {}},
    )


class ToolHandlerRegistry:
    """Maps a tool's own ``tool_key`` onto its Python implementation."""

    def __init__(self, handlers: dict[str, ToolHandler] | None = None) -> None:
        self._handlers: dict[str, ToolHandler] = dict(handlers or {})

    def register(self, tool_key: str, handler: ToolHandler) -> None:
        """Register (or replace) the handler for *tool_key*."""
        self._handlers[tool_key] = handler

    def get(self, tool_key: str) -> ToolHandler | None:
        """Return the handler for *tool_key*, or ``None`` if unregistered."""
        return self._handlers.get(tool_key)

    @property
    def registered_keys(self) -> list[str]:
        """Every tool key with a live handler."""
        return sorted(self._handlers)


__all__ = [
    "ALLOWED",
    "AuthorizationDecision",
    "ToolHandler",
    "ToolHandlerRegistry",
    "authorize",
    "to_specification",
    "validate_arguments",
]
