"""Response schemas for ``POST/DELETE /users/avatar``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class AvatarResponse(BaseModel):
    """The result of an avatar upload."""

    id: UUID
    url: str
    thumbnail_url: str | None
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None


__all__ = ["AvatarResponse"]
