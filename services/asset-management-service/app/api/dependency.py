"""``GET /assets/{id}/dependencies``. Per docs/038 REST list."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, DependencySvc, ManagedAssetSvc
from app.schemas.dependency import AssetDependencyResponse, DependencyGraphNode
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/assets", tags=["Dependencies"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _nodes(records: list[dict[str, Any]]) -> list[DependencyGraphNode]:
    return [
        DependencyGraphNode(
            id=str(record["id"]),
            name=str(record["name"]) if record.get("name") is not None else None,
            asset_type=(
                str(record["asset_type"]) if record.get("asset_type") is not None else None
            ),
            distance=int(record.get("distance", 0)),
        )
        for record in records
    ]


@router.get(
    "/{managed_asset_id}/dependencies", response_model=SuccessResponse[AssetDependencyResponse]
)
async def get_dependencies(
    managed_asset_id: UUID,
    dependencies: DependencySvc,
    managed_assets: ManagedAssetSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[AssetDependencyResponse]:
    """Run a live dependency analysis for a managed asset ("Impact
    Analysis", "Dependency Graph", "Blast Radius Analysis", "Root Cause
    Relationships").
    """
    managed_asset = await managed_assets.get_by_id(managed_asset_id)
    analysis, snapshot = await dependencies.analyze(managed_asset_id)
    data = AssetDependencyResponse(
        managed_asset_id=analysis.managed_asset_id,
        inventory_asset_id=managed_asset.inventory_asset_id,
        dependency_graph=_nodes(snapshot["dependency_graph"]),
        impact_analysis=_nodes(snapshot["impact_analysis"]),
        blast_radius=_nodes(snapshot["blast_radius"]),
        root_cause_candidates=_nodes(snapshot["root_cause_candidates"]),
        computed_at=analysis.computed_at,
    )
    return SuccessResponse(message="Dependency analysis computed.", data=data, meta=_meta())


__all__ = ["get_dependencies", "router"]
