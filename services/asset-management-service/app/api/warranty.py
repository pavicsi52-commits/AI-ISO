"""``/assets/{id}/warranty``. Per docs/038 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, WarrantySvc
from app.models.asset_warranty import AssetWarranty
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.warranty import AssetWarrantyResponse, AssetWarrantyUpdateRequest

router = APIRouter(prefix="/assets", tags=["Warranty"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def warranty_to_response(warranty: AssetWarranty) -> AssetWarrantyResponse:
    return AssetWarrantyResponse(
        id=warranty.id,
        managed_asset_id=warranty.managed_asset_id,
        provider=warranty.provider,
        warranty_number=warranty.warranty_number,
        coverage=warranty.coverage,
        start_date=warranty.start_date,
        end_date=warranty.end_date,
        expiration_alert_sent=warranty.expiration_alert_sent,
        renewal_status=warranty.renewal_status,
        claims=warranty.claims,
    )


@router.get("/{managed_asset_id}/warranty", response_model=SuccessResponse[AssetWarrantyResponse])
async def get_warranty(
    managed_asset_id: UUID, warranty: WarrantySvc, _caller: CurrentUserId
) -> SuccessResponse[AssetWarrantyResponse]:
    """Return a managed asset's current warranty period.

    Raises:
        NotFoundError: If no warranty period has been recorded yet.
    """
    current = await warranty.get_current(managed_asset_id)
    if current is None:
        raise NotFoundError(f"Managed asset '{managed_asset_id}' has no warranty on record.")
    return SuccessResponse(
        message="Warranty retrieved.", data=warranty_to_response(current), meta=_meta()
    )


@router.put("/{managed_asset_id}/warranty", response_model=SuccessResponse[AssetWarrantyResponse])
async def update_warranty(
    managed_asset_id: UUID,
    body: AssetWarrantyUpdateRequest,
    warranty: WarrantySvc,
    _caller: CurrentUserId,
    organization_id: UUID,
) -> SuccessResponse[AssetWarrantyResponse]:
    """Replace a managed asset's current warranty period ("Track")."""
    record = await warranty.update(
        managed_asset_id,
        organization_id=organization_id,
        provider=body.provider,
        warranty_number=body.warranty_number,
        coverage=body.coverage,
        start_date=body.start_date,
        end_date=body.end_date,
        renewal_status=body.renewal_status,
    )
    return SuccessResponse(
        message="Warranty updated.", data=warranty_to_response(record), meta=_meta()
    )


__all__ = ["router", "warranty_to_response"]
