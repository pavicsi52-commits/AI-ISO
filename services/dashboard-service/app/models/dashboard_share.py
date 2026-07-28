"""``dashboard_shares`` table -- one grant of access to a dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SharePermission


class DashboardShare(BaseModel):
    """One share.

    A share is either **directed** (``shared_with_user_id`` set) or a
    **read-only link** (``share_token`` set). The token is a bearer
    credential for someone with no session, so it is returned exactly
    once to its creator and never from a listing endpoint -- the same
    rule ``services/reporting-service`` established for report links.

    ``revoked_at`` rather than deletion: revoking must leave evidence
    that access was once granted, which a deleted row cannot provide.
    """

    __tablename__ = "dashboard_shares"

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    shared_with_user_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    shared_with_role: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    permission: Mapped[SharePermission] = mapped_column(
        String(16), default=SharePermission.VIEW, index=True
    )
    share_token: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    shared_by: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


__all__ = ["DashboardShare"]
