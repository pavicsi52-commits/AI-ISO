"""Response metadata schema shared by every API response."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from shared_core.schemas.base import BaseSchema


class ResponseMeta(BaseSchema):
    """Metadata attached to every response, per docs/006_API_Design_Master.md.txt."""

    request_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
