"""Filter request schema."""

from __future__ import annotations

from pydantic import Field

from shared_core.requests.base import BaseRequest
from shared_core.schemas.filtering import FilterParams


class FilterRequest(BaseRequest):
    """Inbound list of filter clauses for a list endpoint."""

    filters: list[FilterParams] = Field(default_factory=list)
