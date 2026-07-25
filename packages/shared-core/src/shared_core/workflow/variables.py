"""Workflow variables.

Per docs/028_Enterprise_Workflow_SDK.md.txt "VARIABLES": Workflow
Variables, Environment Variables, Runtime Variables, Secret Variables,
System Variables, Context Variables, Scoped Variables.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

_SECRET_MASK = "***"


class VariableScope(StrEnum):
    """Every variable scope docs/028 "VARIABLES" names."""

    SYSTEM = "system"
    ENVIRONMENT = "environment"
    WORKFLOW = "workflow"
    CONTEXT = "context"
    RUNTIME = "runtime"
    SECRET = "secret"


# Lowest to highest precedence -- a higher-precedence scope's value for the
# same name wins when resolving a bare (scope-unqualified) variable reference.
_SCOPE_PRECEDENCE: tuple[VariableScope, ...] = (
    VariableScope.SYSTEM,
    VariableScope.ENVIRONMENT,
    VariableScope.WORKFLOW,
    VariableScope.CONTEXT,
    VariableScope.RUNTIME,
    VariableScope.SECRET,
)


@dataclass(frozen=True, slots=True)
class Variable:
    """One named value within a specific scope. ``repr()`` masks secret-scoped values."""

    name: str
    value: Any
    scope: VariableScope

    def __repr__(self) -> str:
        shown = _SECRET_MASK if self.scope == VariableScope.SECRET else self.value
        return f"Variable(name={self.name!r}, value={shown!r}, scope={self.scope!r})"


class VariableStore:
    """A scoped store of workflow variables ("Scoped Variables")."""

    def __init__(self) -> None:
        self._scopes: dict[VariableScope, dict[str, Any]] = {scope: {} for scope in VariableScope}

    def set(self, name: str, value: Any, *, scope: VariableScope = VariableScope.WORKFLOW) -> None:
        """Set *name* to *value* within *scope*."""
        self._scopes[scope][name] = value

    def get(self, name: str, *, scope: VariableScope | None = None, default: Any = None) -> Any:
        """Resolve *name*, either from a specific *scope* or by scope precedence."""
        if scope is not None:
            return self._scopes[scope].get(name, default)
        for candidate_scope in reversed(_SCOPE_PRECEDENCE):
            if name in self._scopes[candidate_scope]:
                return self._scopes[candidate_scope][name]
        return default

    def has(self, name: str, *, scope: VariableScope | None = None) -> bool:
        """Whether *name* is set, either within a specific *scope* or in any scope."""
        if scope is not None:
            return name in self._scopes[scope]
        return any(name in values for values in self._scopes.values())

    def as_dict(self, *, include_secrets: bool = False) -> dict[str, Any]:
        """Flatten every scope into one name -> value mapping, by precedence.

        Secret-scoped values are masked unless *include_secrets* is
        explicitly requested (by the executor actually running a task,
        never by anything that logs/serializes this).
        """
        flattened: dict[str, Any] = {}
        for scope in _SCOPE_PRECEDENCE:
            for name, value in self._scopes[scope].items():
                flattened[name] = (
                    value if include_secrets or scope != VariableScope.SECRET else _SECRET_MASK
                )
        return flattened

    def child(self) -> VariableStore:
        """Build a new store pre-populated with a snapshot of this one's current values.

        Used to give a sub-workflow/parallel-branch/loop-iteration its
        own independent variable scope seeded from the parent, so
        mutations inside don't leak back out.
        """
        child_store = VariableStore()
        for scope, values in self._scopes.items():
            child_store._scopes[scope] = dict(values)
        return child_store


__all__ = ["Variable", "VariableScope", "VariableStore"]
