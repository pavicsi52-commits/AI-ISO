"""Small, dependency-free utility functions shared across the framework.

Per docs/018_Enterprise_Database_Framework.md.txt "HELPERS": UUID Helper,
Timestamp Helper, Query Helper, Pagination Helper, Search Helper, Sort
Helper, Filter Helper, Migration Helper. Each of those maps to one function
here rather than a dedicated module -- they're small enough that a whole
file per concept would be indirection for its own sake, and
:mod:`~shared_core.database.pagination`, :mod:`~shared_core.database.filtering`,
:mod:`~shared_core.database.search`, and :mod:`~shared_core.database.sorting`
already own the richer, type-specific logic that builds on top of these.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Final

from shared_core.database.constants import (
    DEFAULT_PAGE_NUMBER,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)

_LIKE_WILDCARDS: Final = re.compile(r"([%_\\])")
_WHITESPACE: Final = re.compile(r"\s+")
_SLUG_INVALID: Final = re.compile(r"[^a-z0-9]+")


def new_uuid() -> uuid.UUID:
    """Generate a new entity UUID.

    The single call site every framework module uses to mint an ID, so a
    future switch of ID scheme touches one function.
    """
    return uuid.uuid4()


def utcnow() -> datetime:
    """Current UTC timestamp, timezone-aware.

    Every framework timestamp column uses this rather than
    ``datetime.utcnow()`` (naive, deprecated) or ``datetime.now()``
    (local-timezone, non-deterministic across deployments).
    """
    return datetime.now(UTC)


def escape_like_wildcards(term: str) -> str:
    """Escape ``%``, ``_``, and ``\\`` so *term* is safe inside a LIKE/ILIKE pattern."""
    return _LIKE_WILDCARDS.sub(r"\\\1", term)


def build_like_pattern(term: str, *, anchor_start: bool = False, anchor_end: bool = False) -> str:
    """Build an escaped LIKE/ILIKE pattern from *term*.

    ``anchor_start=True`` requires the match to start with *term*
    (``"term%"`` -- a "starts with" filter). ``anchor_end=True`` requires it
    to end with *term* (``"%term"`` -- "ends with"). Neither anchored is
    "contains" (``"%term%"``); both anchored is an exact match.
    """
    escaped = escape_like_wildcards(term)
    prefix = "" if anchor_start else "%"
    suffix = "" if anchor_end else "%"
    return f"{prefix}{escaped}{suffix}"


def normalize_page_params(page: int | None, page_size: int | None) -> tuple[int, int]:
    """Clamp *page*/*page_size* to sane, bounded values.

    A non-positive or missing page becomes page 1; a non-positive, missing,
    or too-large page size is clamped to
    ``[1, shared_core.database.constants.MAX_PAGE_SIZE]``.
    """
    resolved_page = page if page and page > 0 else DEFAULT_PAGE_NUMBER
    resolved_size = page_size if page_size and page_size > 0 else DEFAULT_PAGE_SIZE
    return resolved_page, min(resolved_size, MAX_PAGE_SIZE)


def sanitize_search_term(term: str) -> str:
    """Trim and collapse internal whitespace in a user-supplied search term."""
    return _WHITESPACE.sub(" ", term.strip())


def clamp(value: int, *, minimum: int, maximum: int) -> int:
    """Clamp *value* into ``[minimum, maximum]``."""
    return max(minimum, min(value, maximum))


def migration_file_slug(message: str) -> str:
    """Turn a human-readable migration message into a filename-safe slug.

    ``"Add users table!"`` -> ``"add_users_table"``.
    """
    slug = _SLUG_INVALID.sub("_", message.strip().lower()).strip("_")
    return slug or "migration"


__all__ = [
    "build_like_pattern",
    "clamp",
    "escape_like_wildcards",
    "migration_file_slug",
    "new_uuid",
    "normalize_page_params",
    "sanitize_search_term",
    "utcnow",
]
