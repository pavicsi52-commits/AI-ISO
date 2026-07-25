"""Plugin dependency resolution.

Per docs/029_Enterprise_Plugin_Framework.md.txt "DEPENDENCY MANAGEMENT":
Required Dependencies, Optional Dependencies, Version Constraints,
Circular Dependency Detection, Conflict Resolution. DFS-based cycle
detection, the same "WHITE/GRAY/BLACK"-style approach as
:meth:`shared_core.scheduler.dependency.DependencyGraph.has_cycle` and
:func:`shared_core.workflow.dag.detect_cycle`, applied here to a
plugin-id -> required-plugin-id graph.
"""

from __future__ import annotations

from shared_core.plugins.exceptions import CircularDependencyError, DependencyResolutionError
from shared_core.plugins.manifest import PluginManifest
from shared_core.plugins.versioning import is_compatible

_UNVISITED = 0
_VISITING = 1
_VISITED = 2


class DependencyResolver:
    """Resolves a load/install order across a set of plugin manifests."""

    def __init__(self, manifests: dict[str, PluginManifest]) -> None:
        self._manifests = manifests

    def _required_dependencies_of(self, plugin_id: str) -> tuple[str, ...]:
        manifest = self._manifests.get(plugin_id)
        if manifest is None:
            return ()
        return tuple(
            dependency.depends_on_plugin_id
            for dependency in manifest.dependencies
            if not dependency.optional and dependency.depends_on_plugin_id in self._manifests
        )

    def validate(self, plugin_id: str) -> None:
        """Validate every dependency of *plugin_id* is present (if required) and version-compatible.

        A missing *optional* dependency is silently skipped; a present
        dependency (required or optional) still has its version
        constraint enforced ("Version Constraints").

        Raises:
            DependencyResolutionError: If a required dependency is
                missing, or any present dependency's version doesn't
                satisfy its constraint ("Conflict Resolution").
        """
        manifest = self._manifests.get(plugin_id)
        if manifest is None:
            raise DependencyResolutionError(f"Plugin {plugin_id!r} is not registered.")
        for dependency in manifest.dependencies:
            target = self._manifests.get(dependency.depends_on_plugin_id)
            if target is None:
                if dependency.optional:
                    continue
                raise DependencyResolutionError(
                    f"Plugin {plugin_id!r} requires "
                    f"{dependency.depends_on_plugin_id!r}, which is not installed."
                )
            if not is_compatible(target.metadata.version, dependency.version_constraint):
                raise DependencyResolutionError(
                    f"Plugin {plugin_id!r} requires {dependency.depends_on_plugin_id!r}"
                    f"{dependency.version_constraint!r}, found "
                    f"{target.metadata.version!r}."
                )

    def has_cycle(self) -> bool:
        """Detect a dependency cycle via depth-first search ("Circular Dependency Detection")."""
        color: dict[str, int] = dict.fromkeys(self._manifests, _UNVISITED)

        def visit(plugin_id: str) -> bool:
            color[plugin_id] = _VISITING
            for dependency_id in self._required_dependencies_of(plugin_id):
                neighbor_color = color.get(dependency_id, _UNVISITED)
                if neighbor_color == _VISITING:
                    return True
                if neighbor_color == _UNVISITED and visit(dependency_id):
                    return True
            color[plugin_id] = _VISITED
            return False

        return any(color[plugin_id] == _UNVISITED and visit(plugin_id) for plugin_id in list(color))

    def resolve_order(self) -> list[str]:
        """Compute a load order where every plugin comes after its required dependencies.

        Raises:
            CircularDependencyError: If the dependency graph contains a cycle.
        """
        if self.has_cycle():
            raise CircularDependencyError("Plugin dependencies contain a cycle.")

        order: list[str] = []
        visited: set[str] = set()

        def visit(plugin_id: str) -> None:
            if plugin_id in visited:
                return
            visited.add(plugin_id)
            for dependency_id in self._required_dependencies_of(plugin_id):
                visit(dependency_id)
            order.append(plugin_id)

        for plugin_id in self._manifests:
            visit(plugin_id)
        return order


__all__ = ["DependencyResolver"]
