"""Standard success response envelope per docs/006_API_Design_Master.md.txt."""

from __future__ import annotations

from shared_core.schemas.base import BaseSchema
from shared_core.schemas.meta import ResponseMeta


class SuccessResponse[DataT](BaseSchema):
    """Standard success envelope. Every successful API response uses this."""

    success: bool = True
    message: str
    data: DataT
    meta: ResponseMeta
