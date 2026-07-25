"""HTTP-related constants."""

from typing import Final


class HttpConstants:
    """HTTP protocol constants used across the platform."""

    API_PREFIX: Final[str] = "/api"
    API_V1_PREFIX: Final[str] = "/api/v1"

    HEADER_REQUEST_ID: Final[str] = "X-Request-ID"
    HEADER_CORRELATION_ID: Final[str] = "X-Correlation-ID"
    HEADER_ORGANIZATION_ID: Final[str] = "X-Organization-ID"
    HEADER_PROJECT_ID: Final[str] = "X-Project-ID"
    HEADER_AUTHORIZATION: Final[str] = "Authorization"
    HEADER_IDEMPOTENCY_KEY: Final[str] = "Idempotency-Key"
    HEADER_CONTENT_TYPE: Final[str] = "Content-Type"

    CONTENT_TYPE_JSON: Final[str] = "application/json"

    BEARER_PREFIX: Final[str] = "Bearer "

    DEFAULT_PAGE: Final[int] = 1
    DEFAULT_PAGE_SIZE: Final[int] = 25
    MAX_PAGE_SIZE: Final[int] = 100

    DEFAULT_RATE_LIMIT_PER_MINUTE: Final[int] = 100

    MAX_UPLOAD_SIZE_BYTES: Final[int] = 100 * 1024 * 1024  # 100 MB
