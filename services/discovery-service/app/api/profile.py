"""``/discovery/profiles``. Per docs/037 REST list and "DISCOVERY PROFILES"."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ProfileSvc
from app.models.discovery_profile import DiscoveryProfile
from app.schemas.profile import (
    DiscoveryProfileCreateRequest,
    DiscoveryProfileResponse,
    DiscoveryProfileUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/discovery/profiles", tags=["Profiles"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(profile: DiscoveryProfile) -> DiscoveryProfileResponse:
    return DiscoveryProfileResponse(
        id=profile.id,
        organization_id=profile.organization_id,
        name=profile.name,
        description=profile.description,
        profile_type=profile.profile_type,
        protocols=profile.protocols,
        default_ports=profile.default_ports,
        timeout_seconds=profile.timeout_seconds,
        concurrency_limit=profile.concurrency_limit,
        is_system=profile.is_system,
    )


@router.get("", response_model=SuccessResponse[list[DiscoveryProfileResponse]])
async def list_profiles(
    organization_id: UUID, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[list[DiscoveryProfileResponse]]:
    """List every discovery profile defined for *organization_id*."""
    records = await profiles.list_for_org(organization_id)
    return SuccessResponse(
        message="Discovery profiles retrieved.",
        data=[_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("", response_model=SuccessResponse[DiscoveryProfileResponse], status_code=201)
async def create_profile(
    body: DiscoveryProfileCreateRequest, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[DiscoveryProfileResponse]:
    """Create a new discovery profile.

    Raises:
        ConflictError: If *name* is already taken within *organization_id*.
    """
    profile = await profiles.create(
        organization_id=body.organization_id,
        name=body.name,
        description=body.description,
        profile_type=body.profile_type,
        protocols=body.protocols,
        default_ports=body.default_ports,
        timeout_seconds=body.timeout_seconds,
        concurrency_limit=body.concurrency_limit,
    )
    return SuccessResponse(
        message="Discovery profile created.", data=_to_response(profile), meta=_meta()
    )


@router.put("/{profile_id}", response_model=SuccessResponse[DiscoveryProfileResponse])
async def update_profile(
    profile_id: UUID,
    body: DiscoveryProfileUpdateRequest,
    profiles: ProfileSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[DiscoveryProfileResponse]:
    """Replace a discovery profile's mutable fields.

    Raises:
        NotFoundError: If no such profile exists.
    """
    profile = await profiles.update(
        profile_id,
        name=body.name,
        description=body.description,
        profile_type=body.profile_type,
        protocols=body.protocols,
        default_ports=body.default_ports,
        timeout_seconds=body.timeout_seconds,
        concurrency_limit=body.concurrency_limit,
    )
    return SuccessResponse(
        message="Discovery profile updated.", data=_to_response(profile), meta=_meta()
    )


@router.delete("/{profile_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_profile(
    profile_id: UUID, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Delete a discovery profile.

    Raises:
        NotFoundError: If no such profile exists.
    """
    await profiles.delete(profile_id)
    return SuccessResponse(
        message="Discovery profile deleted.", data={"success": True}, meta=_meta()
    )


__all__ = ["router"]
