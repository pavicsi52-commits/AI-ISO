"""Sort request schema."""

from __future__ import annotations

from pydantic import Field

from shared_core.requests.base import BaseRequest
from shared_core.schemas.sorting import SortParams


class SortRequest(BaseRequest):
    """Inbound list of sort keys for a list endpoint."""

    sort: list[SortParams] = Field(default_factory=list)
