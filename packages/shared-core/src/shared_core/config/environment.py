"""Deployment environment enumeration and detection."""

from __future__ import annotations

import os
from enum import StrEnum

from shared_core.config.exceptions import UnknownEnvironmentError


class Environment(StrEnum):
    """Deployment environment profiles per docs/013_Configuration_Framework.md.txt."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    TESTING = "testing"
    CI = "ci"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production(self) -> bool:
        """Whether this environment is production."""
        return self is Environment.PRODUCTION

    @property
    def allows_hot_reload(self) -> bool:
        """Whether configuration hot-reload is permitted in this environment.

        Per docs/013_Configuration_Framework.md.txt "HOT RELOAD": development
        only -- a developer's own machine (``local``) is included, but every
        shared environment, most importantly ``production``, is not.
        """
        return self in (Environment.DEVELOPMENT, Environment.LOCAL)


def parse_environment(value: str) -> Environment:
    """Parse *value* as an :class:`Environment`, strictly.

    Raises:
        UnknownEnvironmentError: If *value* does not name a supported
            environment.
    """
    try:
        return Environment(value.strip().lower())
    except ValueError as exc:
        raise UnknownEnvironmentError(value) from exc


def detect_environment() -> Environment:
    """Detect the current environment from ``AIIOS_ENVIRONMENT``.

    Defaults to :attr:`Environment.DEVELOPMENT` if unset or unrecognized.
    """
    raw = os.environ.get("AIIOS_ENVIRONMENT", Environment.DEVELOPMENT.value)
    try:
        return parse_environment(raw)
    except UnknownEnvironmentError:
        return Environment.DEVELOPMENT
