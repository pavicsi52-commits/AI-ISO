"""Standard error response envelope per docs/006_API_Design_Master.md.txt."""

from __future__ import annotations

from pydantic import Field

from shared_core.schemas.base import BaseSchema
from shared_core.schemas.meta import ResponseMeta


class ErrorDetail(BaseSchema):
    """A single structured error code and its details."""

    code: str
    details: list[str] = Field(default_factory=list)


class ErrorResponse(BaseSchema):
    """Standard error envelope. Every failed API response uses this."""

    success: bool = False
    message: str
    error: ErrorDetail
    meta: ResponseMeta
