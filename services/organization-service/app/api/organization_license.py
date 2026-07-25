"""``/organizations/{id}/licenses``. Per docs/033 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, LicenseSvc, require_admin, require_member
from app.models.organization_license import OrganizationLicense
from app.schemas.organization_license import (
    OrganizationLicenseResponse,
    OrganizationLicenseUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(
    prefix="/organizations/{organization_id}/licenses", tags=["Organization Licenses"]
)


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(license_: OrganizationLicense) -> OrganizationLicenseResponse:
    return OrganizationLicenseResponse(
        id=license_.id,
        organization_id=license_.organization_id,
        license_type=license_.license_type,
        license_key=license_.license_key,
        seat_count=license_.seat_count,
        consumed_seats=license_.consumed_seats,
        status=license_.status,
        activated_at=license_.activated_at,
        expires_at=license_.expires_at,
        grace_period_days=license_.grace_period_days,
        created_at=license_.created_at,
        updated_at=license_.updated_at,
    )


@router.get(
    "",
    response_model=SuccessResponse[OrganizationLicenseResponse],
    dependencies=[Depends(require_member)],
)
async def get_license(
    organization_id: UUID, licenses: LicenseSvc, _caller: CurrentUserId
) -> SuccessResponse[OrganizationLicenseResponse]:
    """Return an organization's license, creating a pending one if missing."""
    record = await licenses.get_or_create(organization_id)
    return SuccessResponse(message="License retrieved.", data=_to_response(record), meta=_meta())


@router.put(
    "",
    response_model=SuccessResponse[OrganizationLicenseResponse],
    dependencies=[Depends(require_admin)],
)
async def update_license(
    organization_id: UUID, body: OrganizationLicenseUpdateRequest, licenses: LicenseSvc
) -> SuccessResponse[OrganizationLicenseResponse]:
    """Update an organization's license ("License Changes")."""
    record = await licenses.update(
        organization_id,
        license_type=body.license_type,
        license_key=body.license_key,
        seat_count=body.seat_count,
        expires_at=body.expires_at,
        grace_period_days=body.grace_period_days,
    )
    return SuccessResponse(message="License updated.", data=_to_response(record), meta=_meta())


__all__ = ["router"]
