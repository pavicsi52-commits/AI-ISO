"""Request/response schemas for POST /auth/mfa/{enable,disable,verify}."""

from __future__ import annotations

from pydantic import BaseModel


class MfaEnableResponse(BaseModel):
    """Returned once, immediately after enabling MFA -- the secret and recovery codes
    are never retrievable again.
    """

    secret: str
    otpauth_uri: str
    recovery_codes: list[str]


class MfaVerifyRequest(BaseModel):
    """Body of ``POST /auth/mfa/verify``.

    ``mfa_challenge_id`` is present when verifying as the second step of a
    login flow that returned :class:`app.schemas.auth.MfaChallengeResponse`;
    absent when a caller is proactively verifying an already-authenticated
    session (e.g. before a sensitive operation).
    """

    code: str
    mfa_challenge_id: str | None = None


class MfaDisableRequest(BaseModel):
    """Body of ``POST /auth/mfa/disable``."""

    code: str


__all__ = ["MfaDisableRequest", "MfaEnableResponse", "MfaVerifyRequest"]
