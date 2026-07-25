"""Process-wide settings cache and the Configuration API.

Loads configuration once per process and serves it from memory, with an
explicit :func:`reload_settings` for development hot-reload
(docs/013_Configuration_Framework.md.txt "HOT RELOAD" -- development only)
and an optional TTL for environments that want periodic re-reads without a
file watcher ("CONFIGURATION CACHE" section).

The typed ``get_*`` accessors ("CONFIGURATION API" section) also live here
rather than in :mod:`shared_core.config.loader`, purely to avoid a circular
import: they need the cached :class:`~shared_core.config.loader.Settings`
instance, and :mod:`loader` must stay independent of this module.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import fields as dataclass_fields
from typing import Any, cast

from shared_core.config.constants import ConfigConstants
from shared_core.config.defaults import DEFAULTS
from shared_core.config.exceptions import MissingVariableError
from shared_core.config.helpers import (
    coerce_bool,
    coerce_dict,
    coerce_float,
    coerce_int,
    coerce_list,
)
from shared_core.config.loader import Settings, load_settings
from shared_core.logging import get_logger

logger = get_logger(__name__)

_UNSET: Any = object()


class _SettingsCache:
    """Thread-safe lazy singleton holder for :class:`Settings`, with an optional TTL."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._settings: Settings | None = None
        self._loaded_at: float | None = None
        self._ttl_seconds: float | None = ConfigConstants.DEFAULT_CACHE_TTL_SECONDS

    def get(self) -> Settings:
        with self._lock:
            if self._settings is not None and self._is_expired():
                self._settings = None
            if self._settings is None:
                self._settings = load_settings()
                self._loaded_at = time.monotonic()
        return self._settings

    def reload(self) -> Settings:
        with self._lock:
            self._settings = load_settings()
            self._loaded_at = time.monotonic()
        return self._settings

    def clear(self) -> None:
        with self._lock:
            self._settings = None
            self._loaded_at = None

    def configure_ttl(self, ttl_seconds: float | None) -> None:
        with self._lock:
            self._ttl_seconds = ttl_seconds

    def _is_expired(self) -> bool:
        if self._ttl_seconds is None or self._loaded_at is None:
            return False
        return (time.monotonic() - self._loaded_at) > self._ttl_seconds


_cache = _SettingsCache()


def get_settings() -> Settings:
    """Return the cached :class:`Settings`, loading it on first access (or after TTL expiry)."""
    return _cache.get()


def reload_settings() -> Settings:
    """Force a reload of configuration from the environment.

    Intended for development hot-reload only; production code should treat
    configuration as immutable for the lifetime of the process.
    """
    settings = _cache.reload()
    logger.info("config.reload")
    return settings


def clear_settings_cache() -> None:
    """Clear the cached settings so the next :func:`get_settings` reloads.

    Primarily for test isolation.
    """
    _cache.clear()


def configure_cache_ttl(ttl_seconds: float | None) -> None:
    """Set how long the cached :class:`Settings` remains valid before an
    automatic reload, or ``None`` to cache until an explicit reload/clear.
    """
    _cache.configure_ttl(ttl_seconds)


def _iter_field_values(settings: Settings) -> list[tuple[str, Any]]:
    values: list[tuple[str, Any]] = []
    for section_field in dataclass_fields(settings):
        section = getattr(settings, section_field.name)
        for name in type(section).model_fields:
            values.append((name, getattr(section, name)))
    return values


def get(key: str, default: Any = None) -> Any:
    """Look up a configuration value by field name (e.g. ``"database_host"``).

    Resolution order: the loaded :class:`Settings` sections, then the raw
    ``AIIOS_<KEY>`` environment variable, then the field's own default,
    then *default*.
    """
    normalized = key.lower()
    for name, value in _iter_field_values(get_settings()):
        if name == normalized:
            return value

    env_key = f"{ConfigConstants.ENV_PREFIX}{key.upper()}"
    if env_key in os.environ:
        return os.environ[env_key]
    if env_key in DEFAULTS:
        return DEFAULTS[env_key]
    return default


def exists(key: str) -> bool:
    """Whether *key* resolves to a value anywhere in the configuration."""
    return get(key, _UNSET) is not _UNSET


def _typed_get(key: str, default: Any, coerce: Any) -> Any:
    value = get(key, _UNSET)
    if value is _UNSET:
        if default is _UNSET:
            raise MissingVariableError(key)
        return default
    return coerce(value)


def get_string(key: str, default: Any = _UNSET) -> str:
    """Return the configuration value for *key* as a ``str``."""
    return cast(str, _typed_get(key, default, str))


def get_bool(key: str, default: Any = _UNSET) -> bool:
    """Return the configuration value for *key* as a ``bool``."""
    return cast(bool, _typed_get(key, default, lambda v: coerce_bool(key, v)))


def get_int(key: str, default: Any = _UNSET) -> int:
    """Return the configuration value for *key* as an ``int``."""
    return cast(int, _typed_get(key, default, lambda v: coerce_int(key, v)))


def get_float(key: str, default: Any = _UNSET) -> float:
    """Return the configuration value for *key* as a ``float``."""
    return cast(float, _typed_get(key, default, lambda v: coerce_float(key, v)))


def get_list(key: str, default: Any = _UNSET, *, separator: str = ",") -> list[str]:
    """Return the configuration value for *key* as a ``list[str]``."""
    return cast(
        "list[str]", _typed_get(key, default, lambda v: coerce_list(key, v, separator=separator))
    )


def get_dict(key: str, default: Any = _UNSET) -> dict[str, Any]:
    """Return the configuration value for *key* as a ``dict``."""
    return cast("dict[str, Any]", _typed_get(key, default, lambda v: coerce_dict(key, v)))


def reload() -> Settings:
    """Alias for :func:`reload_settings` matching the framework's
    Configuration API naming (docs/013_Configuration_Framework.md.txt).
    """
    return reload_settings()
