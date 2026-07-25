"""Paginated response payload."""

from __future__ import annotations

from shared_core.schemas.base import BaseSchema
from shared_core.schemas.pagination import PaginationMeta


class PaginatedResponse[ItemT](BaseSchema):
    """Payload for endpoints returning a page of results."""

    items: list[ItemT]
    pagination: PaginationMeta
