"""Plugin dependency declaration and cycle-safe resolution (docs/059
"DEPENDENCY MANAGEMENT").
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.dependencies.engine import CircularDependencyError, creates_cycle, resolve_install_order
from app.models.dependency import PluginDependency
from app.repositories.dependency import PluginDependencyRepository


class PluginDependencyService:
    """Declares, reads, deletes, and cycle-checks plugin dependency edges."""

    def __init__(self, dependencies: PluginDependencyRepository) -> None:
        self._dependencies = dependencies

    async def list_for_plugin(self, plugin_id: UUID) -> list[PluginDependency]:
        """Every dependency declared by *plugin_id*."""
        return await self._dependencies.list_for_plugin(plugin_id)

    async def declare(
        self,
        organization_id: UUID,
        plugin_id: UUID,
        *,
        depends_on_plugin_id: UUID,
        version_constraint: str = "*",
        optional: bool = False,
    ) -> PluginDependency:
        """Declare a new dependency edge.

        Raises:
            ConflictError: If this edge would create a circular
                dependency chain across the organization's own graph.
        """
        edges = await self._edge_map(organization_id)
        if creates_cycle(edges, origin=plugin_id, new_dependency=depends_on_plugin_id):
            raise ConflictError(
                f"Adding a dependency from {plugin_id} on {depends_on_plugin_id} "
                "would create a circular dependency chain."
            )
        return await self._dependencies.create(
            PluginDependency(
                organization_id=organization_id,
                plugin_id=plugin_id,
                depends_on_plugin_id=depends_on_plugin_id,
                version_constraint=version_constraint,
                optional=optional,
            )
        )

    async def delete(self, dependency_id: UUID) -> None:
        """Remove a declared dependency edge."""
        await self._dependencies.delete(dependency_id)

    async def resolve_install_order(self, organization_id: UUID) -> list[UUID]:
        """The organization's own full install order across every declared
        dependency edge.

        Raises:
            CircularDependencyError: If the graph contains a cycle.
        """
        edges = await self._edge_map(organization_id)
        return resolve_install_order(edges)

    async def _edge_map(self, organization_id: UUID) -> dict[UUID, list[UUID]]:
        edges: dict[UUID, list[UUID]] = {}
        for edge in await self._dependencies.list_all_edges(organization_id):
            edges.setdefault(edge.plugin_id, []).append(edge.depends_on_plugin_id)
        return edges


__all__ = ["CircularDependencyError", "PluginDependencyService"]
