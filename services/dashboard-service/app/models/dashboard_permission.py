"""``dashboard_permissions`` table -- role-based dashboard access."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SharePermission


class DashboardPermission(BaseModel):
    """One role's standing permission on one dashboard.

    Distinct from :class:`~app.models.dashboard_share.DashboardShare`:
    a share is an act ("Ana shared this with Ben on Tuesday") and is
    revocable with an audit trail, while a permission is a standing
    rule attached to a role. Collapsing them would force revocation
    history onto role configuration.
    """

    __tablename__ = "dashboard_permissions"
    __table_args__ = (
        UniqueConstraint("dashboard_id", "role", name="uq_dashboard_permission_role"),
    )

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dashboards.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(64), index=True)
    permission: Mapped[SharePermission] = mapped_column(
        String(16), default=SharePermission.VIEW, index=True
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


__all__ = ["DashboardPermission"]
