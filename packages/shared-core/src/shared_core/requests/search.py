"""Search request schema."""

from __future__ import annotations

from pydantic import Field

from shared_core.requests.base import BaseRequest


class SearchRequest(BaseRequest):
    """Inbound global-search query, per docs/006_API_Design_Master.md.txt."""

    q: str | None = Field(default=None, min_length=1, max_length=200)
