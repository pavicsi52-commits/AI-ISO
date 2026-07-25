"""Pagination request schema."""

from __future__ import annotations

from shared_core.requests.base import BaseRequest
from shared_core.schemas.pagination import PaginationParams


class PaginationRequest(BaseRequest, PaginationParams):
    """Inbound pagination parameters for a list endpoint."""
