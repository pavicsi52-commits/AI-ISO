"""Application settings loaded from environment variables.

All variables are prefixed ``AIIOS_`` per
``docs/013_Configuration_Framework.md.txt``. This is a minimal, service-local
settings loader for the platform foundation phase; once
``packages/shared-core/config`` exists (Prompt 013) this module is replaced
by the shared configuration framework.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Gateway service configuration.

    Attributes:
        environment: Deployment environment name.
        app_name: Logical application name, used in logs and health payloads.
        app_version: Semantic version of the running build.
        debug: Enables verbose behavior such as auto-reload friendly logging.
        log_level: Minimum log level emitted by the structured logger.
        host: Interface the ASGI server binds to.
        port: Port the ASGI server binds to.
    """

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "testing", "staging", "production"] = "development"
    app_name: str = Field(default="gateway")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    log_level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Binds all interfaces so the service is reachable inside a container.
    gateway_host: str = Field(default="0.0.0.0")  # nosec B104
    gateway_port: int = Field(default=8000, ge=1, le=65535)
    # Explicit origin allow-list for production CORS
    # (docs/017_Enterprise_Security_Framework.md.txt "CORS"); ignored
    # outside production, where a permissive dev config is used instead.
    cors_allowed_origins: list[str] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance.

    Cached with :func:`functools.lru_cache` so the environment is parsed
    once per process and can be injected via FastAPI ``Depends``.
    """
    return Settings()
