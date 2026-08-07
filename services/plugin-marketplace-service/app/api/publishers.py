"""Publisher profile management and trust (docs/059 "PUBLISHERS", extension surface)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, PublisherSvc
from app.schemas.marketplace import (
    PluginPublisherRegisterRequest,
    PluginPublisherResponse,
    PluginPublisherTrustKeyRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/plugins/publishers", tags=["Publishers"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "", response_model=SuccessResponse[list[PluginPublisherResponse]], summary="List publishers"
)
async def list_publishers(
    organization_id: UUID, publishers: PublisherSvc
) -> SuccessResponse[list[PluginPublisherResponse]]:
    """Every publisher profile registered in this organization."""
    rows = await publishers.list_for_org(organization_id)
    return SuccessResponse(
        message="Publishers listed.",
        data=[PluginPublisherResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/{publisher_id}",
    response_model=SuccessResponse[PluginPublisherResponse],
    summary="Get a publisher",
)
async def get_publisher(
    organization_id: UUID, publisher_id: UUID, publishers: PublisherSvc
) -> SuccessResponse[PluginPublisherResponse]:
    """One publisher."""
    found = await publishers.get(organization_id, publisher_id)
    return SuccessResponse(
        message="Publisher found.", data=PluginPublisherResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[PluginPublisherResponse],
    status_code=201,
    summary="Register a publisher",
)
async def register_publisher(
    organization_id: UUID, body: PluginPublisherRegisterRequest, publishers: PublisherSvc
) -> SuccessResponse[PluginPublisherResponse]:
    """Register a new publisher profile."""
    created = await publishers.register(
        organization_id,
        slug=body.slug,
        display_name=body.display_name,
        publisher_type=body.publisher_type,
        contact_email=body.contact_email,
        website_url=body.website_url,
        bio=body.bio,
    )
    return SuccessResponse(
        message="Publisher registered.",
        data=PluginPublisherResponse.model_validate(created),
        meta=_meta(),
    )


@router.post(
    "/{publisher_id}/verification-requests",
    response_model=SuccessResponse[PluginPublisherResponse],
    status_code=201,
    summary="Request publisher verification",
)
async def request_verification(
    organization_id: UUID, publisher_id: UUID, publishers: PublisherSvc
) -> SuccessResponse[PluginPublisherResponse]:
    """Move a publisher into pending verification."""
    updated = await publishers.request_verification(organization_id, publisher_id)
    return SuccessResponse(
        message="Verification requested.",
        data=PluginPublisherResponse.model_validate(updated),
        meta=_meta(),
    )


@router.post(
    "/{publisher_id}/verify",
    response_model=SuccessResponse[PluginPublisherResponse],
    summary="Verify a publisher",
)
async def verify_publisher(
    organization_id: UUID, publisher_id: UUID, publishers: PublisherSvc, caller: CurrentUserId
) -> SuccessResponse[PluginPublisherResponse]:
    """Mark a publisher verified."""
    updated = await publishers.verify(organization_id, publisher_id, verified_by=str(caller))
    return SuccessResponse(
        message="Publisher verified.",
        data=PluginPublisherResponse.model_validate(updated),
        meta=_meta(),
    )


@router.post(
    "/{publisher_id}/revoke-verification",
    response_model=SuccessResponse[PluginPublisherResponse],
    summary="Revoke a publisher's own verification",
)
async def revoke_verification(
    organization_id: UUID, publisher_id: UUID, publishers: PublisherSvc
) -> SuccessResponse[PluginPublisherResponse]:
    """Revoke a publisher's own verified status."""
    updated = await publishers.revoke_verification(organization_id, publisher_id)
    return SuccessResponse(
        message="Verification revoked.",
        data=PluginPublisherResponse.model_validate(updated),
        meta=_meta(),
    )


@router.put(
    "/{publisher_id}/trusted-signing-key",
    response_model=SuccessResponse[PluginPublisherResponse],
    summary="Set a publisher's own trusted signing key",
)
async def set_trusted_signing_key(
    organization_id: UUID,
    publisher_id: UUID,
    body: PluginPublisherTrustKeyRequest,
    publishers: PublisherSvc,
) -> SuccessResponse[PluginPublisherResponse]:
    """Register the Ed25519 public key this publisher's packages must be signed with."""
    updated = await publishers.set_trusted_signing_key(
        organization_id, publisher_id, public_key_pem=body.public_key_pem
    )
    return SuccessResponse(
        message="Trusted signing key set.",
        data=PluginPublisherResponse.model_validate(updated),
        meta=_meta(),
    )


__all__ = ["router"]
