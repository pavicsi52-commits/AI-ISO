"""Configuration-module-local constants.

Distinct from :mod:`shared_core.constants`, which holds domain-wide
constants shared across every subpackage -- these govern the configuration
loading/caching/hot-reload mechanics themselves.
"""

from __future__ import annotations

from typing import Final


class ConfigConstants:
    """Constants governing configuration loading, caching, and hot reload."""

    ENV_PREFIX: Final[str] = "AIIOS_"
    ENV_FILE_ENCODING: Final[str] = "utf-8"
    BASE_ENV_FILE: Final[str] = ".env"
    LOCAL_ENV_FILE: Final[str] = ".env.local"
    DEFAULT_CACHE_TTL_SECONDS: Final[float | None] = None
    DEFAULT_WATCH_POLL_INTERVAL_SECONDS: Final[float] = 2.0
    SECRET_FIELD_NAME_PATTERN: Final[str] = r"(password|secret|key|token)"
