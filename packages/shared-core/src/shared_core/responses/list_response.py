"""List response payload (unpaginated)."""

from __future__ import annotations

from shared_core.schemas.base import BaseSchema


class ListResponse[ItemT](BaseSchema):
    """Payload for endpoints returning a bounded, unpaginated collection."""

    items: list[ItemT]
    count: int
