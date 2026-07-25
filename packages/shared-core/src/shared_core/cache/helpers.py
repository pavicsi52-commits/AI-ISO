"""Small, dependency-free utility functions shared across the framework."""

from __future__ import annotations

from typing import Any

from shared_core.helpers.hash_helper import stable_hash


def stable_query_hash(**params: Any) -> str:
    """Build a deterministic hash of query parameters for cache-key construction.

    Sorted by parameter name so the same logical query always hashes the
    same way regardless of call-site keyword-argument order.
    """
    parts = (f"{name}={value!r}" for name, value in sorted(params.items()))
    return stable_hash(*parts)


def mask_sensitive_key(key: str, *, visible_chars: int = 4) -> str:
    """Mask all but the last *visible_chars* characters of a key, for safe logging."""
    if len(key) <= visible_chars:
        return "*" * len(key)
    return "*" * (len(key) - visible_chars) + key[-visible_chars:]


__all__ = ["mask_sensitive_key", "stable_query_hash"]
