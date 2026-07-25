"""Request/response schemas for POST /auth/{login,logout,refresh,register}."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator
from shared_core.validators.fields.credentials import validate_password


def validated_password(value: str) -> str:
    """Validate *value* against the platform password policy, raising ``ValueError`` if weak.

    Shared across every schema with a password field
    (:mod:`app.schemas.auth`, :mod:`app.schemas.password`).
    """
    result = validate_password(value)
    if not result.valid:
        raise ValueError("; ".join(result.errors))
    return value


class RegisterRequest(BaseModel):
    """Body of ``POST /auth/register``."""

    email: EmailStr
    password: str
    display_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validated_password(value)


class LoginRequest(BaseModel):
    """Body of ``POST /auth/login``."""

    email: EmailStr
    password: str
    remember_me: bool = False
    device_fingerprint: str | None = None
    mfa_code: str | None = None


class RefreshRequest(BaseModel):
    """Body of ``POST /auth/refresh``."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Body of ``POST /auth/logout``."""

    refresh_token: str | None = None


class TokenResponse(BaseModel):
    """An issued access/refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class MfaChallengeResponse(BaseModel):
    """Returned instead of :class:`TokenResponse` when MFA is required to complete login."""

    mfa_required: Literal[True] = True
    mfa_challenge_id: str


class UserSummary(BaseModel):
    """A minimal, public-safe view of a user."""

    id: UUID
    email: str
    display_name: str | None
    is_email_verified: bool


__all__ = [
    "LoginRequest",
    "LogoutRequest",
    "MfaChallengeResponse",
    "RefreshRequest",
    "RegisterRequest",
    "TokenResponse",
    "UserSummary",
    "validated_password",
]
