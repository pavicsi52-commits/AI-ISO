"""Pagination.

Per docs/018_Enterprise_Database_Framework.md.txt "PAGINATION": Page,
Offset, Cursor, Infinite Scroll, Metadata (Total, Current Page, Page Size,
Has Next, Has Previous). Offset pagination (:func:`paginate_by_offset`)
suits admin tables with jump-to-page UI; cursor pagination
(:func:`paginate_by_cursor`) suits infinite-scroll feeds and stays correct
under concurrent inserts, where offset pagination can skip or repeat rows.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared_core.database.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from shared_core.database.helpers import clamp, normalize_page_params


@dataclass(frozen=True, slots=True)
class PageRequest:
    """A requested page: 1-indexed page number and page size."""

    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class PaginationMetadata:
    """Metadata describing one page's position within the full result set."""

    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool

    @property
    def total_pages(self) -> int:
        """Total number of pages, given ``total`` and ``page_size``."""
        if self.page_size <= 0:
            return 0
        return -(-self.total // self.page_size)


@dataclass(frozen=True, slots=True)
class PaginatedResult[T]:
    """A page of results plus its :class:`PaginationMetadata`."""

    items: list[T]
    metadata: PaginationMetadata


@dataclass(frozen=True, slots=True)
class CursorPage[T]:
    """A page of cursor-paginated results ("infinite scroll")."""

    items: list[T]
    next_cursor: str | None
    has_next: bool


async def paginate_by_offset(
    session: AsyncSession,
    stmt: Select[Any],
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> PaginatedResult[Any]:
    """Paginate *stmt* by page number and size, computing the total via ``COUNT(*)``."""
    resolved_page, resolved_size = normalize_page_params(page, page_size)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    offset = (resolved_page - 1) * resolved_size
    page_stmt = stmt.limit(resolved_size).offset(offset)
    items = list((await session.execute(page_stmt)).scalars().all())

    metadata = PaginationMetadata(
        total=total,
        page=resolved_page,
        page_size=resolved_size,
        has_next=offset + len(items) < total,
        has_previous=resolved_page > 1,
    )
    return PaginatedResult(items=items, metadata=metadata)


def encode_cursor(value: datetime, entity_id: UUID) -> str:
    """Encode a cursor position (an ordering timestamp plus a tie-breaking ID)."""
    payload = f"{value.isoformat()}|{entity_id}"
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode a cursor produced by :func:`encode_cursor`.

    Raises:
        ValueError: If *cursor* is malformed.
    """
    try:
        payload = base64.urlsafe_b64decode(cursor.encode()).decode()
        value_str, id_str = payload.split("|", 1)
        return datetime.fromisoformat(value_str), UUID(id_str)
    except ValueError as exc:
        raise ValueError(f"Invalid pagination cursor: {cursor!r}") from exc


async def paginate_by_cursor(
    session: AsyncSession,
    stmt: Select[Any],
    model: type[Any],
    *,
    cursor_field: str = "created_at",
    cursor: str | None = None,
    limit: int | None = None,
) -> CursorPage[Any]:
    """Paginate *stmt* using a keyset cursor on *cursor_field* (a ``datetime`` column) + ``id``.

    Stable under concurrent inserts (unlike offset pagination): each page
    only ever asks for rows strictly after the last-seen ``(cursor_field,
    id)`` pair, so new rows inserted elsewhere in the set never shift
    already-returned results into or out of a later page.
    """
    resolved_limit = clamp(limit or DEFAULT_PAGE_SIZE, minimum=1, maximum=MAX_PAGE_SIZE)
    column = getattr(model, cursor_field)
    id_column = model.id

    ordered = stmt.order_by(column.asc(), id_column.asc())
    if cursor is not None:
        cursor_value, cursor_id = decode_cursor(cursor)
        ordered = ordered.where(
            (column > cursor_value) | ((column == cursor_value) & (id_column > cursor_id))
        )

    page_stmt = ordered.limit(resolved_limit + 1)
    rows = list((await session.execute(page_stmt)).scalars().all())

    has_next = len(rows) > resolved_limit
    items = rows[:resolved_limit]
    next_cursor = None
    if has_next and items:
        last = items[-1]
        next_cursor = encode_cursor(getattr(last, cursor_field), last.id)

    return CursorPage(items=items, next_cursor=next_cursor, has_next=has_next)


__all__ = [
    "CursorPage",
    "PageRequest",
    "PaginatedResult",
    "PaginationMetadata",
    "decode_cursor",
    "encode_cursor",
    "paginate_by_cursor",
    "paginate_by_offset",
]
