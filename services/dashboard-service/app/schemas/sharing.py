"""Request and response shapes for sharing and access control.

**``ShareSummary`` has no token field, and that is deliberate.** A link
token is a bearer credential for someone with no session; it is
returned once, by :class:`ShareLinkResponse`, to whoever created it. A
listing endpoint that echoed tokens back would hand every viewer of the
share list a working credential for every link.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SharePermission


class ShareWithUserRequest(BaseModel):
    """Share a dashboard directly with one person."""

    dashboard_id: UUID
    user_id: UUID
    permission: SharePermission = SharePermission.VIEW
    expires_at: datetime | None = None


class ShareLinkRequest(BaseModel):
    """Mint a read-only link.

    No permission field: a link always grants ``VIEW``. Handing edit
    rights to whoever holds a URL is not something this service will do.
    """

    dashboard_id: UUID
    ttl_seconds: int | None = Field(default=None, ge=60, le=2_592_000)


class ShareSummary(BaseModel):
    """One share, without its token."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dashboard_id: UUID
    shared_with_user_id: UUID | None
    permission: SharePermission
    expires_at: datetime | None
    revoked_at: datetime | None
    is_revoked: bool
    access_count: int
    is_link: bool = False


class ShareLinkResponse(BaseModel):
    """A newly minted link, with its token.

    The only response in this service that carries a token, and it is
    returned exactly once.
    """

    share: ShareSummary
    token: str
    expires_at: datetime | None


class RolePermissionRequest(BaseModel):
    """Grant a role a standing permission on one dashboard."""

    dashboard_id: UUID
    role: str = Field(min_length=1, max_length=64)
    permission: SharePermission = SharePermission.VIEW


class RolePermissionSummary(BaseModel):
    """One role's standing permission."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dashboard_id: UUID
    role: str
    permission: SharePermission
    enabled: bool


class AccessResponse(BaseModel):
    """What the calling user may do with a dashboard."""

    allowed: bool
    permission: SharePermission | None
    can_edit: bool
    can_manage: bool
    reason: str | None = None


__all__ = [
    "AccessResponse",
    "RolePermissionRequest",
    "RolePermissionSummary",
    "ShareLinkRequest",
    "ShareLinkResponse",
    "ShareSummary",
    "ShareWithUserRequest",
]
