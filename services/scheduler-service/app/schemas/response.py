"""Standard API success response envelope per docs/006_API_Design_Master.md.txt.

Every endpoint in the platform returns this shape on success. The error
shape (``ErrorResponse``) is owned by
``shared_core.exceptions.register_exception_handlers`` -- no service
builds its own.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ResponseMeta(BaseModel):
    """Metadata attached to every response."""

    request_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SuccessResponse[DataT](BaseModel):
    """Standard success envelope."""

    success: bool = True
    message: str
    data: DataT
    meta: ResponseMeta


__all__ = ["ResponseMeta", "SuccessResponse"]
