"""POST /auth/{register,login,logout,refresh}."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from shared_core.logging.context import get_log_context

from app.api.deps import AuthSvc, TokenSvc
from app.config.settings import Settings, get_settings
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MfaChallengeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserSummary,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


@router.post(
    "/register", response_model=SuccessResponse[UserSummary], status_code=201, summary="Register"
)
async def register(body: RegisterRequest, auth: AuthSvc) -> SuccessResponse[UserSummary]:
    """Register a new user with a password credential."""
    user = await auth.register(
        email=body.email, password=body.password, display_name=body.display_name
    )
    data = UserSummary(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_email_verified=user.is_email_verified,
    )
    return SuccessResponse(message="Registration successful.", data=data, meta=_meta())


@router.post("/login", response_model=SuccessResponse[TokenResponse | MfaChallengeResponse])
async def login(
    body: LoginRequest,
    request: Request,
    auth: AuthSvc,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessResponse[TokenResponse | MfaChallengeResponse]:
    """Authenticate with email and password, completing MFA if required."""
    result = await auth.login(
        email=body.email,
        password=body.password,
        mfa_code=body.mfa_code,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        device_fingerprint=body.device_fingerprint,
    )
    if result.requires_mfa:
        assert result.mfa_challenge_id is not None
        return SuccessResponse(
            message="MFA verification required.",
            data=MfaChallengeResponse(mfa_challenge_id=result.mfa_challenge_id),
            meta=_meta(),
        )
    assert result.tokens is not None
    data = TokenResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        expires_in=settings.auth.jwt_access_token_ttl_seconds,
    )
    return SuccessResponse(message="Login successful.", data=data, meta=_meta())


@router.post("/refresh", response_model=SuccessResponse[TokenResponse])
async def refresh(
    body: RefreshRequest, tokens: TokenSvc, settings: Annotated[Settings, Depends(get_settings)]
) -> SuccessResponse[TokenResponse]:
    """Rotate a refresh token, issuing a fresh access/refresh pair."""
    pair = await tokens.refresh(body.refresh_token)
    data = TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=settings.auth.jwt_access_token_ttl_seconds,
    )
    return SuccessResponse(message="Token refreshed.", data=data, meta=_meta())


@router.post("/logout", response_model=SuccessResponse[dict[str, bool]])
async def logout(body: LogoutRequest, auth: AuthSvc) -> SuccessResponse[dict[str, bool]]:
    """Log out, revoking the presented refresh token and terminating its session."""
    if body.refresh_token is not None:
        await auth.logout(refresh_token=body.refresh_token)
    return SuccessResponse(message="Logged out.", data={"success": True}, meta=_meta())


__all__ = ["router"]
