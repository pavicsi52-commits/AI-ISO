"""TTL management.

Per docs/019_Enterprise_Cache_Framework.md.txt "TTL MANAGEMENT": Default
TTL, Custom TTL, Sliding TTL, Absolute TTL, No Expiration, Automatic
Expiration, TTL Metrics, TTL Validation.

"Automatic Expiration" is Redis's own job (every key set with an ``EX``
survives exactly that long, no framework polling needed); "Sliding TTL" is
implemented at the call site via :meth:`shared_core.cache.manager.CacheManager.touch`
(each access extends the TTL) rather than as a value represented here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final

from shared_core.cache.constants import DEFAULT_TTL_SECONDS, MAX_TTL_SECONDS, MIN_TTL_SECONDS
from shared_core.cache.exceptions import CacheTTLError

#: Sentinel TTL value meaning "no expiration" (Redis ``PERSIST`` semantics),
#: distinct from ``None`` meaning "use the framework default."
NO_EXPIRATION: Final[int] = -1


class TTLPolicy(StrEnum):
    """How a cached value's expiration is determined."""

    DEFAULT = "default"
    CUSTOM = "custom"
    SLIDING = "sliding"
    ABSOLUTE = "absolute"
    NO_EXPIRATION = "no_expiration"


def validate_ttl(ttl_seconds: int) -> None:
    """Raise :class:`CacheTTLError` if *ttl_seconds* is out of the allowed range.

    :data:`NO_EXPIRATION` always passes.
    """
    if ttl_seconds == NO_EXPIRATION:
        return
    if not (MIN_TTL_SECONDS <= ttl_seconds <= MAX_TTL_SECONDS):
        raise CacheTTLError(
            f"TTL must be between {MIN_TTL_SECONDS} and {MAX_TTL_SECONDS} seconds "
            f"(or {NO_EXPIRATION} for no expiration), got {ttl_seconds}."
        )


def resolve_ttl(ttl_seconds: int | None, *, default: int = DEFAULT_TTL_SECONDS) -> int | None:
    """Resolve a caller-supplied TTL against the framework default.

    Returns ``None`` (Redis "no expiration") if the resolved value is
    :data:`NO_EXPIRATION`; otherwise the (validated) TTL in seconds.
    """
    resolved = default if ttl_seconds is None else ttl_seconds
    if resolved == NO_EXPIRATION:
        return None
    validate_ttl(resolved)
    return resolved


def absolute_expiry(ttl_seconds: int) -> datetime:
    """Compute the wall-clock UTC instant a key set with this TTL will expire at."""
    validate_ttl(ttl_seconds)
    return datetime.now(UTC) + timedelta(seconds=ttl_seconds)


def ttl_remaining_ratio(*, ttl_seconds: int, remaining_seconds: int) -> float:
    """Return the fraction of a key's TTL still remaining, in ``[0.0, 1.0]``.

    Feeds "TTL Metrics" (docs/019) -- a low ratio across many keys signals
    a TTL that's too short for the access pattern (thrashing) rather than
    a true expiration.
    """
    if ttl_seconds <= 0:
        return 0.0
    return max(0.0, min(1.0, remaining_seconds / ttl_seconds))


__all__ = [
    "NO_EXPIRATION",
    "TTLPolicy",
    "absolute_expiry",
    "resolve_ttl",
    "ttl_remaining_ratio",
    "validate_ttl",
]
