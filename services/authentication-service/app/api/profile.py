"""GET /auth/profile."""

from __future__ import annotations

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUser, MfaSvc
from app.schemas.profile import ProfileResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/auth", tags=["Profile"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("/profile", response_model=SuccessResponse[ProfileResponse])
async def profile(user: CurrentUser, mfa: MfaSvc) -> SuccessResponse[ProfileResponse]:
    """Return the authenticated caller's own profile."""
    data = ProfileResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_email_verified=user.is_email_verified,
        mfa_enabled=await mfa.has_verified_device(user.id),
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )
    return SuccessResponse(message="Profile retrieved.", data=data, meta=_meta())


__all__ = ["router"]
