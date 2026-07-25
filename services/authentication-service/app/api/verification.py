"""POST /auth/{verify-email,resend-verification}."""

from __future__ import annotations

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AuthSvc
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.verification import ResendVerificationRequest, VerifyEmailRequest

router = APIRouter(prefix="/auth", tags=["Verification"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post("/verify-email", response_model=SuccessResponse[dict[str, bool]])
async def verify_email(body: VerifyEmailRequest, auth: AuthSvc) -> SuccessResponse[dict[str, bool]]:
    """Verify an email address using the token from the verification email."""
    await auth.verify_email(body.token)
    return SuccessResponse(message="Email verified.", data={"success": True}, meta=_meta())


@router.post("/resend-verification", response_model=SuccessResponse[dict[str, bool]])
async def resend_verification(
    body: ResendVerificationRequest, auth: AuthSvc
) -> SuccessResponse[dict[str, bool]]:
    """Resend the email verification link. Always succeeds, whether or not the email
    is registered or already verified.
    """
    await auth.resend_verification(body.email)
    return SuccessResponse(
        message="If that email needs verification, a new link has been sent.",
        data={"success": True},
        meta=_meta(),
    )


__all__ = ["router"]
