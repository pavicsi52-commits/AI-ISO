"""``/inventory/assets``. Per docs/036 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AssetSvc, CurrentUserId, TagSvc
from app.models.asset import Asset
from app.schemas.asset import (
    AssetCreateRequest,
    AssetPatchRequest,
    AssetResponse,
    AssetUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/inventory/assets", tags=["Assets"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


async def asset_to_response(asset: Asset, tags: TagSvc) -> AssetResponse:
    labels = [tag.label for tag in await tags.list_for_asset(asset.id)]
    return AssetResponse(
        id=asset.id,
        organization_id=asset.organization_id,
        project_id=asset.project_id,
        name=asset.name,
        display_name=asset.display_name,
        hostname=asset.hostname,
        fqdn=asset.fqdn,
        ip_address=asset.ip_address,
        mac_address=asset.mac_address,
        serial_number=asset.serial_number,
        vendor=asset.vendor,
        manufacturer=asset.manufacturer,
        model=asset.model,
        firmware_version=asset.firmware_version,
        operating_system=asset.operating_system,
        architecture=asset.architecture,
        environment=asset.environment,
        asset_type=asset.asset_type,
        category_id=asset.category_id,
        class_id=asset.class_id,
        location_id=asset.location_id,
        owner_id=asset.owner_id,
        status=asset.status,
        health=asset.health,
        lifecycle_state=asset.lifecycle_state,
        criticality=asset.criticality,
        current_version=asset.current_version,
        metadata=asset.metadata_,
        tags=labels,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[AssetResponse]])
async def list_assets(
    organization_id: UUID, assets: AssetSvc, tags: TagSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AssetResponse]]:
    """List every asset in *organization_id* ("Inventory CRUD")."""
    records = await assets.list_for_org(organization_id)
    data = [await asset_to_response(asset, tags) for asset in records]
    return SuccessResponse(message="Assets retrieved.", data=data, meta=_meta())


@router.get("/{asset_id}", response_model=SuccessResponse[AssetResponse])
async def get_asset(
    asset_id: UUID, assets: AssetSvc, tags: TagSvc, _caller: CurrentUserId
) -> SuccessResponse[AssetResponse]:
    """Return one asset.

    Raises:
        NotFoundError: If no such asset exists.
    """
    asset = await assets.get_by_id(asset_id)
    return SuccessResponse(
        message="Asset retrieved.", data=await asset_to_response(asset, tags), meta=_meta()
    )


@router.post("", response_model=SuccessResponse[AssetResponse], status_code=201)
async def create_asset(
    body: AssetCreateRequest, assets: AssetSvc, tags: TagSvc, caller: CurrentUserId
) -> SuccessResponse[AssetResponse]:
    """Register a new asset ("Create").

    Raises:
        ConflictError: If *hostname*, *serial_number*, or *mac_address*
            is already registered within *organization_id* ("Prevent
            duplicate identifiers").
    """
    asset = await assets.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        display_name=body.display_name,
        hostname=body.hostname,
        fqdn=body.fqdn,
        ip_address=body.ip_address,
        mac_address=body.mac_address,
        serial_number=body.serial_number,
        vendor=body.vendor,
        manufacturer=body.manufacturer,
        model=body.model,
        firmware_version=body.firmware_version,
        operating_system=body.operating_system,
        architecture=body.architecture,
        environment=body.environment,
        asset_type=body.asset_type,
        category_id=body.category_id,
        class_id=body.class_id,
        location_id=body.location_id,
        owner_id=body.owner_id,
        criticality=body.criticality,
        metadata=body.metadata,
        tags=body.tags,
        created_by=caller,
    )
    return SuccessResponse(
        message="Asset created.", data=await asset_to_response(asset, tags), meta=_meta()
    )


@router.put("/{asset_id}", response_model=SuccessResponse[AssetResponse])
async def update_asset(
    asset_id: UUID,
    body: AssetUpdateRequest,
    assets: AssetSvc,
    tags: TagSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AssetResponse]:
    """Replace an asset's mutable fields ("Update")."""
    asset = await assets.update(
        asset_id,
        actor_id=caller,
        name=body.name,
        display_name=body.display_name,
        hostname=body.hostname,
        fqdn=body.fqdn,
        ip_address=body.ip_address,
        mac_address=body.mac_address,
        serial_number=body.serial_number,
        vendor=body.vendor,
        manufacturer=body.manufacturer,
        model=body.model,
        firmware_version=body.firmware_version,
        operating_system=body.operating_system,
        architecture=body.architecture,
        environment=body.environment,
        category_id=body.category_id,
        class_id=body.class_id,
        location_id=body.location_id,
        owner_id=body.owner_id,
        status=body.status,
        health=body.health,
        lifecycle_state=body.lifecycle_state,
        criticality=body.criticality,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Asset updated.", data=await asset_to_response(asset, tags), meta=_meta()
    )


@router.patch("/{asset_id}", response_model=SuccessResponse[AssetResponse])
async def patch_asset(
    asset_id: UUID,
    body: AssetPatchRequest,
    assets: AssetSvc,
    tags: TagSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AssetResponse]:
    """Update only the given fields of an asset ("PATCH partial update")."""
    current = await assets.get_by_id(asset_id)
    patch = body.model_dump(exclude_unset=True)
    asset = await assets.update(
        asset_id,
        actor_id=caller,
        name=patch.get("name", current.name),
        display_name=patch.get("display_name", current.display_name),
        hostname=patch.get("hostname", current.hostname),
        fqdn=patch.get("fqdn", current.fqdn),
        ip_address=patch.get("ip_address", current.ip_address),
        mac_address=patch.get("mac_address", current.mac_address),
        serial_number=patch.get("serial_number", current.serial_number),
        vendor=patch.get("vendor", current.vendor),
        manufacturer=patch.get("manufacturer", current.manufacturer),
        model=patch.get("model", current.model),
        firmware_version=patch.get("firmware_version", current.firmware_version),
        operating_system=patch.get("operating_system", current.operating_system),
        architecture=patch.get("architecture", current.architecture),
        environment=patch.get("environment", current.environment),
        category_id=patch.get("category_id", current.category_id),
        class_id=patch.get("class_id", current.class_id),
        location_id=patch.get("location_id", current.location_id),
        owner_id=patch.get("owner_id", current.owner_id),
        status=patch.get("status", current.status),
        health=patch.get("health", current.health),
        lifecycle_state=patch.get("lifecycle_state", current.lifecycle_state),
        criticality=patch.get("criticality", current.criticality),
        metadata=patch.get("metadata", current.metadata_),
    )
    return SuccessResponse(
        message="Asset updated.", data=await asset_to_response(asset, tags), meta=_meta()
    )


@router.delete("/{asset_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_asset(
    asset_id: UUID, assets: AssetSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Soft-delete an asset ("Deletion")."""
    await assets.delete(asset_id, actor_id=caller)
    return SuccessResponse(message="Asset deleted.", data={"success": True}, meta=_meta())


__all__ = ["asset_to_response", "router"]
