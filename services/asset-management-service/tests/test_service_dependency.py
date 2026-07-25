"""Tests for :class:`app.services.dependency.DependencyService`, against
a real Neo4j graph seeded with :func:`tests.conftest.seed_dependency_graph`.
"""

from __future__ import annotations

import uuid

from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.graph_client import DependencyGraphClient
from app.repositories.asset_dependency_analysis import AssetDependencyAnalysisRepository
from app.repositories.managed_asset import ManagedAssetRepository
from app.services.dependency import DependencyService
from tests.conftest import make_managed_asset, seed_dependency_graph


def _build(db_session: AsyncSession, graph: DependencyGraphClient) -> DependencyService:
    return DependencyService(
        AssetDependencyAnalysisRepository(db_session), ManagedAssetRepository(db_session), graph
    )


async def test_analyze_computes_and_caches(
    db_session: AsyncSession,
    real_neo4j_driver: AsyncDriver,
    dependency_graph_client: DependencyGraphClient,
) -> None:
    web_id = uuid.uuid4()
    api_id = uuid.uuid4()
    db_id = uuid.uuid4()
    await seed_dependency_graph(
        real_neo4j_driver,
        [(web_id, "DEPENDS_ON", api_id), (api_id, "DEPENDS_ON", db_id)],
    )

    managed_asset = await make_managed_asset(db_session, inventory_asset_id=api_id)
    service = _build(db_session, dependency_graph_client)

    analysis, snapshot = await service.analyze(managed_asset.id)

    assert analysis.dependency_count == 1  # api depends_on db
    assert analysis.dependent_count == 1  # web depends_on api
    assert analysis.blast_radius_count == 1
    assert len(snapshot["root_cause_candidates"]) == 1

    cached = await service.get_cached(managed_asset.id)
    assert cached is not None
    assert cached.id == analysis.id


async def test_analyze_twice_updates_existing_cache_row(
    db_session: AsyncSession,
    real_neo4j_driver: AsyncDriver,
    dependency_graph_client: DependencyGraphClient,
) -> None:
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    await seed_dependency_graph(real_neo4j_driver, [(source_id, "RUNS_ON", target_id)])

    managed_asset = await make_managed_asset(db_session, inventory_asset_id=source_id)
    service = _build(db_session, dependency_graph_client)

    first, _ = await service.analyze(managed_asset.id)
    second, _ = await service.analyze(managed_asset.id)

    assert first.id == second.id


async def test_analyze_no_dependencies(
    db_session: AsyncSession, dependency_graph_client: DependencyGraphClient
) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session, dependency_graph_client)

    analysis, snapshot = await service.analyze(managed_asset.id)

    assert analysis.dependency_count == 0
    assert snapshot["dependency_graph"] == []
