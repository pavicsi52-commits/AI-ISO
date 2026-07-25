"""``/assets``. Per docs/038 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import (
    CurrentUserId,
    CurrentUserToken,
    InventoryClientDep,
    ManagedAssetSvc,
)
from app.models.managed_asset import ManagedAsset
from app.schemas.managed_asset import (
    ManagedAssetCreateRequest,
    ManagedAssetPatchRequest,
    ManagedAssetResponse,
    ManagedAssetUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/assets", tags=["Managed Assets"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def managed_asset_to_response(managed_asset: ManagedAsset) -> ManagedAssetResponse:
    return ManagedAssetResponse(
        id=managed_asset.id,
        organization_id=managed_asset.organization_id,
        project_id=managed_asset.project_id,
        inventory_asset_id=managed_asset.inventory_asset_id,
        business_name=managed_asset.business_name,
        business_owner_id=managed_asset.business_owner_id,
        technical_owner_id=managed_asset.technical_owner_id,
        support_team_id=managed_asset.support_team_id,
        vendor_id=managed_asset.vendor_id,
        status=managed_asset.status,
        lifecycle_state=managed_asset.lifecycle_state,
        criticality=managed_asset.criticality,
        warranty_status=managed_asset.warranty_status,
        compliance_status=managed_asset.compliance_status,
        risk_score=float(managed_asset.risk_score),
        operational_health=managed_asset.operational_health,
        acquisition_date=managed_asset.acquisition_date,
        retirement_date=managed_asset.retirement_date,
        metadata=managed_asset.metadata_,
        tags=managed_asset.tags,
        labels=managed_asset.labels,
        created_at=managed_asset.created_at,
        updated_at=managed_asset.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[ManagedAssetResponse]])
async def list_managed_assets(
    organization_id: UUID, managed_assets: ManagedAssetSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ManagedAssetResponse]]:
    """List every managed asset in *organization_id*."""
    records = await managed_assets.list_for_org(organization_id)
    data = [managed_asset_to_response(record) for record in records]
    return SuccessResponse(message="Managed assets retrieved.", data=data, meta=_meta())


@router.get("/{managed_asset_id}", response_model=SuccessResponse[ManagedAssetResponse])
async def get_managed_asset(
    managed_asset_id: UUID, managed_assets: ManagedAssetSvc, _caller: CurrentUserId
) -> SuccessResponse[ManagedAssetResponse]:
    """Return one managed asset.

    Raises:
        NotFoundError: If no such managed asset exists.
    """
    managed_asset = await managed_assets.get_by_id(managed_asset_id)
    return SuccessResponse(
        message="Managed asset retrieved.",
        data=managed_asset_to_response(managed_asset),
        meta=_meta(),
    )


@router.post("", response_model=SuccessResponse[ManagedAssetResponse], status_code=201)
async def create_managed_asset(
    body: ManagedAssetCreateRequest,
    managed_assets: ManagedAssetSvc,
    inventory: InventoryClientDep,
    caller: CurrentUserId,
    caller_token: CurrentUserToken,
) -> SuccessResponse[ManagedAssetResponse]:
    """Bring an inventoried asset under enterprise governance ("Create").

    Raises:
        NotFoundError: If *inventory_asset_id* has no matching Inventory
            Service asset.
        ConflictError: If *inventory_asset_id* is already under management.
    """
    inventory_summary = await inventory.get_asset_summary(
        body.inventory_asset_id, caller_token=caller_token
    )
    if inventory_summary is None:
        raise NotFoundError(f"Inventory asset '{body.inventory_asset_id}' was not found.")
    managed_asset = await managed_assets.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        inventory_asset_id=body.inventory_asset_id,
        business_name=body.business_name,
        business_owner_id=body.business_owner_id,
        technical_owner_id=body.technical_owner_id,
        support_team_id=body.support_team_id,
        vendor_id=body.vendor_id,
        criticality=body.criticality,
        acquisition_date=body.acquisition_date,
        metadata=body.metadata,
        tags=body.tags,
        labels=body.labels,
        created_by=caller,
    )
    return SuccessResponse(
        message="Managed asset created.",
        data=managed_asset_to_response(managed_asset),
        meta=_meta(),
    )


@router.put("/{managed_asset_id}", response_model=SuccessResponse[ManagedAssetResponse])
async def update_managed_asset(
    managed_asset_id: UUID,
    body: ManagedAssetUpdateRequest,
    managed_assets: ManagedAssetSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ManagedAssetResponse]:
    """Replace a managed asset's mutable fields ("Update")."""
    managed_asset = await managed_assets.update(
        managed_asset_id,
        actor_id=caller,
        business_name=body.business_name,
        business_owner_id=body.business_owner_id,
        technical_owner_id=body.technical_owner_id,
        support_team_id=body.support_team_id,
        vendor_id=body.vendor_id,
        status=body.status,
        lifecycle_state=body.lifecycle_state,
        criticality=body.criticality,
        acquisition_date=body.acquisition_date,
        retirement_date=body.retirement_date,
        metadata=body.metadata,
        tags=body.tags,
        labels=body.labels,
    )
    return SuccessResponse(
        message="Managed asset updated.",
        data=managed_asset_to_response(managed_asset),
        meta=_meta(),
    )


@router.patch("/{managed_asset_id}", response_model=SuccessResponse[ManagedAssetResponse])
async def patch_managed_asset(
    managed_asset_id: UUID,
    body: ManagedAssetPatchRequest,
    managed_assets: ManagedAssetSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ManagedAssetResponse]:
    """Update only the given fields of a managed asset ("PATCH partial update")."""
    current = await managed_assets.get_by_id(managed_asset_id)
    patch = body.model_dump(exclude_unset=True)
    managed_asset = await managed_assets.update(
        managed_asset_id,
        actor_id=caller,
        business_name=patch.get("business_name", current.business_name),
        business_owner_id=patch.get("business_owner_id", current.business_owner_id),
        technical_owner_id=patch.get("technical_owner_id", current.technical_owner_id),
        support_team_id=patch.get("support_team_id", current.support_team_id),
        vendor_id=patch.get("vendor_id", current.vendor_id),
        status=patch.get("status", current.status),
        lifecycle_state=patch.get("lifecycle_state", current.lifecycle_state),
        criticality=patch.get("criticality", current.criticality),
        acquisition_date=patch.get("acquisition_date", current.acquisition_date),
        retirement_date=patch.get("retirement_date", current.retirement_date),
        metadata=patch.get("metadata", current.metadata_),
        tags=patch.get("tags", current.tags),
        labels=patch.get("labels", current.labels),
    )
    return SuccessResponse(
        message="Managed asset updated.",
        data=managed_asset_to_response(managed_asset),
        meta=_meta(),
    )


@router.delete("/{managed_asset_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_managed_asset(
    managed_asset_id: UUID, managed_assets: ManagedAssetSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Soft-delete a managed asset ("Delete")."""
    await managed_assets.delete(managed_asset_id, actor_id=caller)
    return SuccessResponse(message="Managed asset deleted.", data={"success": True}, meta=_meta())


__all__ = ["managed_asset_to_response", "router"]
