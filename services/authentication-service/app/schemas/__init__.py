"""Pydantic request/response schemas for the authentication service's REST API."""

from __future__ import annotations

from app.schemas.apikey import ApiKeyCreatedResponse, ApiKeyCreateRequest, ApiKeySummary
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MfaChallengeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserSummary,
    validated_password,
)
from app.schemas.device import DeviceSummary
from app.schemas.health import HealthStatus, LivenessStatus, ReadinessCheck, ReadinessStatus
from app.schemas.mfa import MfaDisableRequest, MfaEnableResponse, MfaVerifyRequest
from app.schemas.password import ForgotPasswordRequest, ResetPasswordRequest
from app.schemas.profile import ProfileResponse
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.session import SessionSummary
from app.schemas.verification import ResendVerificationRequest, VerifyEmailRequest

__all__ = [
    "ApiKeyCreateRequest",
    "ApiKeyCreatedResponse",
    "ApiKeySummary",
    "DeviceSummary",
    "ForgotPasswordRequest",
    "HealthStatus",
    "LivenessStatus",
    "LoginRequest",
    "LogoutRequest",
    "MfaChallengeResponse",
    "MfaDisableRequest",
    "MfaEnableResponse",
    "MfaVerifyRequest",
    "ProfileResponse",
    "ReadinessCheck",
    "ReadinessStatus",
    "RefreshRequest",
    "RegisterRequest",
    "ResendVerificationRequest",
    "ResetPasswordRequest",
    "ResponseMeta",
    "SessionSummary",
    "SuccessResponse",
    "TokenResponse",
    "UserSummary",
    "VerifyEmailRequest",
    "validated_password",
]
