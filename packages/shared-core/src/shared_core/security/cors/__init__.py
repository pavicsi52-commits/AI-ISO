"""CORS configuration.

Per docs/017_Enterprise_Security_Framework.md.txt "CORS": Configurable
Origins, Methods, Headers, Credentials, Environment Specific.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CorsConfig:
    """CORS policy for one service."""

    allow_origins: tuple[str, ...] = ()
    allow_methods: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    allow_headers: tuple[str, ...] = (
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "X-Correlation-ID",
    )
    allow_credentials: bool = False
    max_age_seconds: int = 600


def development_cors_config() -> CorsConfig:
    """Permissive CORS for local development (wildcard origin, no credentials)."""
    return CorsConfig(allow_origins=("*",), allow_credentials=False)


def production_cors_config(allowed_origins: Sequence[str]) -> CorsConfig:
    """Strict, explicit-origin CORS for production.

    Credentials are only ever allowed alongside an explicit origin list --
    never combine wildcard origins with credentials (browsers reject it,
    and it would defeat CORS entirely).
    """
    return CorsConfig(allow_origins=tuple(allowed_origins), allow_credentials=True)


def is_origin_allowed(origin: str, *, config: CorsConfig) -> bool:
    """Return whether *origin* is permitted under *config*."""
    return "*" in config.allow_origins or origin in config.allow_origins
