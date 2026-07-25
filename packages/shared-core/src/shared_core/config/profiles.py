"""Per-environment behavioral profiles.

Distinct from :mod:`shared_core.config.environment`, which only detects
*which* environment is active -- this module says what that environment
*means* for framework-level behavior (debug mode, hot reload, cache TTL,
default log verbosity).
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_core.config.environment import Environment


@dataclass(frozen=True, slots=True)
class EnvironmentProfile:
    """Framework-level behavior defaults for one deployment environment."""

    debug: bool
    hot_reload_enabled: bool
    cache_ttl_seconds: float | None
    log_level: str


_PROFILES: dict[Environment, EnvironmentProfile] = {
    Environment.LOCAL: EnvironmentProfile(
        debug=True, hot_reload_enabled=True, cache_ttl_seconds=None, log_level="DEBUG"
    ),
    Environment.DEVELOPMENT: EnvironmentProfile(
        debug=True, hot_reload_enabled=True, cache_ttl_seconds=None, log_level="DEBUG"
    ),
    Environment.CI: EnvironmentProfile(
        debug=False, hot_reload_enabled=False, cache_ttl_seconds=None, log_level="INFO"
    ),
    Environment.TESTING: EnvironmentProfile(
        debug=False, hot_reload_enabled=False, cache_ttl_seconds=None, log_level="WARNING"
    ),
    Environment.STAGING: EnvironmentProfile(
        debug=False, hot_reload_enabled=False, cache_ttl_seconds=60.0, log_level="INFO"
    ),
    Environment.PRODUCTION: EnvironmentProfile(
        debug=False, hot_reload_enabled=False, cache_ttl_seconds=300.0, log_level="INFO"
    ),
}


def get_profile(environment: Environment) -> EnvironmentProfile:
    """Return the behavioral profile for *environment*."""
    return _PROFILES[environment]
