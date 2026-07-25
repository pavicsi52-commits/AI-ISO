"""``/organizations/{id}/branding``. Per docs/033 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import BrandingSvc, CurrentUserId, require_admin, require_member
from app.models.organization_branding import OrganizationBranding
from app.schemas.organization_branding import (
    OrganizationBrandingResponse,
    OrganizationBrandingUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(
    prefix="/organizations/{organization_id}/branding", tags=["Organization Branding"]
)


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(branding: OrganizationBranding) -> OrganizationBrandingResponse:
    return OrganizationBrandingResponse(
        id=branding.id,
        organization_id=branding.organization_id,
        logo_url=branding.logo_url,
        dark_logo_url=branding.dark_logo_url,
        favicon_url=branding.favicon_url,
        primary_color=branding.primary_color,
        secondary_color=branding.secondary_color,
        theme=branding.theme,
        email_templates=branding.email_templates,
        login_screen_branding=branding.login_screen_branding,
        dashboard_branding=branding.dashboard_branding,
        created_at=branding.created_at,
        updated_at=branding.updated_at,
    )


@router.get(
    "",
    response_model=SuccessResponse[OrganizationBrandingResponse],
    dependencies=[Depends(require_member)],
)
async def get_branding(
    organization_id: UUID, branding: BrandingSvc, _caller: CurrentUserId
) -> SuccessResponse[OrganizationBrandingResponse]:
    """Return an organization's branding, creating defaults if missing."""
    record = await branding.get_or_create(organization_id)
    return SuccessResponse(message="Branding retrieved.", data=_to_response(record), meta=_meta())


@router.put(
    "",
    response_model=SuccessResponse[OrganizationBrandingResponse],
    dependencies=[Depends(require_admin)],
)
async def update_branding(
    organization_id: UUID, body: OrganizationBrandingUpdateRequest, branding: BrandingSvc
) -> SuccessResponse[OrganizationBrandingResponse]:
    """Update an organization's branding ("Branding Changes")."""
    record = await branding.update(
        organization_id,
        logo_url=body.logo_url,
        dark_logo_url=body.dark_logo_url,
        favicon_url=body.favicon_url,
        primary_color=body.primary_color,
        secondary_color=body.secondary_color,
        theme=body.theme,
        email_templates=body.email_templates,
        login_screen_branding=body.login_screen_branding,
        dashboard_branding=body.dashboard_branding,
    )
    return SuccessResponse(message="Branding updated.", data=_to_response(record), meta=_meta())


__all__ = ["router"]
