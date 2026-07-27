"""``/validation-profiles``. Per docs/043 REST list.

A lighter list/create surface over the identical
:class:`~app.models.validation_profile.ValidationProfile` resource
``app/api/validations.py``'s own ``/validations`` router already fronts
in full -- see that module's own docstring for why both literal paths
exist without inventing two different underlying resource types.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ProfileSvc
from app.api.validations import profile_to_response
from app.schemas.profile import ValidationProfileCreateRequest, ValidationProfileResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/validation-profiles", tags=["Validation Profiles"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[ValidationProfileResponse]])
async def list_validation_profiles(
    organization_id: UUID, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ValidationProfileResponse]]:
    """List every validation profile in *organization_id*."""
    records = await profiles.list_for_org(organization_id)
    data = [profile_to_response(record) for record in records]
    return SuccessResponse(message="Validation profiles retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[ValidationProfileResponse], status_code=201)
async def create_validation_profile(
    body: ValidationProfileCreateRequest, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationProfileResponse]:
    """Create a new validation profile ("Create")."""
    profile = await profiles.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        profile_type=body.profile_type,
        target_types=body.target_types,
        check_ids=body.check_ids,
        concurrency_strategy=body.concurrency_strategy,
        scoring_weights=body.scoring_weights,
        tags=body.tags,
        owner=body.owner,
    )
    return SuccessResponse(
        message="Validation profile created.", data=profile_to_response(profile), meta=_meta()
    )


__all__ = ["router"]
