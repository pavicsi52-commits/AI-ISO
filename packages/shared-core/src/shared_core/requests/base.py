"""Base request schema."""

from __future__ import annotations

from shared_core.schemas.base import BaseSchema


class BaseRequest(BaseSchema):
    """Base class for every inbound API request payload."""
