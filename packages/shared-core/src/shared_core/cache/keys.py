"""Centralized cache key building.

Per docs/019_Enterprise_Cache_Framework.md.txt "CACHE KEYS": "Centralized
key builder... Never hardcode cache keys." Every domain-scoped key
(``organization:{id}``, ``project:{id}``, ``user:{id}``, ...) goes through
one of the named builders here rather than being assembled ad hoc at each
call site.
"""

from __future__ import annotations

from shared_core.cache.constants import KEY_PREFIX, KEY_SEPARATOR, MAX_KEY_LENGTH
from shared_core.cache.exceptions import InvalidCacheKeyError


def build_cache_key(*parts: str) -> str:
    """Build a namespaced cache key from the given parts.

    Example: ``build_cache_key("organization", str(org_id))`` ->
    ``"aiios:organization:<org_id>"``.
    """
    key = KEY_SEPARATOR.join((KEY_PREFIX, *parts))
    validate_cache_key(key)
    return key


def build_pattern(*parts: str) -> str:
    """Build a ``SCAN``/``KEYS``-style wildcard pattern from the given parts.

    Example: ``build_pattern("organization", "*")`` ->
    ``"aiios:organization:*"`` -- matches every organization key,
    regardless of ID. Used by pattern-based invalidation
    (:mod:`shared_core.cache.cleanup`).
    """
    return KEY_SEPARATOR.join((KEY_PREFIX, *parts))


def validate_cache_key(key: str) -> None:
    """Raise :class:`InvalidCacheKeyError` if *key* is empty, too long, or malformed.

    Raises:
        InvalidCacheKeyError: If *key* is empty/whitespace-only, exceeds
            :data:`~shared_core.cache.constants.MAX_KEY_LENGTH`, or contains
            a raw whitespace/control character (which would make the key
            ambiguous to read back or match with a pattern).
    """
    if not key or not key.strip():
        raise InvalidCacheKeyError("Cache key must not be empty.")
    if len(key) > MAX_KEY_LENGTH:
        raise InvalidCacheKeyError(f"Cache key exceeds the maximum length of {MAX_KEY_LENGTH}.")
    if any(char.isspace() or not char.isprintable() for char in key):
        raise InvalidCacheKeyError("Cache key must not contain whitespace or control characters.")


def organization_key(organization_id: str) -> str:
    """Key for an organization's cached data."""
    return build_cache_key("organization", organization_id)


def project_key(project_id: str) -> str:
    """Key for a project's cached data."""
    return build_cache_key("project", project_id)


def user_key(user_id: str) -> str:
    """Key for a user's cached data."""
    return build_cache_key("user", user_id)


def asset_key(asset_id: str) -> str:
    """Key for an asset's cached data."""
    return build_cache_key("asset", asset_id)


def inventory_key(inventory_id: str) -> str:
    """Key for an inventory item's cached data."""
    return build_cache_key("inventory", inventory_id)


def playbook_key(playbook_id: str) -> str:
    """Key for a playbook's cached data."""
    return build_cache_key("playbook", playbook_id)


def workflow_key(workflow_id: str) -> str:
    """Key for a workflow's cached data."""
    return build_cache_key("workflow", workflow_id)


def execution_key(execution_id: str) -> str:
    """Key for a workflow execution's cached data."""
    return build_cache_key("execution", execution_id)


def validation_key(validation_id: str) -> str:
    """Key for a validation run's cached data."""
    return build_cache_key("validation", validation_id)


def job_key(job_id: str) -> str:
    """Key for a background job's cached data."""
    return build_cache_key("job", job_id)


__all__ = [
    "asset_key",
    "build_cache_key",
    "build_pattern",
    "execution_key",
    "inventory_key",
    "job_key",
    "organization_key",
    "playbook_key",
    "project_key",
    "user_key",
    "validate_cache_key",
    "validation_key",
    "workflow_key",
]
