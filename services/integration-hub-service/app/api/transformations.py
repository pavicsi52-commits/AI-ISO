"""Connector transformation rules (docs/058 "DATA TRANSFORMATION")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import ConnectorSvc, TransformationSvc
from app.schemas.hub import (
    TransformationApplyRequest,
    TransformationCreateRequest,
    TransformationResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.transformations import engine as transformations_engine

router = APIRouter(prefix="/integrations/transformations", tags=["Transformations"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "",
    response_model=SuccessResponse[list[TransformationResponse]],
    summary="List a connector's own rules",
)
async def list_transformations(
    organization_id: UUID,
    connector_id: UUID,
    connectors: ConnectorSvc,
    transformations: TransformationSvc,
) -> SuccessResponse[list[TransformationResponse]]:
    """Every transformation rule attached to one connector in this org, in priority order."""
    await connectors.get(organization_id, connector_id)
    rows = await transformations.list_for_connector(connector_id)
    return SuccessResponse(
        message="Transformations listed.",
        data=[TransformationResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "",
    response_model=SuccessResponse[TransformationResponse],
    status_code=201,
    summary="Create a rule",
)
async def create_transformation(
    organization_id: UUID,
    body: TransformationCreateRequest,
    connectors: ConnectorSvc,
    transformations: TransformationSvc,
) -> SuccessResponse[TransformationResponse]:
    """Register a new transformation rule.

    Confirms *body.connector_id* actually belongs to *organization_id*
    first (docs/058 "SECURITY": organization isolation).
    """
    await connectors.get(organization_id, body.connector_id)
    created = await transformations.create(
        organization_id,
        connector_id=body.connector_id,
        name=body.name,
        kind=body.kind,
        source_format=body.source_format,
        target_format=body.target_format,
        config=body.config,
        priority=body.priority,
    )
    return SuccessResponse(
        message="Transformation created.",
        data=TransformationResponse.model_validate(created),
        meta=_meta(),
    )


@router.post(
    "/{transformation_id}/apply",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Apply one rule to sample data",
)
async def apply_transformation(
    organization_id: UUID,
    transformation_id: UUID,
    body: TransformationApplyRequest,
    transformations: TransformationSvc,
) -> SuccessResponse[dict[str, Any]]:
    """Preview one transformation rule against caller-supplied sample data."""
    rule = await transformations.get(organization_id, transformation_id)
    result = transformations_engine.apply_transformation(
        body.data, kind=rule.kind, config=rule.config
    )
    return SuccessResponse(message="Transformation applied.", data={"result": result}, meta=_meta())


__all__ = ["router"]
