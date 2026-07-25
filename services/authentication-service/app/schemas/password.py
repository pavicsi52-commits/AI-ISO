"""Request schemas for POST /auth/{forgot-password,reset-password}."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.auth import validated_password


class ForgotPasswordRequest(BaseModel):
    """Body of ``POST /auth/forgot-password``."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Body of ``POST /auth/reset-password``."""

    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validated_password(value)


__all__ = ["ForgotPasswordRequest", "ResetPasswordRequest"]
