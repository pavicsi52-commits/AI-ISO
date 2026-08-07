"""Dependency-graph cycle detection and install-order resolution.

Operates on a plain edge map (``plugin_id`` -> its required
``depends_on_plugin_id`` set) that ``PluginDependencyService`` builds
from real ``PluginDependencyRepository`` rows spanning organizations --
a genuinely DB-backed graph, unlike
``shared_core.plugins.resolver.DependencyResolver``, which only ever
walks an in-memory ``dict[str, PluginManifest]`` for one already-loaded
process. Real DFS cycle detection (WHITE/GRAY/BLACK), the same approach
``shared_core.plugins.resolver.DependencyResolver.has_cycle`` and
``playbook-service/app/services/dependency.py``'s own
``PlaybookDependencyService._creates_cycle`` both already use.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from uuid import UUID

_WHITE = 0
_GRAY = 1
_BLACK = 2


class CircularDependencyError(Exception):
    """Adding an edge to the dependency graph would create a cycle."""


def creates_cycle(edges: Mapping[UUID, Iterable[UUID]], origin: UUID, new_dependency: UUID) -> bool:
    """Whether adding an edge ``origin -> new_dependency`` would create a
    cycle, given the *existing* edges already in the graph.
    """
    if new_dependency == origin:
        return True
    visited: set[UUID] = set()
    stack = [new_dependency]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == origin:
            return True
        stack.extend(neighbor for neighbor in edges.get(current, ()) if neighbor not in visited)
    return False


def resolve_install_order(edges: Mapping[UUID, Iterable[UUID]]) -> list[UUID]:
    """Topologically order every plugin in *edges* so each comes after
    every plugin it depends on.

    Raises:
        CircularDependencyError: If the graph contains a cycle.
    """
    color: dict[UUID, int] = {}
    order: list[UUID] = []

    def visit(node: UUID) -> None:
        color[node] = _GRAY
        for neighbor in edges.get(node, ()):
            neighbor_color = color.get(neighbor, _WHITE)
            if neighbor_color == _GRAY:
                raise CircularDependencyError(
                    f"Dependency graph contains a cycle involving {neighbor}."
                )
            if neighbor_color == _WHITE:
                visit(neighbor)
        color[node] = _BLACK
        order.append(node)

    for node in list(edges):
        if color.get(node, _WHITE) == _WHITE:
            visit(node)
    return order


__all__ = ["CircularDependencyError", "creates_cycle", "resolve_install_order"]
