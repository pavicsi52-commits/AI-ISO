"""Tests for :class:`app.services.dependency.PluginDependencyService` --
declaration, cycle-safe guarding, deletion, and install-order resolution
over a real DB-backed dependency graph.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from shared_core.exceptions.conflict import ConflictError

from app.models.dependency import PluginDependency
from app.repositories.dependency import PluginDependencyRepository
from app.services.dependency import CircularDependencyError, PluginDependencyService


class TestListAndDeclare:
    async def test_list_for_plugin_empty_then_populated(
        self,
        dependency_service: PluginDependencyService,
        make_plugin: Callable[..., Awaitable[Any]],
    ) -> None:
        plugin_a = await make_plugin(slug="dep-list-a")
        plugin_b = await make_plugin(slug="dep-list-b")

        assert await dependency_service.list_for_plugin(plugin_a.id) == []

        await dependency_service.declare(
            plugin_a.organization_id, plugin_a.id, depends_on_plugin_id=plugin_b.id
        )

        edges = await dependency_service.list_for_plugin(plugin_a.id)
        assert len(edges) == 1
        assert edges[0].plugin_id == plugin_a.id
        assert edges[0].depends_on_plugin_id == plugin_b.id

    async def test_declare_happy_path_sets_all_fields(
        self,
        dependency_service: PluginDependencyService,
        make_plugin: Callable[..., Awaitable[Any]],
    ) -> None:
        plugin_a = await make_plugin(slug="dep-fields-a")
        plugin_b = await make_plugin(slug="dep-fields-b")

        dependency = await dependency_service.declare(
            plugin_a.organization_id,
            plugin_a.id,
            depends_on_plugin_id=plugin_b.id,
            version_constraint=">=1.0.0,<2.0.0",
            optional=True,
        )

        assert dependency.organization_id == plugin_a.organization_id
        assert dependency.plugin_id == plugin_a.id
        assert dependency.depends_on_plugin_id == plugin_b.id
        assert dependency.version_constraint == ">=1.0.0,<2.0.0"
        assert dependency.optional is True

    async def test_declare_defaults(
        self,
        dependency_service: PluginDependencyService,
        make_plugin: Callable[..., Awaitable[Any]],
    ) -> None:
        plugin_a = await make_plugin(slug="dep-defaults-a")
        plugin_b = await make_plugin(slug="dep-defaults-b")

        dependency = await dependency_service.declare(
            plugin_a.organization_id, plugin_a.id, depends_on_plugin_id=plugin_b.id
        )

        assert dependency.version_constraint == "*"
        assert dependency.optional is False

    async def test_declare_self_reference_raises_conflict(
        self,
        dependency_service: PluginDependencyService,
        make_plugin: Callable[..., Awaitable[Any]],
    ) -> None:
        plugin_a = await make_plugin(slug="dep-self")
        with pytest.raises(ConflictError, match="circular"):
            await dependency_service.declare(
                plugin_a.organization_id, plugin_a.id, depends_on_plugin_id=plugin_a.id
            )

    async def test_declare_transitive_cycle_raises_conflict(
        self,
        dependency_service: PluginDependencyService,
        make_plugin: Callable[..., Awaitable[Any]],
    ) -> None:
        plugin_a = await make_plugin(slug="dep-cycle-a")
        plugin_b = await make_plugin(slug="dep-cycle-b")

        # a -> b is fine.
        await dependency_service.declare(
            plugin_a.organization_id, plugin_a.id, depends_on_plugin_id=plugin_b.id
        )
        # b -> a would close the cycle.
        with pytest.raises(ConflictError, match="circular"):
            await dependency_service.declare(
                plugin_b.organization_id, plugin_b.id, depends_on_plugin_id=plugin_a.id
            )

    async def test_declare_non_cyclic_edge_succeeds(
        self,
        dependency_service: PluginDependencyService,
        make_plugin: Callable[..., Awaitable[Any]],
    ) -> None:
        plugin_a = await make_plugin(slug="dep-noncyclic-a")
        plugin_b = await make_plugin(slug="dep-noncyclic-b")
        plugin_c = await make_plugin(slug="dep-noncyclic-c")

        await dependency_service.declare(
            plugin_a.organization_id, plugin_a.id, depends_on_plugin_id=plugin_b.id
        )
        # a -> c does not touch the a -> b edge at all -- no cycle.
        dependency = await dependency_service.declare(
            plugin_a.organization_id, plugin_a.id, depends_on_plugin_id=plugin_c.id
        )
        assert dependency.depends_on_plugin_id == plugin_c.id


class TestDelete:
    async def test_delete_removes_edge(
        self,
        dependency_service: PluginDependencyService,
        make_plugin: Callable[..., Awaitable[Any]],
    ) -> None:
        plugin_a = await make_plugin(slug="dep-delete-a")
        plugin_b = await make_plugin(slug="dep-delete-b")
        dependency = await dependency_service.declare(
            plugin_a.organization_id, plugin_a.id, depends_on_plugin_id=plugin_b.id
        )

        await dependency_service.delete(dependency.id)

        assert await dependency_service.list_for_plugin(plugin_a.id) == []


class TestResolveInstallOrder:
    async def test_resolve_install_order_across_diamond_graph(
        self,
        dependency_service: PluginDependencyService,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        # D depends on B and C; both B and C depend on A. A must therefore
        # install before B and C, and both of those before D.
        plugin_a = await make_plugin(slug="dep-order-a")
        plugin_b = await make_plugin(slug="dep-order-b")
        plugin_c = await make_plugin(slug="dep-order-c")
        plugin_d = await make_plugin(slug="dep-order-d")

        await dependency_service.declare(
            organization_id, plugin_b.id, depends_on_plugin_id=plugin_a.id
        )
        await dependency_service.declare(
            organization_id, plugin_c.id, depends_on_plugin_id=plugin_a.id
        )
        await dependency_service.declare(
            organization_id, plugin_d.id, depends_on_plugin_id=plugin_b.id
        )
        await dependency_service.declare(
            organization_id, plugin_d.id, depends_on_plugin_id=plugin_c.id
        )

        order = await dependency_service.resolve_install_order(organization_id)

        assert order.index(plugin_a.id) < order.index(plugin_b.id)
        assert order.index(plugin_a.id) < order.index(plugin_c.id)
        assert order.index(plugin_b.id) < order.index(plugin_d.id)
        assert order.index(plugin_c.id) < order.index(plugin_d.id)

    async def test_resolve_install_order_empty_graph(
        self, dependency_service: PluginDependencyService, organization_id: uuid.UUID
    ) -> None:
        assert await dependency_service.resolve_install_order(organization_id) == []

    async def test_resolve_install_order_propagates_circular_dependency_error(
        self,
        dependency_service: PluginDependencyService,
        dependencies_repo: PluginDependencyRepository,
        make_plugin: Callable[..., Awaitable[Any]],
        organization_id: uuid.UUID,
    ) -> None:
        """``declare`` fully guards against cycles, so the only way to
        exercise ``resolve_install_order``'s own ``CircularDependencyError``
        propagation is to write both edges of a cycle directly through the
        repository, bypassing the service's own guard entirely -- the same
        state a corrupted or manually-edited row would produce.
        """
        plugin_a = await make_plugin(slug="dep-realcycle-a")
        plugin_b = await make_plugin(slug="dep-realcycle-b")

        await dependencies_repo.create(
            PluginDependency(
                organization_id=organization_id,
                plugin_id=plugin_a.id,
                depends_on_plugin_id=plugin_b.id,
            )
        )
        await dependencies_repo.create(
            PluginDependency(
                organization_id=organization_id,
                plugin_id=plugin_b.id,
                depends_on_plugin_id=plugin_a.id,
            )
        )

        with pytest.raises(CircularDependencyError):
            await dependency_service.resolve_install_order(organization_id)
