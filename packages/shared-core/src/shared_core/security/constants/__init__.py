"""Security-framework-local constants.

Distinct from :class:`shared_core.constants.authentication.AuthConstants`
(domain-wide JWT/session/password/API-key defaults, Prompt 012) -- these
govern the newer subsystems this prompt adds: MFA, CSRF, rate limiting,
and RSA key size.
"""

from __future__ import annotations

from typing import Final


class SecurityFrameworkConstants:
    """Constants governing MFA, CSRF, rate limiting, and asymmetric encryption."""

    TOTP_DIGITS: Final[int] = 6
    TOTP_PERIOD_SECONDS: Final[int] = 30
    RECOVERY_CODE_COUNT: Final[int] = 10
    TRUSTED_DEVICE_TTL_DAYS: Final[int] = 30

    CSRF_TOKEN_LENGTH_BYTES: Final[int] = 32

    DEFAULT_RATE_LIMIT_WINDOW_SECONDS: Final[float] = 60.0

    RSA_KEY_SIZE_BITS: Final[int] = 4096
