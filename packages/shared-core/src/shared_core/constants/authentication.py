"""Authentication-related constants."""

from typing import Final


class AuthConstants:
    """JWT, session, and password policy constants."""

    JWT_ALGORITHM: Final[str] = "RS256"
    ACCESS_TOKEN_TTL_SECONDS: Final[int] = 900
    REFRESH_TOKEN_TTL_SECONDS: Final[int] = 604_800
    JWT_ISSUER: Final[str] = "ai-ios"

    PASSWORD_MIN_LENGTH: Final[int] = 12
    PASSWORD_MAX_LENGTH: Final[int] = 128
    PASSWORD_HISTORY_SIZE: Final[int] = 5

    SESSION_IDLE_TIMEOUT_SECONDS: Final[int] = 1_800
    SESSION_ABSOLUTE_TIMEOUT_SECONDS: Final[int] = 28_800
    MAX_CONCURRENT_SESSIONS: Final[int] = 5

    API_KEY_PREFIX: Final[str] = "aiios_"
    API_KEY_LENGTH: Final[int] = 48
