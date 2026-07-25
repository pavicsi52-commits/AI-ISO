"""Workflow validation rules (docs/016 "WORKFLOW VALIDATION").

Structural validation of an abstract workflow graph (nodes + directed
edges) and its declared execution properties -- no workflow *engine* is
implemented here (docs/016 "DO NOT IMPLEMENT": "Automation"), only
validation of a graph definition any future automation engine would need
to have already passed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from shared_core.enums.permission import Permission
from shared_core.enums.role import Role
from shared_core.security.rbac import has_permission
from shared_core.validation.base import ValidationSeverity
from shared_core.validation.results import ValidationResult

_WHITE, _GRAY, _BLACK = 0, 1, 2


def check_circular_dependency(
    nodes: Sequence[str], edges: Sequence[tuple[str, str]]
) -> ValidationResult:
    """Validate a directed node graph contains no cycle (DFS-based)."""
    graph: dict[str, list[str]] = {node: [] for node in nodes}
    for source, target in edges:
        graph.setdefault(source, []).append(target)

    color = dict.fromkeys(graph, _WHITE)

    def _has_cycle(start: str) -> bool:
        stack = [(start, iter(graph.get(start, [])))]
        color[start] = _GRAY
        while stack:
            node, neighbors = stack[-1]
            advanced = False
            for neighbor in neighbors:
                state = color.get(neighbor, _WHITE)
                if state == _GRAY:
                    return True
                if state == _WHITE:
                    color[neighbor] = _GRAY
                    stack.append((neighbor, iter(graph.get(neighbor, []))))
                    advanced = True
                    break
            if not advanced:
                color[node] = _BLACK
                stack.pop()
        return False

    if any(color[node] == _WHITE and _has_cycle(node) for node in graph):
        return ValidationResult.fail("Workflow graph contains a circular dependency.")
    return ValidationResult.ok()


def check_infinite_loop(loop_nodes: Sequence[Mapping[str, Any]]) -> ValidationResult:
    """Validate every loop-type node declares a bounded, positive iteration count."""
    errors = [
        f"Loop node '{node.get('id', '?')}' must declare a positive integer 'max_iterations'."
        for node in loop_nodes
        if not isinstance(node.get("max_iterations"), int) or node.get("max_iterations", 0) <= 0
    ]
    if errors:
        return ValidationResult.fail(*errors)
    return ValidationResult.ok()


def check_missing_node(nodes: Sequence[str], edges: Sequence[tuple[str, str]]) -> ValidationResult:
    """Validate every edge references a node that's actually defined."""
    node_set = set(nodes)
    missing = {endpoint for edge in edges for endpoint in edge if endpoint not in node_set}
    if missing:
        return ValidationResult.fail(
            f"Edge(s) reference undefined node(s): {', '.join(sorted(missing))}."
        )
    return ValidationResult.ok()


def check_invalid_transition(
    *, from_state: str, to_state: str, allowed_transitions: Mapping[str, set[str]]
) -> ValidationResult:
    """Validate a state transition is in the allowed transition table."""
    if to_state not in allowed_transitions.get(from_state, set()):
        return ValidationResult.fail(
            f"Transition from '{from_state}' to '{to_state}' is not allowed."
        )
    return ValidationResult.ok()


def check_workflow_permission(*, role: Role, required_permission: Permission) -> ValidationResult:
    """Validate a role may execute a workflow requiring a given permission."""
    if not has_permission(role, required_permission):
        return ValidationResult.fail(f"Role '{role.value}' cannot execute this workflow.")
    return ValidationResult.ok()


def check_required_inputs(
    *, provided: Mapping[str, Any], required: Sequence[str]
) -> ValidationResult:
    """Validate every required workflow input was provided."""
    missing = [name for name in required if name not in provided]
    if missing:
        return ValidationResult.fail(f"Missing required workflow input(s): {', '.join(missing)}.")
    return ValidationResult.ok()


def check_workflow_timeout(
    *, timeout_seconds: int | None, max_timeout_seconds: int
) -> ValidationResult:
    """Validate a workflow declares a positive timeout within the allowed maximum."""
    if timeout_seconds is None or timeout_seconds <= 0:
        return ValidationResult.fail("Workflow must declare a positive 'timeout_seconds'.")
    if timeout_seconds > max_timeout_seconds:
        return ValidationResult.fail(
            f"Workflow timeout {timeout_seconds}s exceeds the maximum of {max_timeout_seconds}s."
        )
    return ValidationResult.ok()


def check_rollback_support(*, supports_rollback: bool, is_destructive: bool) -> ValidationResult:
    """Validate destructive workflow steps declare rollback support."""
    if is_destructive and not supports_rollback:
        return ValidationResult.fail(
            "Destructive workflow steps must declare rollback support.",
            severity=ValidationSeverity.WARNING,
        )
    return ValidationResult.ok()
