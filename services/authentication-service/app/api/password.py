"""POST /auth/{forgot-password,reset-password}."""

from __future__ import annotations

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AuthSvc
from app.schemas.password import ForgotPasswordRequest, ResetPasswordRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/auth", tags=["Password"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post("/forgot-password", response_model=SuccessResponse[dict[str, bool]])
async def forgot_password(
    body: ForgotPasswordRequest, auth: AuthSvc
) -> SuccessResponse[dict[str, bool]]:
    """Request a password reset. Always succeeds, whether or not the email is registered."""
    await auth.forgot_password(body.email)
    return SuccessResponse(
        message="If that email is registered, a reset link has been sent.",
        data={"success": True},
        meta=_meta(),
    )


@router.post("/reset-password", response_model=SuccessResponse[dict[str, bool]])
async def reset_password(
    body: ResetPasswordRequest, auth: AuthSvc
) -> SuccessResponse[dict[str, bool]]:
    """Complete a password reset using a token from the "forgot password" email."""
    await auth.reset_password(token=body.token, new_password=body.new_password)
    return SuccessResponse(message="Password has been reset.", data={"success": True}, meta=_meta())


__all__ = ["router"]
