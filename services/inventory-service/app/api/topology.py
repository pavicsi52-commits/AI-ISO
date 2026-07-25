"""``GET /inventory/topology``. Per docs/036 "TOPOLOGY": Dependency
Graph, Relationship Traversal, Impact Analysis.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import AssetSvc, CurrentUserId, TopologySvc
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.topology import TopologyNode, TopologyResponse

router = APIRouter(prefix="/inventory/topology", tags=["Topology"])

_QueryKind = Literal["neighbors", "dependencies", "impact"]


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_node(raw: dict[str, object]) -> TopologyNode:
    distance = raw.get("distance")
    return TopologyNode(
        id=UUID(str(raw["id"])),
        name=str(raw["name"]),
        asset_type=str(raw["asset_type"]),
        distance=int(str(distance)) if distance is not None else None,
        relationship_type=(
            str(raw["relationship_type"]) if raw.get("relationship_type") is not None else None
        ),
        outgoing=bool(raw["outgoing"]) if raw.get("outgoing") is not None else None,
    )


@router.get("", response_model=SuccessResponse[TopologyResponse])
async def get_topology(
    asset_id: Annotated[UUID, Query()],
    assets: AssetSvc,
    topology: TopologySvc,
    _caller: CurrentUserId,
    query_kind: Annotated[_QueryKind, Query()] = "neighbors",
    depth: Annotated[int, Query(ge=1, le=5)] = 2,
) -> SuccessResponse[TopologyResponse]:
    """Traverse *asset_id*'s topology ("Dependency Graph", "Relationship
    Traversal", "Impact Analysis").

    Raises:
        NotFoundError: If no such asset exists.
    """
    asset = await assets.get_by_id(asset_id)
    if query_kind == "dependencies":
        nodes = await topology.get_dependency_graph(
            asset_id, organization_id=asset.organization_id, depth=depth
        )
    elif query_kind == "impact":
        nodes = await topology.get_impact_analysis(
            asset_id, organization_id=asset.organization_id, depth=depth
        )
    else:
        nodes = await topology.get_neighbors(asset_id, organization_id=asset.organization_id)

    data = TopologyResponse(
        root_asset_id=asset_id, query_kind=query_kind, nodes=[_to_node(node) for node in nodes]
    )
    return SuccessResponse(message="Topology retrieved.", data=data, meta=_meta())


__all__ = ["router"]
