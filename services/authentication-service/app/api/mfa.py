"""POST /auth/mfa/{enable,disable,verify}."""

from __future__ import annotations

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AuthSvc, CurrentUser
from app.schemas.mfa import MfaDisableRequest, MfaEnableResponse, MfaVerifyRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/auth/mfa", tags=["MFA"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post("/enable", response_model=SuccessResponse[MfaEnableResponse])
async def enable(user: CurrentUser, auth: AuthSvc) -> SuccessResponse[MfaEnableResponse]:
    """Enroll a new TOTP device (not yet enforced until confirmed via ``/auth/mfa/verify``)."""
    device, otpauth_uri, recovery_codes = await auth.enable_mfa(user)
    data = MfaEnableResponse(
        secret=device.secret, otpauth_uri=otpauth_uri, recovery_codes=recovery_codes
    )
    return SuccessResponse(
        message="Scan the QR code, then confirm with a code via /auth/mfa/verify.",
        data=data,
        meta=_meta(),
    )


@router.post("/verify", response_model=SuccessResponse[dict[str, bool]])
async def verify(
    body: MfaVerifyRequest, user: CurrentUser, auth: AuthSvc
) -> SuccessResponse[dict[str, bool]]:
    """Confirm a just-enrolled TOTP device, enforcing MFA on future logins."""
    await auth.confirm_mfa(user, body.code)
    return SuccessResponse(message="MFA enabled.", data={"success": True}, meta=_meta())


@router.post("/disable", response_model=SuccessResponse[dict[str, bool]])
async def disable(
    body: MfaDisableRequest, user: CurrentUser, auth: AuthSvc
) -> SuccessResponse[dict[str, bool]]:
    """Disable MFA, requiring a valid code first."""
    await auth.disable_mfa(user, body.code)
    return SuccessResponse(message="MFA disabled.", data={"success": True}, meta=_meta())


__all__ = ["router"]
