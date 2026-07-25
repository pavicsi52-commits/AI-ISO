"""Environment helper functions.

Thin, generic helpers only. The full environment-loading pipeline lives in
``shared_core.config`` (docs/013_Configuration_Framework.md.txt).
"""

from __future__ import annotations

import os
from pathlib import Path


def get_env(name: str, default: str | None = None) -> str | None:
    """Return the environment variable ``name``, or ``default`` if unset."""
    return os.environ.get(name, default)


def get_env_bool(name: str, default: bool = False) -> bool:
    """Return the environment variable ``name`` parsed as a boolean."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_env_int(name: str, default: int = 0) -> int:
    """Return the environment variable ``name`` parsed as an integer."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def is_running_in_container() -> bool:
    """Return whether the process appears to be running inside a container."""
    return Path("/.dockerenv").exists() or os.environ.get("KUBERNETES_SERVICE_HOST") is not None
