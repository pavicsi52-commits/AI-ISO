"""Search.

Per docs/018_Enterprise_Database_Framework.md.txt "SEARCH": PostgreSQL Full
Text Search, ILIKE, Trigram. ("Future: Vector Search" is explicitly out of
scope here -- pgvector-backed similarity search belongs to whichever future
prompt owns embeddings, not this framework.)
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from sqlalchemy import Select, func, or_

from shared_core.database.constants import (
    DEFAULT_FULL_TEXT_LANGUAGE,
    DEFAULT_TRIGRAM_SIMILARITY_THRESHOLD,
)
from shared_core.database.helpers import build_like_pattern, sanitize_search_term


class SearchMode(StrEnum):
    """Strategy used to match *query* against the searched columns."""

    ILIKE = "ilike"
    FULL_TEXT = "full_text"
    TRIGRAM = "trigram"


def apply_search(
    stmt: Select[Any],
    model: type[Any],
    fields: Sequence[str],
    query: str,
    *,
    mode: SearchMode = SearchMode.ILIKE,
    language: str = DEFAULT_FULL_TEXT_LANGUAGE,
    trigram_threshold: float = DEFAULT_TRIGRAM_SIMILARITY_THRESHOLD,
) -> Select[Any]:
    """Filter *stmt* to rows where *query* matches any of *fields*.

    - ``ILIKE``: simple case-insensitive substring match. Always correct,
      always available, slowest on large tables without a trigram index.
    - ``FULL_TEXT``: PostgreSQL ``tsvector``/``tsquery`` word-based search
      via ``websearch_to_tsquery`` (handles quoted phrases, ``-exclude``,
      ``OR``). Best for natural-language search fields.
    - ``TRIGRAM``: ``pg_trgm`` ``similarity()`` fuzzy matching, tolerant of
      typos. Requires the ``pg_trgm`` extension to be enabled on the
      database (see ``shared_core.database.migration``).

    An empty (post-sanitization) *query* or empty *fields* returns *stmt*
    unmodified -- no search means no filter, not "match nothing".
    """
    term = sanitize_search_term(query)
    if not term or not fields:
        return stmt

    columns = [getattr(model, field) for field in fields]

    if mode is SearchMode.ILIKE:
        pattern = build_like_pattern(term)
        return stmt.where(or_(*(column.ilike(pattern) for column in columns)))

    if mode is SearchMode.FULL_TEXT:
        document = func.to_tsvector(language, func.concat_ws(" ", *columns))
        tsquery = func.websearch_to_tsquery(language, term)
        return stmt.where(document.op("@@")(tsquery))

    if mode is SearchMode.TRIGRAM:
        return stmt.where(
            or_(*(func.similarity(column, term) > trigram_threshold for column in columns))
        )

    raise ValueError(f"Unsupported search mode: {mode!r}")  # pragma: no cover -- exhaustive above


__all__ = ["SearchMode", "apply_search"]
