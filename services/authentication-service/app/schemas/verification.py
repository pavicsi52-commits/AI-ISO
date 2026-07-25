"""Request schemas for POST /auth/{verify-email,resend-verification}."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


class VerifyEmailRequest(BaseModel):
    """Body of ``POST /auth/verify-email``."""

    token: str


class ResendVerificationRequest(BaseModel):
    """Body of ``POST /auth/resend-verification``."""

    email: EmailStr


__all__ = ["ResendVerificationRequest", "VerifyEmailRequest"]
