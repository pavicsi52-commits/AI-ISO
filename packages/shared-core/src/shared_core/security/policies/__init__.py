"""Attribute-based policy engine.

Per docs/017_Enterprise_Security_Framework.md.txt's RBAC pipeline:
"Users -> Roles -> Permissions -> Policies -> Resources -> Actions". A
policy is a predicate over a :class:`PolicyContext`; the engine grants
access only if every registered policy for an action passes -- "Deny by
Default" (docs/017 "SECURITY PRINCIPLES").
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

PolicyPredicate = Callable[["PolicyContext"], bool]


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """Everything a policy predicate might need to make its decision."""

    action: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Policy:
    """A named, evaluatable access-control rule."""

    name: str
    predicate: PolicyPredicate


class PolicyEngine:
    """Registers policies per action and evaluates them -- deny by default."""

    def __init__(self) -> None:
        self._policies: dict[str, list[Policy]] = {}

    def register(self, action: str, policy: Policy) -> None:
        """Register *policy* as one of the checks required for *action*."""
        self._policies.setdefault(action, []).append(policy)

    def policies_for(self, action: str) -> list[Policy]:
        """Every policy registered for *action*."""
        return list(self._policies.get(action, []))

    def evaluate(self, context: PolicyContext) -> bool:
        """Return whether *every* policy registered for the context's action passes.

        An action with no registered policies is denied -- "Deny by
        Default" (docs/017 "SECURITY PRINCIPLES") -- rather than silently
        permitted because nobody wrote a rule for it yet.
        """
        policies = self._policies.get(context.action, [])
        if not policies:
            return False
        return all(policy.predicate(context) for policy in policies)
