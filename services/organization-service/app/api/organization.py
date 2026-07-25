"""``/organizations``. Per docs/033 REST list.

``POST /organizations`` requires only authentication -- there is no
existing membership to check for a brand-new organization (the same
bootstrap problem ``services/rbac-service``'s own guard docstring
discusses for its first Platform Administrator), so any authenticated
caller may create one, automatically becoming its owner. Every other
mutation requires the caller hold at least the admin role in the
target organization (:func:`app.api.deps.require_admin`).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, MemberSvc, OrgSvc, require_admin
from app.models.enums import MemberRole
from app.models.organization import Organization
from app.schemas.organization import (
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/organizations", tags=["Organizations"])

_RequireAdmin = Depends(require_admin)


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(organization: Organization) -> OrganizationResponse:
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        display_name=organization.display_name,
        short_name=organization.short_name,
        slug=organization.slug,
        description=organization.description,
        status=organization.status,
        primary_domain=organization.primary_domain,
        primary_contact_email=organization.primary_contact_email,
        logo_url=organization.logo_url,
        website=organization.website,
        industry=organization.industry,
        timezone=organization.timezone,
        language=organization.language,
        country=organization.country,
        currency=organization.currency,
        metadata=organization.metadata_,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[OrganizationResponse]])
async def list_organizations(
    organizations: OrgSvc, _caller: CurrentUserId
) -> SuccessResponse[list[OrganizationResponse]]:
    """List every organization ("Organization Management")."""
    records = await organizations.list_all()
    return SuccessResponse(
        message="Organizations retrieved.", data=[_to_response(o) for o in records], meta=_meta()
    )


@router.get("/{organization_id}", response_model=SuccessResponse[OrganizationResponse])
async def get_organization(
    organization_id: UUID, organizations: OrgSvc, _caller: CurrentUserId
) -> SuccessResponse[OrganizationResponse]:
    """Return one organization."""
    organization = await organizations.get_by_id(organization_id)
    return SuccessResponse(
        message="Organization retrieved.", data=_to_response(organization), meta=_meta()
    )


@router.post("", response_model=SuccessResponse[OrganizationResponse], status_code=201)
async def create_organization(
    body: OrganizationCreateRequest,
    organizations: OrgSvc,
    members: MemberSvc,
    caller: CurrentUserId,
) -> SuccessResponse[OrganizationResponse]:
    """Create a new organization ("Create"). The caller becomes its owner."""
    organization = await organizations.create(
        name=body.name,
        slug=body.slug,
        display_name=body.display_name,
        short_name=body.short_name,
        description=body.description,
        primary_domain=body.primary_domain,
        primary_contact_email=body.primary_contact_email,
        website=body.website,
        industry=body.industry,
        timezone=body.timezone,
        language=body.language,
        country=body.country,
        currency=body.currency,
        metadata=body.metadata,
    )
    await members.add(organization.id, caller, role=MemberRole.OWNER)
    return SuccessResponse(
        message="Organization created.", data=_to_response(organization), meta=_meta()
    )


@router.put(
    "/{organization_id}",
    response_model=SuccessResponse[OrganizationResponse],
    dependencies=[_RequireAdmin],
)
async def update_organization(
    organization_id: UUID, body: OrganizationUpdateRequest, organizations: OrgSvc
) -> SuccessResponse[OrganizationResponse]:
    """Replace an organization's mutable fields ("Update")."""
    organization = await organizations.update(
        organization_id,
        name=body.name,
        display_name=body.display_name,
        short_name=body.short_name,
        description=body.description,
        status=body.status,
        primary_domain=body.primary_domain,
        primary_contact_email=body.primary_contact_email,
        logo_url=body.logo_url,
        website=body.website,
        industry=body.industry,
        timezone=body.timezone,
        language=body.language,
        country=body.country,
        currency=body.currency,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Organization updated.", data=_to_response(organization), meta=_meta()
    )


@router.delete(
    "/{organization_id}",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[_RequireAdmin],
)
async def delete_organization(
    organization_id: UUID, organizations: OrgSvc
) -> SuccessResponse[dict[str, bool]]:
    """Delete an organization ("Delete")."""
    await organizations.delete(organization_id)
    return SuccessResponse(message="Organization deleted.", data={"success": True}, meta=_meta())


__all__ = ["router"]
