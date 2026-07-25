"""Request schema for ``POST /roles/{id}/permissions``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class GrantPermissionRequest(BaseModel):
    """Body of ``POST /roles/{id}/permissions``."""

    permission_id: UUID


__all__ = ["GrantPermissionRequest"]
