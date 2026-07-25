"""GET/PUT ``/users/profile`` -- the authenticated caller's own extended profile.

Self-scoped like docs/031's explicit ``/users/preferences``,
``/users/avatar``, ``/users/activity``, ``/users/tags`` endpoints
(the caller's identity, resolved from the Bearer token, *is* the
target -- no ``{user_id}`` path parameter). ``app/api/note.py`` is the
one exception in this service: notes are admin/manager-authored
*about* another user, so it takes an explicit ``{user_id}``.
"""

from __future__ import annotations

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ProfileSvc
from app.models.profile import UserProfile
from app.schemas.profile import ProfileResponse, ProfileUpdateRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/users/profile", tags=["Profile"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(profile: UserProfile) -> ProfileResponse:
    return ProfileResponse(
        user_id=profile.user_id,
        biography=profile.biography,
        job_title=profile.job_title,
        department=profile.department,
        employee_id=profile.employee_id,
        manager_id=profile.manager_id,
        profile_photo=profile.profile_photo,
        custom_fields=profile.custom_fields,
    )


@router.get("", response_model=SuccessResponse[ProfileResponse])
async def get_profile(
    profiles: ProfileSvc, current_user_id: CurrentUserId
) -> SuccessResponse[ProfileResponse]:
    """Return the caller's own extended profile."""
    profile = await profiles.get_or_create(current_user_id)
    return SuccessResponse(message="Profile retrieved.", data=_to_response(profile), meta=_meta())


@router.put("", response_model=SuccessResponse[ProfileResponse])
async def update_profile(
    body: ProfileUpdateRequest, profiles: ProfileSvc, current_user_id: CurrentUserId
) -> SuccessResponse[ProfileResponse]:
    """Update the caller's own extended profile ("Profile Updates")."""
    profile = await profiles.update(
        current_user_id,
        biography=body.biography,
        job_title=body.job_title,
        department=body.department,
        employee_id=body.employee_id,
        manager_id=body.manager_id,
        custom_fields=body.custom_fields,
    )
    return SuccessResponse(message="Profile updated.", data=_to_response(profile), meta=_meta())


__all__ = ["router"]
